"""Record a real animated GIF of FL Studio being controlled live via fl-studio-mcp.

Demonstrates:
  1. Setting BPM & clearing pattern
  2. Loading a generator plugin (FLEX) via Plugin Picker & opening its UI
  3. Generating an expressive Violin melody (.mid) & importing it into the Piano Roll
  4. Programming drums on the Step Sequencer & sculpting Mixer EQ
  5. Live playback with Channel Rack / Mixer meters moving

Run in your interactive Windows PowerShell while loopMIDI and FL Studio are open
(with Settings closed):
    uv run --with pillow python scripts/record_live_demo.py
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import time
from pathlib import Path
from typing import Any

import mido
from PIL import Image, ImageDraw, ImageFont, ImageGrab

from fl_studio_mcp import server as srv
from fl_studio_mcp.paths import get_midi_out_dir, get_project_root
from fl_studio_mcp.win_auto import (
    VK_ESCAPE,
    focus_fl_studio,
    get_foreground_info,
    tap_vk,
)


def _get_window_rect(hwnd: int) -> tuple[int, int, int, int]:
    user32: Any = ctypes.WinDLL("user32", use_last_error=True)
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return (rect.left, rect.top, rect.right, rect.bottom)


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = Path(r"C:\Windows\Fonts\consolab.ttf" if bold else r"C:\Windows\Fonts\consola.ttf")
    if path.exists():
        return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _generate_violin_melody_midi(bpm: float = 140.0) -> Path:
    """Create an expressive 4-bar F Harmonic Minor violin melody (.mid)."""
    out_dir = get_midi_out_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "demo_violin_melody.mid"

    tpb = 480
    mid = mido.MidiFile(ticks_per_beat=tpb)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))

    # (beat_offset, midi_note, duration_beats, velocity)
    # F5=77, G5=79, Ab5=80, Bb5=82, C6=84, Db6=85, E6=88, F6=89
    phrase = [
        (0.0, 77, 1.5, 92),
        (1.5, 80, 0.5, 98),
        (2.0, 84, 1.5, 110),
        (3.5, 85, 0.5, 104),
        (4.0, 84, 1.0, 108),
        (5.0, 80, 1.0, 96),
        (6.0, 79, 2.0, 90),
        (8.0, 77, 1.0, 95),
        (9.0, 80, 1.0, 102),
        (10.0, 85, 1.5, 114),
        (11.5, 88, 0.5, 118),
        (12.0, 89, 2.0, 122),
        (14.0, 84, 1.0, 104),
        (15.0, 79, 1.0, 94),
    ]

    events: list[tuple[int, str, int, int]] = []
    for beat, note, dur_beats, vel in phrase:
        t_on = int(beat * tpb)
        t_off = int((beat + dur_beats * 0.94) * tpb)
        events.append((t_on, "note_on", note, vel))
        events.append((t_off, "note_off", note, 0))

    events.sort(key=lambda e: (e[0], 0 if e[1] == "note_off" else 1))
    last_tick = 0
    for tick, kind, note, vel in events:
        track.append(mido.Message(kind, note=note, velocity=vel, time=max(0, tick - last_tick)))
        last_tick = tick

    mid.save(out_path)
    return out_path


def _annotate_frame(
    img: Image.Image, cmd_label: str, status_label: str, playing: bool
) -> Image.Image:
    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    bar_h = 46
    draw.rectangle((0, h - bar_h, w, h), fill=(13, 17, 23, 228))
    draw.line((0, h - bar_h, w, h - bar_h), fill=(255, 145, 56, 225), width=2)

    font_cmd = _load_font(14, bold=True)
    font_st = _load_font(13, bold=False)

    if playing:
        draw.polygon([(16, h - 30), (16, h - 16), (27, h - 23)], fill=(63, 185, 80, 255))
    else:
        draw.ellipse((16, h - 28, 26, h - 18), fill=(255, 145, 56, 255))

    draw.text((36, h - 32), cmd_label, fill=(230, 237, 243, 255), font=font_cmd)
    st_w = int(draw.textlength(status_label, font=font_st))
    draw.text((w - st_w - 18, h - 31), status_label, fill=(63, 185, 80, 255), font=font_st)

    combined = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    return combined.quantize(colors=128, method=Image.Quantize.MEDIANCUT)


def main() -> int:
    ping = srv.fl_ping()
    print("Connected to FL Studio:", ping)

    hwnd = focus_fl_studio()
    fg_hwnd, fg_title, _ = get_foreground_info()
    if fg_hwnd and fg_hwnd != hwnd and "Settings" in fg_title:
        tap_vk(VK_ESCAPE)
        time.sleep(0.25)
        hwnd = focus_fl_studio()

    bbox = _get_window_rect(hwnd)
    frames: list[Image.Image] = []
    durations: list[int] = []

    def snap(
        cmd_label: str,
        status_label: str,
        *,
        playing: bool = False,
        count: int = 1,
        delay_s: float = 0.14,
    ) -> None:
        for _ in range(count):
            raw = ImageGrab.grab(bbox=bbox)
            raw.thumbnail((960, 540), Image.Resampling.LANCZOS)
            frames.append(_annotate_frame(raw, cmd_label, status_label, playing))
            durations.append(int(delay_s * 1000))
            time.sleep(delay_s)

    # 1. Reset transport & set 140 BPM
    srv.fl_transport("stop")
    srv.fl_transport("set_bpm", bpm=140.0)
    srv.fl_ui_focus("channel_rack")
    snap("MCP: fl_transport('set_bpm', 140.0)", "140.0 BPM", count=4, delay_s=0.16)

    # 2. Load FLEX plugin into Channel Rack & show its UI
    add_res = srv.fl_add_plugin("FLEX", target="channel")
    channels = srv.fl_channels_list()["channels"]
    violin_idx = channels[-1]["index"]
    srv.fl_channel_set(violin_idx, name="Violin Lead", mixer_track=2, select=True)
    srv.fl_channel_editor(violin_idx, open=True)
    time.sleep(0.35)
    snap(
        f"MCP: fl_add_plugin('FLEX') -> ch {violin_idx}",
        f"Channels: {add_res.get('channel_count_after')}",
        count=7,
        delay_s=0.18,
    )
    srv.fl_channel_editor(violin_idx, open=False)

    # 3. Generate expressive Violin melody & import into Piano Roll
    violin_mid = _generate_violin_melody_midi(bpm=140.0)
    srv.fl_import_midi(violin_idx, str(violin_mid))
    srv.fl_ui_focus("piano_roll")
    time.sleep(0.25)
    snap(
        "MCP: fl_import_midi('demo_violin_melody.mid')",
        "Piano Roll (F Harmonic Minor)",
        count=8,
        delay_s=0.18,
    )

    # 4. Layer drums on Step Sequencer
    srv.fl_ui_focus("channel_rack")
    srv.fl_step_sequencer(index=0, steps=[0, 4, 8, 12], mode="indices", length=16)
    srv.fl_step_sequencer(index=1, steps=[4, 12], mode="indices", length=16)
    srv.fl_step_sequencer(index=2, steps=[2, 6, 10, 14], mode="indices", length=16)
    snap("MCP: fl_step_sequencer() Kick / Clap / Hats", "Drums Layered", count=5, delay_s=0.18)

    # 5. Route & EQ Violin Bus in Mixer
    srv.fl_ui_focus("mixer", mixer_track=2)
    srv.fl_mixer_set(index=2, name="Violin Bus", volume=0.82)
    srv.fl_mixer_eq(index=2, band=0, gain=-0.35)
    srv.fl_mixer_eq(index=2, band=2, gain=0.25)
    snap("MCP: fl_mixer_set(2, 'Violin Bus') + fl_mixer_eq()", "Low -0.35 | High +0.25", count=6)

    # 6. Play the arrangement live!
    srv.fl_ui_focus("channel_rack")
    srv.fl_transport("play")
    snap(
        "MCP: fl_transport('play')  •  Violin + Beat Live",
        "PLAYING 140 BPM",
        playing=True,
        count=28,
        delay_s=0.12,
    )
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
