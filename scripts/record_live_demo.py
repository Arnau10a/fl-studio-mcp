"""Record a real animated GIF of FL Studio being controlled live via fl-studio-mcp.

Run this in your interactive Windows PowerShell while loopMIDI and FL Studio are open:
    uv run --with pillow python scripts/record_live_demo.py
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageGrab

from fl_studio_mcp import server as srv
from fl_studio_mcp.paths import get_project_root
from fl_studio_mcp.win_auto import focus_fl_studio


def _get_window_rect(hwnd: int) -> tuple[int, int, int, int]:
    user32: Any = ctypes.WinDLL("user32", use_last_error=True)
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return (rect.left, rect.top, rect.right, rect.bottom)


def main() -> int:
    ping = srv.fl_ping()
    print("Connected to FL Studio:", ping)

    hwnd = focus_fl_studio()
    bbox = _get_window_rect(hwnd)
    frames: list[Image.Image] = []
    durations: list[int] = []

    def snap(count: int = 1, delay_s: float = 0.14) -> None:
        for _ in range(count):
            img = ImageGrab.grab(bbox=bbox)
            img.thumbnail((960, 540), Image.Resampling.LANCZOS)
            frames.append(img)
            durations.append(int(delay_s * 1000))
            time.sleep(delay_s)

    # 1. Focus Channel Rack & set BPM
    srv.fl_ui_focus("channel_rack")
    srv.fl_transport("set_bpm", bpm=150.0)
    snap(4, 0.18)

    # 2. Program 4x4 kick + off-beat hat on Step Sequencer
    srv.fl_step_sequencer(index=0, steps=[0, 4, 8, 12], mode="indices", length=16)
    snap(3, 0.18)
    srv.fl_step_sequencer(index=1, steps=[4, 12], mode="indices", length=16)
    snap(3, 0.18)
    srv.fl_step_sequencer(index=2, steps=[2, 6, 10, 14], mode="indices", length=16)
    snap(4, 0.18)

    # 3. Focus Mixer, adjust track 1 & EQ
    srv.fl_ui_focus("mixer", mixer_track=1)
    srv.fl_mixer_set(index=1, name="Kick Bus", volume=0.85)
    srv.fl_mixer_eq(index=1, band=0, gain=0.25)
    snap(5, 0.18)

    # 4. Back to Channel Rack & hit Play!
    srv.fl_ui_focus("channel_rack")
    srv.fl_transport("play")
    snap(24, 0.12)
    srv.fl_transport("stop")

    out_gif: Path = get_project_root() / "docs" / "demo.gif"
    out_gif.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        out_gif,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )
    print(f"Saved live FL Studio GIF to: {out_gif} ({out_gif.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
