"""Install the FLStudioMCP MIDI controller script into FL Studio's Hardware folder."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def get_default_hardware_dir() -> Path:
    return Path.home() / "Documents" / "Image-Line" / "FL Studio" / "Settings" / "Hardware"


def get_default_piano_roll_dir() -> Path:
    return (
        Path.home() / "Documents" / "Image-Line" / "FL Studio" / "Settings" / "Piano roll scripts"
    )


def get_source_script() -> Path:
    try:
        from fl_studio_mcp.paths import get_fl_script_source

        return get_fl_script_source()
    except ImportError:
        return Path(__file__).resolve().parent.parent / "fl_script" / "device_FLStudioMCP.py"


def get_source_piano_roll_script() -> Path:
    try:
        from fl_studio_mcp.paths import get_piano_roll_script_source

        return get_piano_roll_script_source()
    except ImportError:
        return (
            Path(__file__).resolve().parent.parent / "fl_script" / "FLStudioMCP_PianoRoll.pyscript"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install FLStudioMCP controller and Piano Roll scripts into FL Studio."
    )
    parser.add_argument(
        "--target-dir",
        type=Path,
        default=get_default_hardware_dir() / "FLStudioMCP",
        help=(
            "Destination directory "
            "(default: ~/Documents/Image-Line/FL Studio/Settings/Hardware/FLStudioMCP)"
        ),
    )
    parser.add_argument(
        "--piano-roll-dir",
        type=Path,
        default=get_default_piano_roll_dir(),
        help="Destination directory for Piano Roll scripts",
    )
    args = parser.parse_args()

    src = get_source_script()
    if not src.exists():
        print(f"Error: source script not found at {src}", file=sys.stderr)
        return 1

    args.target_dir.mkdir(parents=True, exist_ok=True)
    dst = args.target_dir / "device_FLStudioMCP.py"
    shutil.copy2(src, dst)
    print(f"Installed FL Studio controller script to: {dst}")

    pr_src = get_source_piano_roll_script()
    if pr_src.exists():
        args.piano_roll_dir.mkdir(parents=True, exist_ok=True)
        pr_dst = args.piano_roll_dir / pr_src.name
        shutil.copy2(pr_src, pr_dst)
        print(f"Installed Piano Roll script to: {pr_dst}")

    print("Next steps in FL Studio -> Options -> MIDI Settings:")
    print("  1. Set Output 'FL_MCP_OUT' and Input 'FL_MCP_IN' to the same Port number (e.g. 10).")
    print("  2. Set Controller type for 'FL_MCP_IN' to 'FLStudioMCP' and enable it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
