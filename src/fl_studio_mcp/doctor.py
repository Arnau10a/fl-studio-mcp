"""Diagnostic checks for FL Studio MCP setup, MIDI ports, and controller script parity."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

from fl_studio_mcp.bridge import FLBridge, is_mock_enabled
from fl_studio_mcp.paths import get_default_hardware_dir, get_fl_script_source
from fl_studio_mcp.win_auto import find_fl_studio_hwnd


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_diagnostics(
    bridge: FLBridge | None = None,
    hardware_dir: Path | None = None,
) -> dict[str, Any]:
    """Run environment, script-parity, MIDI port, and FL Studio SysEx ping checks."""
    br = bridge or FLBridge()
    hw_dir = hardware_dir or get_default_hardware_dir()
    src_script = get_fl_script_source()
    installed_script = hw_dir / "FLStudioMCP" / "device_FLStudioMCP.py"

    checks: dict[str, dict[str, Any]] = {}

    # 1. Environment & Mode
    mock = br.is_mock or is_mock_enabled()
    checks["environment"] = {
        "status": "ok",
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "mock_mode": mock,
    }

    # 2. Controller script installation & parity
    if not src_script.exists():
        checks["fl_script"] = {
            "status": "fail",
            "message": f"Source controller script missing at {src_script}",
        }
    elif not installed_script.exists():
        checks["fl_script"] = {
            "status": "warn" if mock else "fail",
            "source": str(src_script),
            "installed": str(installed_script),
            "message": (
                "Controller script is not installed in FL Studio's Hardware directory. "
                "Run: uv run python scripts/install_fl_script.py"
            ),
        }
    else:
        src_hash = _sha256(src_script)
        dst_hash = _sha256(installed_script)
        in_sync = src_hash == dst_hash
        checks["fl_script"] = {
            "status": "ok" if in_sync else "warn",
            "source": str(src_script),
            "installed": str(installed_script),
            "in_sync": in_sync,
            "message": (
                "Controller script matches repository copy."
                if in_sync
                else "Installed controller script differs from repo; re-run install_fl_script.py."
            ),
        }

    # 3. MIDI ports
    ports = br.list_ports()
    inputs = ports.get("midi_inputs", [])
    outputs = ports.get("midi_outputs", [])
    has_out = any(br.out_port_name.lower() in p.lower() for p in outputs)
    has_in = any(br.in_port_name.lower() in p.lower() for p in inputs)
    checks["midi_ports"] = {
        "status": "ok" if (has_out and has_in) else "fail",
        "expected_out_to_fl": br.out_port_name,
        "expected_in_from_fl": br.in_port_name,
        "found_out": has_out,
        "found_in": has_in,
        "available_outputs": outputs,
        "available_inputs": inputs,
    }

    # 4. FL Studio window (Windows only, skipped in mock mode)
    if mock:
        checks["fl_window"] = {"status": "ok", "message": "Skipped (mock mode enabled)."}
    elif sys.platform != "win32":
        checks["fl_window"] = {
            "status": "warn",
            "message": "Non-Windows OS; FL Studio Win32 GUI automation unavailable.",
        }
    else:
        hwnd = find_fl_studio_hwnd()
        checks["fl_window"] = {
            "status": "ok" if hwnd else "fail",
            "hwnd": hwnd,
            "message": (
                "FL Studio window detected."
                if hwnd
                else "FL Studio window not found. Launch FL Studio."
            ),
        }

    # 5. Live SysEx RPC ping
    if has_out and has_in:
        t0 = time.perf_counter()
        try:
            pong = br.call("ping", timeout=2.5)
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            checks["sysex_ping"] = {
                "status": "ok",
                "latency_ms": latency_ms,
                "pong": pong,
            }
        except Exception as exc:
            checks["sysex_ping"] = {
                "status": "fail",
                "error": str(exc),
            }
    else:
        checks["sysex_ping"] = {
            "status": "fail",
            "message": "Skipped because expected MIDI ports were not found.",
        }

    statuses = [c["status"] for c in checks.values()]
    overall = "fail" if "fail" in statuses else ("warn" if "warn" in statuses else "ok")
    return {"overall": overall, "checks": checks}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnose fl-studio-mcp setup and connectivity.")
    parser.add_argument("--json", action="store_true", help="Output JSON diagnostics")
    args = parser.parse_args(argv)

    report = run_diagnostics()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"FL Studio MCP Doctor — overall: {report['overall'].upper()}")
        for name, info in report["checks"].items():
            badge = {"ok": "[OK]  ", "warn": "[WARN]", "fail": "[FAIL]"}.get(info["status"], "[?]")
            detail = info.get("message") or info.get("error") or ""
            if name == "sysex_ping" and info["status"] == "ok":
                detail = f"pong in {info['latency_ms']} ms (BPM={info['pong'].get('bpm')})"
            elif name == "midi_ports":
                detail = f"out={info['found_out']} in={info['found_in']}"
            elif name == "environment":
                detail = f"{info['platform']} / Python {info['python']} / mock={info['mock_mode']}"
            print(f"  {badge} {name}: {detail}")

    return 0 if report["overall"] != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())
