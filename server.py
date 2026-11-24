"""FL Studio Hard Techno MCP Server."""

import time
from pathlib import Path
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer

from bridge import FLBridge
from hard_techno import generate_hard_techno_kick_wav, generate_hard_techno_midi
from win_auto import (
    VK_APPS,
    VK_CONTROL,
    VK_DELETE,
    VK_DOWN,
    VK_ESCAPE,
    VK_F7,
    VK_F8,
    VK_MENU,
    VK_RETURN,
    focus_fl_studio,
    get_foreground_info,
    hotkey,
    search_samples,
    tap_vk,
    type_text,
)

mcp = MCPServer("fl-studio-mcp")
bridge = FLBridge()


@mcp.tool()
def fl_list_midi_ports() -> dict[str, list[str]]:
    """List available Windows MIDI input and output ports (useful to verify loopMIDI setup)."""
    return bridge.list_ports()


@mcp.tool()
def fl_ping() -> dict[str, Any]:
    """Check connection to FL Studio and get current BPM, transport state, pattern, and counts."""
    return bridge.call("ping")


@mcp.tool()
def fl_transport(
    action: Literal["play", "stop", "pause", "record", "set_loop_mode", "set_bpm", "set_song_pos"],
    bpm: float | None = None,
    mode: Literal["pattern", "song"] | None = None,
    position: float | None = None,
) -> dict[str, Any]:
    """Control FL Studio transport (play, stop, pause, record, loop mode, BPM, song position)."""
    params: dict[str, Any] = {"action": action}
    if bpm is not None:
        params["bpm"] = bpm
    if mode is not None:
        params["mode"] = mode
    if position is not None:
        params["position"] = position
    return bridge.call("transport", params)


@mcp.tool()
def fl_channels_list() -> dict[str, Any]:
    """List all Channel Rack channels with their plugin, volume, pan, mute/solo, and mixer track."""
    return bridge.call("channels_list")


@mcp.tool()
def fl_channel_set(
    index: int,
    name: str | None = None,
    volume: float | None = None,
    pan: float | None = None,
    muted: bool | None = None,
    solo: bool | None = None,
    mixer_track: int | None = None,
    select: bool = False,
) -> dict[str, Any]:
    """Update a Channel Rack channel's name, volume (0..1), pan (-1..1), mute, solo, or mixer routing."""
    params: dict[str, Any] = {"index": index, "select": select}
    if name is not None:
        params["name"] = name
    if volume is not None:
        params["volume"] = volume
    if pan is not None:
        params["pan"] = pan
    if muted is not None:
        params["muted"] = muted
    if solo is not None:
        params["solo"] = solo
    if mixer_track is not None:
        params["mixer_track"] = mixer_track
    return bridge.call("channel_set", params)


@mcp.tool()
def fl_step_sequencer(
    index: int,
    steps: list[int],
    mode: Literal["bits", "indices"] = "indices",
    length: int = 16,
    clear_first: bool = True,
) -> dict[str, Any]:
    """Program the Step Sequencer grid for a channel.

    With mode='indices', pass active step numbers (e.g. [0, 4, 8, 12] for a 4x4 Hard Techno kick).
    With mode='bits', pass a list of 0/1 values for each step.
    """
    return bridge.call(
        "step_sequencer",
        {
            "index": index,
            "steps": steps,
            "mode": mode,
            "length": length,
            "clear_first": clear_first,
        },
    )


@mcp.tool()
def fl_step_sequencer_get(index: int, length: int = 16) -> dict[str, Any]:
    """Read the current Step Sequencer grid for a channel without modifying it."""
    return bridge.call("step_sequencer_get", {"index": index, "length": length})


@mcp.tool()
def fl_channel_editor(index: int, open: bool = True) -> dict[str, Any]:
    """Show or hide a Channel's plugin/settings window in FL Studio."""
    return bridge.call("channel_editor", {"index": index, "open": open})


@mcp.tool()
def fl_patterns(
    action: Literal["list", "select", "rename", "find_or_create"],
    index: int | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """List, select, rename, or create patterns in FL Studio."""
    params: dict[str, Any] = {"action": action}
    if index is not None:
        params["index"] = index
    if name is not None:
        params["name"] = name
    return bridge.call("patterns", params)


@mcp.tool()
def fl_mixer_list(start: int = 0, end: int = 32) -> dict[str, Any]:
    """List Mixer tracks with peak levels, volumes, mute/solo state, and loaded FX plugins."""
    return bridge.call("mixer_list", {"start": start, "end": end})


@mcp.tool()
def fl_mixer_set(
    index: int,
    name: str | None = None,
    volume: float | None = None,
    pan: float | None = None,
    muted: bool | None = None,
    solo: bool | None = None,
    route_to: int | None = None,
    route_active: bool = True,
) -> dict[str, Any]:
    """Update a Mixer track's name, volume (0..1), pan (-1..1), mute, solo, or bus routing."""
    params: dict[str, Any] = {"index": index, "route_active": route_active}
    if name is not None:
        params["name"] = name
    if volume is not None:
        params["volume"] = volume
    if pan is not None:
        params["pan"] = pan
    if muted is not None:
        params["muted"] = muted
    if solo is not None:
        params["solo"] = solo
    if route_to is not None:
        params["route_to"] = route_to
    return bridge.call("mixer_set", params)


@mcp.tool()
def fl_plugin_params(
    index: int,
    slot: int = -1,
    offset: int = 0,
    limit: int = 40,
) -> dict[str, Any]:
    """List parameters of a Channel plugin (slot=-1) or Mixer FX plugin (index=mixer_track, slot=0..9)."""
    return bridge.call(
        "plugin_params",
        {"index": index, "slot": slot, "offset": offset, "limit": limit},
    )


@mcp.tool()
def fl_plugin_set(
    index: int,
    action: Literal["set_param", "next_preset", "prev_preset"] = "set_param",
    slot: int = -1,
    param_index: int | None = None,
    value: float | None = None,
) -> dict[str, Any]:
    """Set a plugin parameter (0.0..1.0) or switch presets on a Channel or Mixer FX plugin."""
    params: dict[str, Any] = {"index": index, "action": action, "slot": slot}
    if param_index is not None:
        params["param_index"] = param_index
    if value is not None:
        params["value"] = value
    return bridge.call("plugin_set", params)


@mcp.tool()
def fl_mixer_eq(
    index: int,
    band: Literal[0, 1, 2],
    gain: float | None = None,
    frequency: float | None = None,
    bandwidth: float | None = None,
) -> dict[str, Any]:
    """Adjust a Mixer track's built-in 3-band EQ (band: 0=Low, 1=Mid, 2=High; gain: -1..1, freq/bw: 0..1)."""
    params: dict[str, Any] = {"index": index, "band": band}
    if gain is not None:
        params["gain"] = gain
    if frequency is not None:
        params["frequency"] = frequency
    if bandwidth is not None:
        params["bandwidth"] = bandwidth
    return bridge.call("mixer_eq", params)


@mcp.tool()
def fl_playlist_list(start: int = 1, end: int = 32) -> dict[str, Any]:
    """List Playlist tracks (1-based index) with name, mute, and solo state."""
    return bridge.call("playlist_list", {"start": start, "end": end})


@mcp.tool()
def fl_playlist_set(
    index: int,
    name: str | None = None,
    muted: bool | None = None,
    solo: bool | None = None,
) -> dict[str, Any]:
    """Update a Playlist track's name, mute, or solo state (1-based index)."""
    params: dict[str, Any] = {"index": index}
    if name is not None:
        params["name"] = name
    if muted is not None:
        params["muted"] = muted
    if solo is not None:
        params["solo"] = solo
    return bridge.call("playlist_set", params)


@mcp.tool()
def fl_midi_note(
    index: int,
    note: int,
    velocity: int = 100,
    duration: float | None = None,
) -> dict[str, Any]:
    """Trigger a live MIDI note on a Channel (velocity=0 sends note-off; optional duration in seconds auto-releases)."""
    res = bridge.call("midi_note", {"index": index, "note": note, "velocity": velocity})
    if duration is not None and duration > 0 and velocity > 0:
        time.sleep(min(duration, 10.0))
        bridge.call("midi_note", {"index": index, "note": note, "velocity": 0})
        res["duration"] = duration
    return res


@mcp.tool()
def fl_undo(direction: Literal["up", "down"] = "up") -> dict[str, Any]:
    """Undo ('up') or redo ('down') the last action in FL Studio."""
    return bridge.call("undo", {"direction": direction})


@mcp.tool()
def fl_ui_focus(
    window: Literal["channel_rack", "mixer", "playlist", "piano_roll", "browser"],
    mixer_track: int | None = None,
) -> dict[str, Any]:
    """Focus a window in FL Studio (and optionally select a Mixer track)."""
    params: dict[str, Any] = {"window": window}
    if mixer_track is not None:
        params["mixer_track"] = mixer_track
    return bridge.call("ui_focus", params)


@mcp.tool()
def fl_add_plugin(
    name: str,
    target: Literal["channel", "mixer"] = "channel",
    mixer_track: int | None = None,
) -> dict[str, Any]:
    """Load a generator or effect plugin in FL Studio via the Plugin Picker (F8).

    target='channel' adds an instrument to the Channel Rack (e.g. 'Serum 2', 'Kepler Exo', 'Harmor').
    target='mixer' adds an FX plugin to the specified mixer_track (e.g. 'Fruity Reeverb 2').
    """
    before = bridge.call("ping")
    focus_params: dict[str, Any] = {"window": "mixer" if target == "mixer" else "channel_rack"}
    if target == "mixer" and mixer_track is not None:
        focus_params["mixer_track"] = mixer_track
    bridge.call("ui_focus", focus_params)
    focus_fl_studio()
    tap_vk(VK_F8)
    time.sleep(0.45)
    type_text(name)
    time.sleep(0.3)
    tap_vk(VK_RETURN)
    time.sleep(0.6)
    after = bridge.call("ping")
    return {
        "requested_plugin": name,
        "target": target,
        "channel_count_before": before.get("channel_count"),
        "channel_count_after": after.get("channel_count"),
    }


@mcp.tool()
def fl_search_samples(
    query: str,
    category: str | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    """Search FL Studio's Packs library (Drums, Loops, Risers, etc.) and output/ for audio samples."""
    matches = search_samples(query=query, category=category, limit=limit)
    return {"query": query, "count": len(matches), "samples": matches}


@mcp.tool()
def fl_load_sample(
    query: str,
    category: str | None = None,
    replace_selected: bool = False,
) -> dict[str, Any]:
    """Find a sample in FL Studio's Packs library and load it into the Channel Rack via the Browser."""
    matches = search_samples(query=query, category=category, limit=1)
    sample_name = matches[0]["name"] if matches else query

    before = bridge.call("ping")
    bridge.call("ui_focus", {"window": "browser"})
    focus_fl_studio()
    # Ctrl+F opens Browser Find in FL Studio
    hotkey(VK_CONTROL, ord("F"))
    time.sleep(0.25)
    type_text(sample_name)
    time.sleep(0.2)
    tap_vk(VK_RETURN)
    time.sleep(0.35)
    # Open context menu on the found Browser item
    tap_vk(VK_APPS)
    time.sleep(0.25)
    if not replace_selected:
        # 1st item is "Open in new channel" / 2nd is "Send to selected channel"
        tap_vk(VK_DOWN)
        time.sleep(0.08)
    else:
        tap_vk(VK_DOWN)
        time.sleep(0.08)
        tap_vk(VK_DOWN)
        time.sleep(0.08)
    tap_vk(VK_RETURN)
    time.sleep(0.4)
    after = bridge.call("ping")
    return {
        "sample": matches[0] if matches else {"name": sample_name},
        "channel_count_before": before.get("channel_count"),
        "channel_count_after": after.get("channel_count"),
    }


@mcp.tool()
def fl_import_midi(
    index: int,
    midi_path: str,
) -> dict[str, Any]:
    """Import a .mid file into a Channel's Piano Roll using FL Studio's Piano Roll Import MIDI (Ctrl+M)."""
    resolved = Path(midi_path)
    if not resolved.is_absolute():
        resolved = Path(__file__).resolve().parent / resolved
    if not resolved.exists():
        raise FileNotFoundError(f"MIDI file not found: {resolved}")

    bridge.call("channel_set", {"index": index, "select": True})
    bridge.call("ui_focus", {"window": "channel_rack"})
    focus_fl_studio()
    time.sleep(0.15)
    # F7 opens/switches Piano Roll to the currently selected channel
    tap_vk(VK_F7)
    time.sleep(0.25)
    hotkey(VK_CONTROL, ord("M"))
    time.sleep(0.6)
    type_text(str(resolved))
    time.sleep(0.25)
    tap_vk(VK_RETURN)
    time.sleep(0.7)
    tap_vk(VK_RETURN)
    time.sleep(0.3)
    return {"index": index, "midi_file": str(resolved), "imported": True}


@mcp.tool()
def fl_new_project(discard_unsaved: bool = True) -> dict[str, Any]:
    """Start a new project in FL Studio (Ctrl+N), optionally dismissing the unsaved-changes prompt."""
    main_hwnd = focus_fl_studio()
    hotkey(VK_CONTROL, ord("N"))
    time.sleep(0.5)
    if discard_unsaved:
        fg_hwnd, _title, cls = get_foreground_info()
        if fg_hwnd and fg_hwnd != main_hwnd and cls in ("TMessageForm", "#32770"):
            tap_vk(ord("N"))
            time.sleep(0.5)
            fg_hwnd2, _title2, cls2 = get_foreground_info()
            if fg_hwnd2 and fg_hwnd2 != main_hwnd and cls2 == "#32770":
                tap_vk(VK_ESCAPE)
                time.sleep(0.3)
    info = bridge.call("ping")
    return {"new_project": True, "ping": info}


@mcp.tool()
def fl_delete_channel(index: int) -> dict[str, Any]:
    """Delete a single Channel Rack channel by index using Alt+Delete."""
    before = bridge.call("ping")
    bridge.call("channel_set", {"index": index, "select": True})
    bridge.call("ui_focus", {"window": "channel_rack"})
    main_hwnd = focus_fl_studio()
    hotkey(VK_MENU, VK_DELETE)
    time.sleep(0.45)
    fg_hwnd, _title, cls = get_foreground_info()
    if fg_hwnd and fg_hwnd != main_hwnd and cls in ("TMessageForm", "#32770"):
        tap_vk(VK_RETURN)
        time.sleep(0.4)
    after = bridge.call("ping")
    return {
        "deleted_index": index,
        "channel_count_before": before.get("channel_count"),
        "channel_count_after": after.get("channel_count"),
    }


@mcp.tool()
def ht_generate_midi(
    style: Literal["rumble_bass", "acid_303", "rave_stab", "schranz_perc"],
    bpm: float = 150.0,
    root_note: str = "F",
    scale: Literal["phrygian", "minor", "harmonic_minor", "locrian"] = "phrygian",
    bars: int = 4,
    seed: int | None = None,
    filename: str | None = None,
) -> dict[str, str]:
    """Generate a Hard Techno MIDI file (.mid) ready to drop into FL Studio's Piano Roll."""
    path = generate_hard_techno_midi(
        style=style,
        bpm=bpm,
        root_note=root_note,
        scale=scale,
        bars=bars,
        seed=seed,
        filename=filename,
    )
    return {"midi_file": str(path), "style": style, "bpm": str(bpm)}


@mcp.tool()
def ht_generate_kick_sample(
    bpm: float = 150.0,
    drive: float = 4.5,
    sub_freq: float = 48.0,
    include_rumble: bool = True,
    filename: str | None = None,
) -> dict[str, str]:
    """Synthesize a 1-bar distorted Hard Techno kick (+ optional sidechained rumble) WAV synced to BPM."""
    path = generate_hard_techno_kick_wav(
        bpm=bpm,
        drive=drive,
        sub_freq=sub_freq,
        include_rumble=include_rumble,
        filename=filename,
    )
    return {"wav_file": str(path), "bpm": str(bpm)}


def main() -> None:
    """Run the FL Studio MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
