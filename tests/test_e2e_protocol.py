"""End-to-end SysEx protocol tests exercising FLBridge against device_FLStudioMCP.py."""

from __future__ import annotations

import time

import pytest

from fl_studio_mcp.bridge import FLBridge


@pytest.fixture()
def mock_bridge() -> FLBridge:
    bridge = FLBridge(mock_mode=True)
    yield bridge
    bridge.close()


def test_e2e_all_18_sysex_commands(mock_bridge: FLBridge) -> None:
    # 1. ping
    ping = mock_bridge.call("ping")
    assert ping["pong"] is True
    assert ping["bpm"] == 150.0
    assert ping["channel_count"] == 4

    # 2. transport
    t_res = mock_bridge.call("transport", {"action": "set_bpm", "bpm": 175.0})
    assert t_res["bpm"] == 175.0
    t_res = mock_bridge.call("transport", {"action": "play"})
    assert t_res["playing"] is True
    t_res = mock_bridge.call("transport", {"action": "set_loop_mode", "mode": "song"})
    assert t_res["loop_mode"] == "song"
    t_res = mock_bridge.call("transport", {"action": "record"})
    assert t_res["recording"] is True
    t_res = mock_bridge.call("transport", {"action": "stop"})
    assert t_res["playing"] is False

    # 3 & 4. channels_list & channel_set
    ch_list = mock_bridge.call("channels_list")
    assert len(ch_list["channels"]) == 4
    ch_upd = mock_bridge.call(
        "channel_set",
        {
            "index": 0,
            "name": "Straikerz Kick",
            "volume": 0.9,
            "pan": -0.2,
            "muted": True,
            "mixer_track": 5,
            "select": True,
        },
    )
    assert ch_upd["name"] == "Straikerz Kick"
    assert ch_upd["muted"] is True
    assert ch_upd["mixer_track"] == 5

    # 5 & 6. step_sequencer & step_sequencer_get
    seq = mock_bridge.call(
        "step_sequencer",
        {"index": 0, "steps": [0, 4, 8, 12], "mode": "indices", "length": 16, "clear_first": True},
    )
    assert seq["steps"] == [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]
    got = mock_bridge.call("step_sequencer_get", {"index": 0, "length": 16})
    assert got["steps"] == seq["steps"]

    # 7. channel_editor
    ed = mock_bridge.call("channel_editor", {"index": 0, "open": True})
    assert ed["open"] is True

    # 8. patterns
    pats = mock_bridge.call("patterns", {"action": "list"})
    assert pats["current"] == 1
    created = mock_bridge.call("patterns", {"action": "find_or_create", "name": "Drop 1"})
    assert created["name"] == "Drop 1"
    renamed = mock_bridge.call("patterns", {"action": "rename", "index": 1, "name": "Intro"})
    assert renamed["name"] == "Intro"
    selected = mock_bridge.call("patterns", {"action": "select", "index": 1})
    assert selected["current"] == 1

    # 9 & 10 & 11. mixer_list, mixer_set, mixer_eq
    mix = mock_bridge.call("mixer_list", {"start": 0, "end": 8})
    assert len(mix["tracks"]) == 8
    m_upd = mock_bridge.call(
        "mixer_set",
        {"index": 1, "name": "Kick Bus", "volume": 0.85, "route_to": 0, "route_active": True},
    )
    assert m_upd["name"] == "Kick Bus"
    eq = mock_bridge.call(
        "mixer_eq", {"index": 1, "band": 0, "gain": 0.3, "frequency": 0.2, "bandwidth": 0.4}
    )
    assert eq["gain"] == 0.3

    # 12 & 13. playlist_list & playlist_set
    pl = mock_bridge.call("playlist_list", {"start": 1, "end": 4})
    assert len(pl["tracks"]) == 4
    pl_upd = mock_bridge.call("playlist_set", {"index": 1, "name": "Kicks", "muted": True})
    assert pl_upd["name"] == "Kicks"
    assert pl_upd["muted"] is True

    # 14. ui_focus
    ui_res = mock_bridge.call("ui_focus", {"window": "mixer", "mixer_track": 1})
    assert ui_res["focused"] == "mixer"

    # 15 & 16. plugin_params & plugin_set
    p_list = mock_bridge.call("plugin_params", {"index": 3, "slot": -1})
    assert p_list["plugin"] == "3x Osc"
    assert len(p_list["params"]) > 0
    p_set = mock_bridge.call(
        "plugin_set",
        {"index": 3, "slot": -1, "action": "set_param", "param_index": 0, "value": 0.91},
    )
    assert p_set["value"] == 0.91
    assert mock_bridge.call("plugin_set", {"index": 3, "action": "next_preset"})["preset"] == "next"
    assert mock_bridge.call("plugin_set", {"index": 3, "action": "prev_preset"})["preset"] == "prev"

    # 17. midi_note
    note = mock_bridge.call("midi_note", {"index": 3, "note": 60, "velocity": 110})
    assert note["note"] == 60
    assert (3, 60, 110) in mock_bridge.mock_runtime.note_events

    # 18. undo
    assert mock_bridge.call("undo", {"direction": "up"})["undo"] == "up"
    assert mock_bridge.call("undo", {"direction": "down"})["undo"] == "down"


def test_e2e_multi_chunk_sysex_and_error_propagation(mock_bridge: FLBridge) -> None:
    # Force a >512 hex char payload (multiple SysEx chunks both ways)
    big_name = "X" * 350
    res = mock_bridge.call("channel_set", {"index": 1, "name": big_name})
    assert res["name"] == big_name

    # Unknown command should return structured FL Studio error
    with pytest.raises(RuntimeError, match="FL Studio error: Unknown command"):
        mock_bridge.call("nonexistent_command")


def test_stale_rx_buffer_pruning(mock_bridge: FLBridge) -> None:
    mock_bridge._rx_buffers[999] = {0: "abcd"}
    mock_bridge._rx_timestamps[999] = time.monotonic() - 100.0
    mock_bridge._prune_stale_rx_buffers(time.monotonic(), max_age_s=10.0)
    assert 999 not in mock_bridge._rx_buffers
    assert 999 not in mock_bridge._rx_timestamps


def test_rx_buffer_cap_in_device_script(mock_bridge: FLBridge) -> None:
    script = mock_bridge.mock_runtime.script_module
    script._rx_buffers.clear()
    for i in range(40):
        # Partial chunk 0 of 2 frames directly into OnSysEx
        class _Ev:
            def __init__(self, msg_id: int) -> None:
                id_hi = (msg_id >> 7) & 0x7F
                id_lo = msg_id & 0x7F
                self.sysex = bytes([0xF0, 0x7D, 0x46, 0x4D, id_hi, id_lo, 0, 2]) + b"7b" + b"\xf7"
                self.handled = False

        script.OnSysEx(_Ev(i + 1))
    assert len(script._rx_buffers) <= script.MAX_RX_BUFFERS
