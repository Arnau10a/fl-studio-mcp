"""Bidirectional MIDI SysEx bridge between the MCP server and FL Studio."""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Protocol

import mido

SYSEX_HEADER = [0x7D, 0x46, 0x4D]  # 7D 'F' 'M' (mido strips F0/F7)
CHUNK_PAYLOAD_SIZE = 512

DEFAULT_OUT_TO_FL = os.environ.get("FL_MCP_IN_PORT", "FL_MCP_IN")
DEFAULT_IN_FROM_FL = os.environ.get("FL_MCP_OUT_PORT", "FL_MCP_OUT")


class MidiOutputPort(Protocol):
    def send(self, message: mido.Message) -> None: ...
    def close(self) -> None: ...


class MidiInputPort(Protocol):
    def iter_pending(self) -> Any: ...
    def close(self) -> None: ...


def is_mock_enabled() -> bool:
    """Return True when FL_MCP_MOCK is enabled in the environment."""
    return os.environ.get("FL_MCP_MOCK", "").strip().lower() in ("1", "true", "yes")


def _find_port(available: list[str], target: str) -> str | None:
    for name in available:
        if name == target or target.lower() in name.lower():
            return name
    return None


class FLBridge:
    """Thread-safe SysEx RPC client for FL Studio (live MIDI or in-memory simulator)."""

    def __init__(
        self,
        out_port_name: str | None = None,
        in_port_name: str | None = None,
        mock_mode: bool | None = None,
    ) -> None:
        self.out_port_name = out_port_name or os.environ.get("FL_MCP_IN_PORT", DEFAULT_OUT_TO_FL)
        self.in_port_name = in_port_name or os.environ.get("FL_MCP_OUT_PORT", DEFAULT_IN_FROM_FL)
        self._mock_mode_override = mock_mode
        self._lock = threading.Lock()
        self._next_id = 1
        self._out_port: MidiOutputPort | None = None
        self._in_port: MidiInputPort | None = None
        self._active_mock: bool | None = None
        self._mock_runtime: Any = None
        self._rx_buffers: dict[int, dict[int, str]] = {}
        self._rx_timestamps: dict[int, float] = {}

    @property
    def is_mock(self) -> bool:
        if self._mock_mode_override is not None:
            return self._mock_mode_override
        return is_mock_enabled()

    @property
    def mock_runtime(self) -> Any:
        """Return the active MockFLRuntime instance when running in mock mode."""
        if not self.is_mock:
            return None
        if self._mock_runtime is None:
            from fl_studio_mcp.simulator import MockFLRuntime

            self._mock_runtime = MockFLRuntime()
        return self._mock_runtime

    def list_ports(self) -> dict[str, list[str]]:
        if self.is_mock:
            return {
                "midi_inputs": [f"{self.in_port_name} (mock)"],
                "midi_outputs": [f"{self.out_port_name} (mock)"],
            }
        return {
            "midi_inputs": list(mido.get_input_names()),
            "midi_outputs": list(mido.get_output_names()),
        }

    def _ensure_connected(self) -> None:
        want_mock = self.is_mock
        if (
            self._out_port is not None
            and self._in_port is not None
            and self._active_mock == want_mock
        ):
            return

        if self._active_mock is not None and self._active_mock != want_mock:
            self.close()

        if want_mock:
            runtime = self.mock_runtime
            assert runtime is not None
            out_port, in_port = runtime.create_ports()
            self._out_port = out_port
            self._in_port = in_port
            self._active_mock = True
            return

        outputs = list(mido.get_output_names())
        inputs = list(mido.get_input_names())

        out_match = _find_port(outputs, self.out_port_name)
        in_match = _find_port(inputs, self.in_port_name)

        if not out_match or not in_match:
            raise RuntimeError(
                f"Virtual MIDI ports not found. Expected output='{self.out_port_name}' "
                f"and input='{self.in_port_name}'. "
                f"Make sure loopMIDI is running with ports '{self.out_port_name}' "
                f"and '{self.in_port_name}'. "
                f"Available outputs={outputs}, inputs={inputs}"
            )

        self._out_port = mido.open_output(out_match)
        self._in_port = mido.open_input(in_match)
        self._active_mock = False

    def close(self) -> None:
        if self._out_port is not None:
            self._out_port.close()
            self._out_port = None
        if self._in_port is not None:
            self._in_port.close()
            self._in_port = None
        self._active_mock = None
        self._rx_buffers.clear()
        self._rx_timestamps.clear()

    def _prune_stale_rx_buffers(self, now: float, max_age_s: float) -> None:
        stale = [msg_id for msg_id, ts in self._rx_timestamps.items() if (now - ts) > max_age_s]
        for msg_id in stale:
            self._rx_buffers.pop(msg_id, None)
            self._rx_timestamps.pop(msg_id, None)

    def call(
        self,
        cmd: str,
        params: dict[str, Any] | None = None,
        timeout: float = 4.0,
    ) -> dict[str, Any]:
        with self._lock:
            self._ensure_connected()
            assert self._out_port is not None and self._in_port is not None

            # Drain any stale messages
            for _ in self._in_port.iter_pending():
                pass
            self._prune_stale_rx_buffers(time.monotonic(), max(timeout * 2.0, 10.0))

            req_id = self._next_id
            self._next_id = (self._next_id % 16000) + 1

            payload = {"id": req_id, "cmd": cmd, "params": params or {}}
            raw_hex = json.dumps(payload, ensure_ascii=True).encode("utf-8").hex()
            total = max(1, (len(raw_hex) + CHUNK_PAYLOAD_SIZE - 1) // CHUNK_PAYLOAD_SIZE)

            id_hi = (req_id >> 7) & 0x7F
            id_lo = req_id & 0x7F

            for idx in range(total):
                chunk = raw_hex[idx * CHUNK_PAYLOAD_SIZE : (idx + 1) * CHUNK_PAYLOAD_SIZE]
                data = (
                    SYSEX_HEADER
                    + [id_hi, id_lo, idx & 0x7F, total & 0x7F]
                    + list(chunk.encode("ascii"))
                )
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
                    self._rx_timestamps[msg_id] = time.monotonic()
                    buf[chunk_idx] = chunk_hex
                    if len(buf) < total_chunks:
                        continue

                    full_hex = "".join(buf[i] for i in range(total_chunks) if i in buf)
                    self._rx_buffers.pop(msg_id, None)
                    self._rx_timestamps.pop(msg_id, None)
                    resp = json.loads(bytes.fromhex(full_hex).decode("utf-8"))
                    if resp.get("id") == req_id:
                        if not resp.get("ok"):
                            raise RuntimeError(f"FL Studio error: {resp.get('error', 'unknown')}")
                        result = resp.get("result", {})
                        return result if isinstance(result, dict) else {"value": result}

                time.sleep(0.005)

            self._rx_buffers.pop(req_id, None)
            self._rx_timestamps.pop(req_id, None)
            raise TimeoutError(
                f"Timed out waiting for FL Studio response to '{cmd}'. "
                "Verify FL Studio is open, FL_MCP_IN/OUT are enabled in MIDI Settings, "
                "and Controller Type is set to 'FLStudioMCP'."
            )
