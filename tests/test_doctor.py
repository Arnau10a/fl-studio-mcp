"""Tests for fl_studio_mcp.doctor diagnostic checks."""

from __future__ import annotations

import shutil
from pathlib import Path

from fl_studio_mcp.bridge import FLBridge
from fl_studio_mcp.doctor import main as doctor_main
from fl_studio_mcp.doctor import run_diagnostics
from fl_studio_mcp.paths import get_fl_script_source


def test_doctor_in_mock_mode_with_synced_script(tmp_path: Path) -> None:
    hw_dir = tmp_path / "Hardware"
    target = hw_dir / "FLStudioMCP" / "device_FLStudioMCP.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(get_fl_script_source(), target)

    bridge = FLBridge(mock_mode=True)
    try:
        report = run_diagnostics(bridge=bridge, hardware_dir=hw_dir)
        assert report["overall"] == "ok"
        assert report["checks"]["fl_script"]["in_sync"] is True
        assert report["checks"]["sysex_ping"]["status"] == "ok"
    finally:
        bridge.close()


def test_doctor_detects_missing_or_outdated_script(tmp_path: Path) -> None:
    hw_dir = tmp_path / "Hardware"
    bridge = FLBridge(mock_mode=True)
    try:
        report_missing = run_diagnostics(bridge=bridge, hardware_dir=hw_dir)
        assert report_missing["checks"]["fl_script"]["status"] == "warn"
        assert report_missing["overall"] == "warn"

        target = hw_dir / "FLStudioMCP" / "device_FLStudioMCP.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# stale copy\n", encoding="utf-8")
        report_stale = run_diagnostics(bridge=bridge, hardware_dir=hw_dir)
        assert report_stale["checks"]["fl_script"]["in_sync"] is False
        assert report_stale["checks"]["fl_script"]["status"] == "warn"
    finally:
        bridge.close()


def test_doctor_cli_json_output(monkeypatch, capsys) -> None:
    monkeypatch.setenv("FL_MCP_MOCK", "1")
    exit_code = doctor_main(["--json"])
    assert exit_code in (0, 1)
    out = capsys.readouterr().out
    assert '"overall"' in out
    assert '"sysex_ping"' in out
