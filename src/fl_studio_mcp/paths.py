"""Centralized filesystem paths for fl-studio-mcp."""

from __future__ import annotations

import os
from pathlib import Path


def get_project_root() -> Path:
    """Locate the repository root containing fl_script/ or pyproject.toml."""
    here = Path(__file__).resolve()
    for parent in (here.parent.parent.parent, here.parent.parent, Path.cwd()):
        if (parent / "fl_script").exists() or (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


def get_output_dir() -> Path:
    """Return base directory for generated MIDI and WAV files."""
    override = os.environ.get("FL_MCP_OUTPUT_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return get_project_root() / "output"


def get_midi_out_dir() -> Path:
    return get_output_dir() / "midi"


def get_sample_out_dir() -> Path:
    return get_output_dir() / "samples"


def get_fl_script_source() -> Path:
    return get_project_root() / "fl_script" / "device_FLStudioMCP.py"


def get_default_hardware_dir() -> Path:
    return Path.home() / "Documents" / "Image-Line" / "FL Studio" / "Settings" / "Hardware"
