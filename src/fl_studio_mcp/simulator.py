"""In-memory FL Studio MIDI Scripting simulator for E2E protocol tests and FL_MCP_MOCK=1."""

from __future__ import annotations

import importlib.util
import sys
import threading
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import mido

from fl_studio_mcp.paths import get_fl_script_source

_SCRIPT_LOAD_LOCK = threading.Lock()


@dataclass
class SimPlugin:
    name: str
    params: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {"name": "Cutoff", "value": 0.65},
            {"name": "Resonance", "value": 0.35},
            {"name": "Drive", "value": 0.5},
            {"name": "Master Level", "value": 0.8},
        ]
    )
    preset_idx: int = 0


@dataclass
class SimChannel:
    name: str
    plugin: SimPlugin | None = None
    volume: float = 0.7812
    pan: float = 0.0
    muted: bool = False
    solo: bool = False
    mixer_track: int = 1
    selected: bool = False
    editor_open: bool = False
    color: int = 0x5C6470
    grid: dict[int, int] = field(default_factory=dict)
    piano_roll_files: list[str] = field(default_factory=list)
    piano_roll_notes: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SimMixerTrack:
    name: str
    volume: float = 0.8
    pan: float = 0.0
    stereo_separation: float = 0.0
    muted: bool = False
    solo: bool = False
    armed: bool = False
    color: int = 0x5C6470
    peak_lr: float = 0.0
    routes: set[int] = field(default_factory=lambda: {0})
    fx_slots: dict[int, SimPlugin] = field(default_factory=dict)
    eq: dict[int, dict[str, float]] = field(
        default_factory=lambda: {
            0: {"gain": 0.0, "freq": 0.25, "bw": 0.5},
            1: {"gain": 0.0, "freq": 0.5, "bw": 0.5},
            2: {"gain": 0.0, "freq": 0.8, "bw": 0.5},
        }
    )


@dataclass
class SimPattern:
    name: str
    length: int = 16


@dataclass
class SimPlaylistTrack:
    name: str
    muted: bool = False
    solo: bool = False


class _SimSysExEvent:
    def __init__(self, sysex: bytes) -> None:
        self.sysex = sysex
        self.handled = False


class MockMidiOutPort:
    def __init__(self, runtime: MockFLRuntime) -> None:
        self._runtime = runtime
        self.closed = False

    def send(self, message: mido.Message) -> None:
        if message.type != "sysex":
            return
        frame = b"\xf0" + bytes(message.data) + b"\xf7"
        event = _SimSysExEvent(frame)
        self._runtime.script_module.OnSysEx(event)

    def close(self) -> None:
        self.closed = True


class MockMidiInPort:
    def __init__(self, queue: deque[mido.Message]) -> None:
        self._queue = queue
        self.closed = False

    def iter_pending(self) -> list[mido.Message]:
        items: list[mido.Message] = []
        while self._queue:
            items.append(self._queue.popleft())
        return items

    def close(self) -> None:
        self.closed = True


class MockFLRuntime:
    """In-memory FL Studio session state wired directly into device_FLStudioMCP.py."""

    def __init__(self, script_path: Path | None = None) -> None:
        self.bpm: float = 150.0
        self.playing: bool = False
        self.recording: bool = False
        self.loop_mode: int = 0
        self.song_pos: float = 0.0
        self.current_pattern: int = 1
        self.selected_mixer_track: int = 0
        self.focused_window: int = 1
        self.undo_pos: int = 0
        self.note_events: list[tuple[int, int, int]] = []
        self._rx_queue: deque[mido.Message] = deque()

        self.patterns: list[SimPattern] = [SimPattern(name=f"Pattern {i + 1}") for i in range(4)]
        self.channels: list[SimChannel] = [
            SimChannel(
                name="Kick",
                plugin=SimPlugin(name="Sampler"),
                mixer_track=1,
                selected=True,
            ),
            SimChannel(name="Clap", plugin=SimPlugin(name="Sampler"), mixer_track=2),
            SimChannel(name="Hat", plugin=SimPlugin(name="Sampler"), mixer_track=3),
            SimChannel(name="Acid 303", plugin=SimPlugin(name="3x Osc"), mixer_track=4),
        ]
        self.mixer_tracks: list[SimMixerTrack] = [
            SimMixerTrack(
                name="Master" if i == 0 else f"Insert {i}",
                routes=set() if i == 0 else {0},
                peak_lr=0.18 if i in (0, 1) else 0.0,
                fx_slots=({0: SimPlugin(name="Fruity Limiter")} if i == 0 else {}),
            )
            for i in range(64)
        ]
        self.playlist_tracks: list[SimPlaylistTrack] = [
            SimPlaylistTrack(name=f"Track {i}") for i in range(1, 65)
        ]

        self.script_module = self._load_device_script(script_path or get_fl_script_source())
        self.script_module.OnInit()

    def create_ports(self) -> tuple[MockMidiOutPort, MockMidiInPort]:
        return MockMidiOutPort(self), MockMidiInPort(self._rx_queue)

    def _build_fl_modules(self) -> dict[str, ModuleType]:
        rt = self

        midi_mod = ModuleType("midi")
        midi_mod.__dict__.update(
            {
                "REC_Control": 1,
                "REC_UpdateValue": 2,
                "REC_UpdateControl": 4,
                "REC_Tempo": 100,
                "FFNEP_FindFirst": 1,
                "FFNEP_DontPromptName": 2,
                "widMixer": 0,
                "widChannelRack": 1,
                "widPlaylist": 2,
                "widPianoRoll": 3,
                "widBrowser": 4,
            }
        )

        transport_mod = ModuleType("transport")
        transport_mod.__dict__.update(
            {
                "isPlaying": lambda: 1 if rt.playing else 0,
                "isRecording": lambda: 1 if rt.recording else 0,
                "getLoopMode": lambda: rt.loop_mode,
                "start": lambda: setattr(rt, "playing", not rt.playing),
                "stop": lambda: setattr(rt, "playing", False),
                "record": lambda: setattr(rt, "recording", not rt.recording),
                "setLoopMode": lambda: setattr(rt, "loop_mode", 0 if rt.loop_mode == 1 else 1),
                "setSongPos": lambda pos: setattr(rt, "song_pos", float(pos)),
            }
        )

        def _get_plugin(idx: int, slot: int = -1) -> SimPlugin | None:
            if slot == -1:
                if 0 <= idx < len(rt.channels):
                    return rt.channels[idx].plugin
                return None
            if 0 <= idx < len(rt.mixer_tracks):
                return rt.mixer_tracks[idx].fx_slots.get(slot)
            return None

        def _require_plugin(idx: int, slot: int = -1) -> SimPlugin:
            plug = _get_plugin(idx, slot)
            if plug is None:
                raise ValueError(f"No plugin at index={idx}, slot={slot}")
            return plug

        def _get_plugin_name(idx: int, slot: int = -1) -> str:
            plug = _get_plugin(idx, slot)
            return plug.name if plug is not None else ""

        def _get_param_count(idx: int, slot: int = -1) -> int:
            plug = _get_plugin(idx, slot)
            return len(plug.params) if plug is not None else 0

        def _set_param_value(val: float, p: int, idx: int, slot: int = -1) -> None:
            _require_plugin(idx, slot).params[p]["value"] = float(val)

        def _next_preset(idx: int, slot: int = -1) -> None:
            plug = _require_plugin(idx, slot)
            plug.preset_idx += 1

        def _prev_preset(idx: int, slot: int = -1) -> None:
            plug = _require_plugin(idx, slot)
            plug.preset_idx = max(0, plug.preset_idx - 1)

        plugins_mod = ModuleType("plugins")
        plugins_mod.__dict__.update(
            {
                "isValid": lambda idx, slot=-1: _get_plugin(idx, slot) is not None,
                "getPluginName": _get_plugin_name,
                "getParamCount": _get_param_count,
                "getParamName": lambda p, idx, slot=-1: str(
                    _require_plugin(idx, slot).params[p]["name"]
                ),
                "getParamValue": lambda p, idx, slot=-1: float(
                    _require_plugin(idx, slot).params[p]["value"]
                ),
                "setParamValue": _set_param_value,
                "getParamValueString": lambda p, idx, slot=-1: (
                    f"{round(float(_require_plugin(idx, slot).params[p]['value']) * 100, 1)}%"
                ),
                "nextPreset": _next_preset,
                "prevPreset": _prev_preset,
            }
        )

        def _select_one_channel(idx: int) -> None:
            for i, ch in enumerate(rt.channels):
                ch.selected = i == idx

        channels_mod = ModuleType("channels")
        channels_mod.__dict__.update(
            {
                "channelCount": lambda: len(rt.channels),
                "getChannelName": lambda i: rt.channels[i].name,
                "setChannelName": lambda i, name: setattr(rt.channels[i], "name", name),
                "getChannelVolume": lambda i: rt.channels[i].volume,
                "setChannelVolume": lambda i, v: setattr(rt.channels[i], "volume", v),
                "getChannelPan": lambda i: rt.channels[i].pan,
                "setChannelPan": lambda i, p: setattr(rt.channels[i], "pan", p),
                "getChannelColor": lambda i: rt.channels[i].color,
                "setChannelColor": lambda i, c: setattr(rt.channels[i], "color", int(c)),
                "isChannelMuted": lambda i: rt.channels[i].muted,
                "muteChannel": lambda i: setattr(rt.channels[i], "muted", not rt.channels[i].muted),
                "isChannelSolo": lambda i: rt.channels[i].solo,
                "soloChannel": lambda i: setattr(rt.channels[i], "solo", not rt.channels[i].solo),
                "getTargetFxTrack": lambda i: rt.channels[i].mixer_track,
                "setTargetFxTrack": lambda i, t: setattr(rt.channels[i], "mixer_track", t),
                "isChannelSelected": lambda i: rt.channels[i].selected,
                "selectOneChannel": _select_one_channel,
                "setGridBit": lambda i, s, v: rt.channels[i].grid.__setitem__(s, int(v)),
                "getGridBit": lambda i, s: rt.channels[i].grid.get(s, 0),
                "showCSForm": lambda i, state: setattr(rt.channels[i], "editor_open", bool(state)),
                "midiNoteOn": lambda i, note, vel: rt.note_events.append((i, note, vel)),
            }
        )

        def _find_or_create_pat(_flags: int) -> None:
            rt.patterns.append(SimPattern(name=f"Pattern {len(rt.patterns) + 1}"))
            rt.current_pattern = len(rt.patterns)

        patterns_mod = ModuleType("patterns")
        patterns_mod.__dict__.update(
            {
                "patternNumber": lambda: rt.current_pattern,
                "patternCount": lambda: len(rt.patterns),
                "getPatternName": lambda p: rt.patterns[p - 1].name,
                "setPatternName": lambda p, name: setattr(rt.patterns[p - 1], "name", name),
                "getPatternLength": lambda p: rt.patterns[p - 1].length,
                "jumpToPattern": lambda p: setattr(
                    rt, "current_pattern", max(1, min(len(rt.patterns), p))
                ),
                "findFirstNextEmptyPat": _find_or_create_pat,
            }
        )

        def _set_route_to(src: int, dst: int, val: int) -> None:
            if val:
                rt.mixer_tracks[src].routes.add(dst)
            else:
                rt.mixer_tracks[src].routes.discard(dst)

        mixer_mod = ModuleType("mixer")
        mixer_mod.__dict__.update(
            {
                "getCurrentTempo": lambda _mode=0: int(round(rt.bpm * 1000)),
                "trackCount": lambda: len(rt.mixer_tracks),
                "getTrackName": lambda t: rt.mixer_tracks[t].name,
                "setTrackName": lambda t, name: setattr(rt.mixer_tracks[t], "name", name),
                "getTrackVolume": lambda t: rt.mixer_tracks[t].volume,
                "setTrackVolume": lambda t, v: setattr(rt.mixer_tracks[t], "volume", v),
                "getTrackPan": lambda t: rt.mixer_tracks[t].pan,
                "setTrackPan": lambda t, p: setattr(rt.mixer_tracks[t], "pan", p),
                "getTrackStereoSeparation": lambda t: rt.mixer_tracks[t].stereo_separation,
                "setTrackStereoSeparation": lambda t, s: setattr(
                    rt.mixer_tracks[t], "stereo_separation", s
                ),
                "getTrackColor": lambda t: rt.mixer_tracks[t].color,
                "setTrackColor": lambda t, c: setattr(rt.mixer_tracks[t], "color", int(c)),
                "isTrackMuted": lambda t: rt.mixer_tracks[t].muted,
                "muteTrack": lambda t: setattr(
                    rt.mixer_tracks[t], "muted", not rt.mixer_tracks[t].muted
                ),
                "isTrackSolo": lambda t: rt.mixer_tracks[t].solo,
                "soloTrack": lambda t: setattr(
                    rt.mixer_tracks[t], "solo", not rt.mixer_tracks[t].solo
                ),
                "isTrackArmed": lambda t: rt.mixer_tracks[t].armed,
                "armTrack": lambda t: setattr(
                    rt.mixer_tracks[t], "armed", not rt.mixer_tracks[t].armed
                ),
                "getTrackPeaks": lambda t, _mode=2: rt.mixer_tracks[t].peak_lr,
                "setRouteTo": _set_route_to,
                "setEqGain": lambda t, b, v: rt.mixer_tracks[t].eq[b].__setitem__("gain", v),
                "getEqGain": lambda t, b: rt.mixer_tracks[t].eq[b]["gain"],
                "setEqFrequency": lambda t, b, v: rt.mixer_tracks[t].eq[b].__setitem__("freq", v),
                "getEqFrequency": lambda t, b: rt.mixer_tracks[t].eq[b]["freq"],
                "setEqBandwidth": lambda t, b, v: rt.mixer_tracks[t].eq[b].__setitem__("bw", v),
                "getEqBandwidth": lambda t, b: rt.mixer_tracks[t].eq[b]["bw"],
                "setTrackNumber": lambda t: setattr(rt, "selected_mixer_track", t),
            }
        )

        playlist_mod = ModuleType("playlist")
        playlist_mod.__dict__.update(
            {
                "trackCount": lambda: len(rt.playlist_tracks),
                "getTrackName": lambda t: rt.playlist_tracks[t - 1].name,
                "setTrackName": lambda t, name: setattr(rt.playlist_tracks[t - 1], "name", name),
                "isTrackMuted": lambda t: rt.playlist_tracks[t - 1].muted,
                "muteTrack": lambda t: setattr(
                    rt.playlist_tracks[t - 1], "muted", not rt.playlist_tracks[t - 1].muted
                ),
                "isTrackSolo": lambda t: rt.playlist_tracks[t - 1].solo,
                "soloTrack": lambda t: setattr(
                    rt.playlist_tracks[t - 1], "solo", not rt.playlist_tracks[t - 1].solo
                ),
            }
        )

        ui_mod = ModuleType("ui")
        ui_mod.__dict__.update(
            {
                "getVersion": lambda: "24.2.0 (Mock)",
                "showWindow": lambda wid: setattr(rt, "focused_window", wid),
                "setFocused": lambda wid: setattr(rt, "focused_window", wid),
            }
        )

        def _process_rec(event_id: int, value: int, _flags: int) -> None:
            if event_id == 100:
                rt.bpm = value / 1000.0

        general_mod = ModuleType("general")
        general_mod.__dict__.update(
            {
                "processRECEvent": _process_rec,
                "undoUp": lambda: setattr(rt, "undo_pos", rt.undo_pos - 1),
                "undoDown": lambda: setattr(rt, "undo_pos", rt.undo_pos + 1),
            }
        )

        def _midi_out_sysex(frame: bytes) -> None:
            if len(frame) >= 2 and frame[0] == 0xF0 and frame[-1] == 0xF7:
                rt._rx_queue.append(mido.Message("sysex", data=list(frame[1:-1])))

        device_mod = ModuleType("device")
        device_mod.__dict__.update(
            {
                "isAssigned": lambda: True,
                "midiOutSysex": _midi_out_sysex,
            }
        )

        return {
            "transport": transport_mod,
            "mixer": mixer_mod,
            "channels": channels_mod,
            "patterns": patterns_mod,
            "playlist": playlist_mod,
            "plugins": plugins_mod,
            "ui": ui_mod,
            "general": general_mod,
            "device": device_mod,
            "midi": midi_mod,
        }

    def _load_device_script(self, script_path: Path) -> ModuleType:
        if not script_path.exists():
            raise FileNotFoundError(f"FL Studio controller script not found: {script_path}")
        fl_mods = self._build_fl_modules()
        spec = importlib.util.spec_from_file_location("device_FLStudioMCP_sim", script_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load controller script from {script_path}")
        module = importlib.util.module_from_spec(spec)
        with _SCRIPT_LOAD_LOCK:
            previous = {name: sys.modules.get(name) for name in fl_mods}
            sys.modules.update(fl_mods)
            try:
                spec.loader.exec_module(module)
            finally:
                for name, prev in previous.items():
                    if prev is None:
                        sys.modules.pop(name, None)
                    else:
                        sys.modules[name] = prev
        return module

    # --- Simulated GUI-level operations (when FL_MCP_MOCK=1) ---

    def gui_add_plugin(
        self, name: str, target: str = "channel", mixer_track: int | None = None
    ) -> dict[str, Any]:
        before = len(self.channels)
        if target == "channel":
            self.channels.append(SimChannel(name=name, plugin=SimPlugin(name=name), mixer_track=1))
        else:
            t_idx = mixer_track if mixer_track is not None else self.selected_mixer_track
            track = self.mixer_tracks[t_idx]
            next_slot = next((s for s in range(10) if s not in track.fx_slots), 9)
            track.fx_slots[next_slot] = SimPlugin(name=name)
        return {
            "requested_plugin": name,
            "target": target,
            "channel_count_before": before,
            "channel_count_after": len(self.channels),
            "mock": True,
        }

    def gui_load_sample(
        self, sample: dict[str, str], replace_selected: bool = False
    ) -> dict[str, Any]:
        before = len(self.channels)
        name = sample.get("name", "Sample")
        if replace_selected:
            selected = next((c for c in self.channels if c.selected), self.channels[0])
            selected.name = name
        else:
            self.channels.append(
                SimChannel(name=name, plugin=SimPlugin(name="Sampler"), mixer_track=1)
            )
        return {
            "sample": sample,
            "channel_count_before": before,
            "channel_count_after": len(self.channels),
            "mock": True,
        }

    def gui_import_midi(self, index: int, resolved: Path) -> dict[str, Any]:
        self.channels[index].piano_roll_files.append(str(resolved))
        return {"index": index, "midi_file": str(resolved), "imported": True, "mock": True}

    def gui_new_project(self) -> dict[str, Any]:
        self.bpm = 140.0
        self.playing = False
        self.recording = False
        self.channels = [SimChannel(name="Kick", plugin=SimPlugin(name="Sampler"), selected=True)]
        self.patterns = [SimPattern(name="Pattern 1")]
        self.current_pattern = 1
        return {
            "new_project": True,
            "mock": True,
            "ping": SimpleNamespace(bpm=self.bpm, channel_count=len(self.channels)).__dict__,
        }

    def gui_delete_channel(self, index: int) -> dict[str, Any]:
        before = len(self.channels)
        if not (0 <= index < before):
            raise IndexError(f"Channel index out of range: {index}")
        self.channels.pop(index)
        if self.channels and not any(c.selected for c in self.channels):
            self.channels[0].selected = True
        return {
            "deleted_index": index,
            "channel_count_before": before,
            "channel_count_after": len(self.channels),
            "mock": True,
        }

    def gui_piano_roll_notes(
        self,
        index: int,
        notes: list[dict[str, Any]],
        clear_first: bool = False,
    ) -> dict[str, Any]:
        ch = self.channels[index]
        if clear_first:
            ch.piano_roll_notes.clear()
        for n in notes:
            ch.piano_roll_notes.append(
                {
                    "number": int(n["number"]),
                    "time": int(n["time"]),
                    "length": int(n.get("length", 48)),
                    "velocity": float(n.get("velocity", 0.8)),
                    "pan": float(n.get("pan", 0.5)),
                    "color": int(n.get("color", 0)),
                    "slide": bool(n.get("slide", False)),
                    "porta": bool(n.get("porta", False)),
                }
            )
        return {
            "index": index,
            "added": len(notes),
            "total_notes": len(ch.piano_roll_notes),
            "mock": True,
        }

    def gui_piano_roll_state(self, index: int) -> dict[str, Any]:
        ch = self.channels[index]
        return {
            "index": index,
            "note_count": len(ch.piano_roll_notes),
            "notes": list(ch.piano_roll_notes),
            "mock": True,
        }

    def gui_piano_roll_clear(self, index: int) -> dict[str, Any]:
        ch = self.channels[index]
        removed = len(ch.piano_roll_notes)
        ch.piano_roll_notes.clear()
        return {"index": index, "cleared": removed, "mock": True}
