"""Bidirectional MIDI SysEx bridge between the MCP server and FL Studio."""

import json
import os
import threading
import time
from typing import Any

import mido

SYSEX_HEADER = [0x7D, 0x46, 0x4D]  # 7D 'F' 'M' (mido strips F0/F7)
CHUNK_PAYLOAD_SIZE = 512

DEFAULT_OUT_TO_FL = os.environ.get("FL_MCP_IN_PORT", "FL_MCP_IN")
DEFAULT_IN_FROM_FL = os.environ.get("FL_MCP_OUT_PORT", "FL_MCP_OUT")


def _find_port(available: list[str], target: str) -> str | None:
    for name in available:
        if name == target or target.lower() in name.lower():
            return name
    return None


class FLBridge:
    """Thread-safe SysEx RPC client for FL Studio."""

    def __init__(
        self,
        out_port_name: str = DEFAULT_OUT_TO_FL,
        in_port_name: str = DEFAULT_IN_FROM_FL,
    ) -> None:
        self.out_port_name = out_port_name
        self.in_port_name = in_port_name
        self._lock = threading.Lock()
        self._next_id = 1
        self._out_port = None
        self._in_port = None
        self._rx_buffers: dict[int, dict[int, str]] = {}

    def list_ports(self) -> dict[str, list[str]]:
        return {
            "midi_inputs": mido.get_input_names(),
            "midi_outputs": mido.get_output_names(),
        }

    def _ensure_connected(self) -> None:
        if self._out_port is not None and self._in_port is not None:
            return

        outputs = mido.get_output_names()
        inputs = mido.get_input_names()

        out_match = _find_port(outputs, self.out_port_name)
        in_match = _find_port(inputs, self.in_port_name)

        if not out_match or not in_match:
            raise RuntimeError(
                f"Virtual MIDI ports not found. Expected output='{self.out_port_name}' "
                f"and input='{self.in_port_name}'. "
                f"Make sure loopMIDI is running with ports '{self.out_port_name}' and '{self.in_port_name}'. "
                f"Available outputs={outputs}, inputs={inputs}"
            )

        self._out_port = mido.open_output(out_match)
        self._in_port = mido.open_input(in_match)

    def close(self) -> None:
        if self._out_port is not None:
            self._out_port.close()
            self._out_port = None
        if self._in_port is not None:
            self._in_port.close()
            self._in_port = None

    def call(self, cmd: str, params: dict[str, Any] | None = None, timeout: float = 4.0) -> dict[str, Any]:
        with self._lock:
            self._ensure_connected()
            assert self._out_port is not None and self._in_port is not None

            # Drain any stale messages
            for _ in self._in_port.iter_pending():
                pass

            req_id = self._next_id
            self._next_id = (self._next_id % 16000) + 1

            payload = {"id": req_id, "cmd": cmd, "params": params or {}}
            raw_hex = json.dumps(payload, ensure_ascii=True).encode("utf-8").hex()
            total = max(1, (len(raw_hex) + CHUNK_PAYLOAD_SIZE - 1) // CHUNK_PAYLOAD_SIZE)

            id_hi = (req_id >> 7) & 0x7F
            id_lo = req_id & 0x7F

            for idx in range(total):
                chunk = raw_hex[idx * CHUNK_PAYLOAD_SIZE : (idx + 1) * CHUNK_PAYLOAD_SIZE]
                data = SYSEX_HEADER + [id_hi, id_lo, idx & 0x7F, total & 0x7F] + list(chunk.encode("ascii"))
                self._out_port.send(mido.Message("sysex", data=data))

            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                for msg in self._in_port.iter_pending():
                    if msg.type != "sysex" or len(msg.data) < 7:
                        continue
                    if list(msg.data[:3]) != SYSEX_HEADER:
                        continue
                    msg_id = ((msg.data[3] & 0x7F) << 7) | (msg.data[4] & 0x7F)
                    chunk_idx = msg.data[5] & 0x7F
                    total_chunks = msg.data[6] & 0x7F
                    chunk_hex = bytes(msg.data[7:]).decode("ascii", errors="ignore")

                    buf = self._rx_buffers.setdefault(msg_id, {})
                    buf[chunk_idx] = chunk_hex
                    if len(buf) < total_chunks:
                        continue

                    full_hex = "".join(buf[i] for i in range(total_chunks) if i in buf)
                    self._rx_buffers.pop(msg_id, None)
                    resp = json.loads(bytes.fromhex(full_hex).decode("utf-8"))
                    if resp.get("id") == req_id:
                        if not resp.get("ok"):
                            raise RuntimeError(f"FL Studio error: {resp.get('error', 'unknown')}")
                        return resp.get("result", {})

                time.sleep(0.005)

            self._rx_buffers.pop(req_id, None)
            raise TimeoutError(
                f"Timed out waiting for FL Studio response to '{cmd}'. "
                "Verify FL Studio is open, FL_MCP_IN/OUT are enabled in MIDI Settings, "
                "and Controller Type is set to 'FLStudioMCP'."
            )
