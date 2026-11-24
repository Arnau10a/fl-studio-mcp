"""Unit tests for the SysEx RPC bridge protocol."""

import json
import unittest
from unittest.mock import patch

import mido

from bridge import CHUNK_PAYLOAD_SIZE, FLBridge, SYSEX_HEADER


class _FakePort:
    def __init__(self, on_send=None) -> None:
        self.sent: list[mido.Message] = []
        self.pending: list[mido.Message] = []
        self._on_send = on_send
        self.closed = False

    def send(self, msg: mido.Message) -> None:
        self.sent.append(msg)
        if self._on_send is not None:
            self._on_send(msg)

    def iter_pending(self):
        items = list(self.pending)
        self.pending.clear()
        return iter(items)

    def close(self) -> None:
        self.closed = True


def _encode_sysex_chunks(payload: dict) -> list[mido.Message]:
    raw_hex = json.dumps(payload, ensure_ascii=True).encode("utf-8").hex()
    total = max(1, (len(raw_hex) + CHUNK_PAYLOAD_SIZE - 1) // CHUNK_PAYLOAD_SIZE)
    msg_id = int(payload.get("id", 0)) & 0x3FFF
    id_hi = (msg_id >> 7) & 0x7F
    id_lo = msg_id & 0x7F
    msgs = []
    for idx in range(total):
        chunk = raw_hex[idx * CHUNK_PAYLOAD_SIZE : (idx + 1) * CHUNK_PAYLOAD_SIZE]
        data = SYSEX_HEADER + [id_hi, id_lo, idx & 0x7F, total & 0x7F] + list(chunk.encode("ascii"))
        msgs.append(mido.Message("sysex", data=data))
    return msgs


class TestFLBridge(unittest.TestCase):
    def test_roundtrip_single_and_multi_chunk_sysex(self) -> None:
        rx_buf: dict[int, dict[int, str]] = {}
        in_port = _FakePort()

        def handle_send(msg: mido.Message) -> None:
            data = list(msg.data)
            self.assertEqual(data[:3], SYSEX_HEADER)
            msg_id = ((data[3] & 0x7F) << 7) | (data[4] & 0x7F)
            idx = data[5] & 0x7F
            total = data[6] & 0x7F
            chunk_hex = bytes(data[7:]).decode("ascii")
            buf = rx_buf.setdefault(msg_id, {})
            buf[idx] = chunk_hex
            if len(buf) == total:
                full_hex = "".join(buf[i] for i in range(total))
                req = json.loads(bytes.fromhex(full_hex).decode("utf-8"))
                # Send back a multi-chunk response (> 512 hex chars)
                resp = {
                    "id": req["id"],
                    "ok": True,
                    "result": {"echo": req["cmd"], "blob": "x" * 600},
                }
                in_port.pending.extend(_encode_sysex_chunks(resp))

        out_port = _FakePort(on_send=handle_send)

        bridge = FLBridge()
        with (
            patch("bridge.mido.get_output_names", return_value=["FL_MCP_IN 1"]),
            patch("bridge.mido.get_input_names", return_value=["FL_MCP_OUT 2"]),
            patch("bridge.mido.open_output", return_value=out_port),
            patch("bridge.mido.open_input", return_value=in_port),
        ):
            res = bridge.call("ping", {"long": "y" * 400}, timeout=1.0)
            self.assertEqual(res["echo"], "ping")
            self.assertEqual(len(res["blob"]), 600)
            self.assertGreater(len(out_port.sent), 1)
            bridge.close()
            self.assertTrue(out_port.closed)
            self.assertTrue(in_port.closed)

    def test_fl_error_raises_runtime_error(self) -> None:
        in_port = _FakePort()

        def handle_send(msg: mido.Message) -> None:
            data = list(msg.data)
            msg_id = ((data[3] & 0x7F) << 7) | (data[4] & 0x7F)
            in_port.pending.extend(
                _encode_sysex_chunks({"id": msg_id, "ok": False, "error": "boom"})
            )

        out_port = _FakePort(on_send=handle_send)
        bridge = FLBridge()
        with (
            patch("bridge.mido.get_output_names", return_value=["FL_MCP_IN"]),
            patch("bridge.mido.get_input_names", return_value=["FL_MCP_OUT"]),
            patch("bridge.mido.open_output", return_value=out_port),
            patch("bridge.mido.open_input", return_value=in_port),
        ):
            with self.assertRaisesRegex(RuntimeError, "FL Studio error: boom"):
                bridge.call("bad_cmd", timeout=1.0)

    def test_missing_ports_raises_clear_error(self) -> None:
        bridge = FLBridge()
        with (
            patch("bridge.mido.get_output_names", return_value=[]),
            patch("bridge.mido.get_input_names", return_value=[]),
        ):
            with self.assertRaisesRegex(RuntimeError, "Virtual MIDI ports not found"):
                bridge.call("ping", timeout=0.1)


if __name__ == "__main__":
    unittest.main()
