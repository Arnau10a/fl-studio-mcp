"""Tests for MCP tools, resources, prompts, and FL_MCP_MOCK=1 end-to-end execution."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

import fl_studio_mcp.server as srv
import server as root_shim
from fl_studio_mcp import win_auto


def test_root_shim_exports_same_mcp() -> None:
    assert root_shim.mcp is srv.mcp


def test_registered_tools_resources_and_prompts() -> None:
    tools = srv.mcp._tool_manager.list_tools()
    tool_names = {t.name for t in tools}
    assert len(tool_names) == 32
    assert {
        "fl_doctor",
        "fl_analyze_audio",
        "fl_ping",
        "ht_generate_kick_sample",
        "fl_piano_roll_notes",
        "fl_piano_roll_state",
        "fl_piano_roll_clear",
    }.issubset(tool_names)

    resources = asyncio.run(srv.mcp.list_resources())
    uris = {str(r.uri) for r in resources}
    assert uris == {
        "fl://session/state",
        "fl://channels/rack",
        "fl://mixer/tracks",
        "fl://samples/output",
    }

    prompts = asyncio.run(srv.mcp.list_prompts())
    prompt_names = {p.name for p in prompts}
    assert prompt_names == {"hard_techno_drop", "mix_gain_staging"}


def test_mock_mode_tools_and_resources(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FL_MCP_MOCK", "1")
    monkeypatch.setenv("FL_MCP_OUTPUT_DIR", str(tmp_path))
    srv.bridge.close()
    srv.bridge._mock_runtime = None

    try:
        ping = srv.fl_ping()
        assert ping["pong"] is True

        added = srv.fl_add_plugin("Serum 2", target="channel")
        assert added["mock"] is True
        assert added["channel_count_after"] == added["channel_count_before"] + 1

        loaded = srv.fl_load_sample("kloenk")
        assert loaded["mock"] is True

        # Generate a real MIDI and import it in mock mode
        midi_path = tmp_path / "test_acid.mid"
        midi_path.write_bytes(b"MThd\x00\x00\x00\x06\x00\x00\x00\x01\x01\xe0")
        imp = srv.fl_import_midi(0, str(midi_path))
        assert imp["imported"] is True

        pr_add = srv.fl_piano_roll_notes(
            0,
            [{"number": 60, "time": 0, "length": 96, "velocity": 0.9}],
            clear_first=True,
        )
        assert pr_add["total_notes"] == 1
        pr_state = srv.fl_piano_roll_state(0)
        assert pr_state["note_count"] == 1
        assert srv.fl_piano_roll_clear(0)["cleared"] == 1

        deleted = srv.fl_delete_channel(0)
        assert deleted["channel_count_after"] == deleted["channel_count_before"] - 1

        new_proj = srv.fl_new_project()
        assert new_proj["new_project"] is True

        # Read MCP Resources
        state_res: Any = asyncio.run(srv.mcp.read_resource("fl://session/state"))
        state_text = state_res[0].content if isinstance(state_res, list) else str(state_res)
        assert json.loads(state_text)["pong"] is True

        # Render MCP Prompt
        prompt_res = asyncio.run(
            srv.mcp.get_prompt("hard_techno_drop", {"bpm": 160.0, "root_note": "G"})
        )
        assert "160.0 BPM" in str(prompt_res.messages[0].content)
    finally:
        srv.bridge.close()
        srv.bridge._mock_runtime = None


def test_win_auto_non_windows_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(win_auto, "user32", None)
    with pytest.raises(RuntimeError, match="only supported on Windows"):
        win_auto.find_fl_studio_hwnd()
