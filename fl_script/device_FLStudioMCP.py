# name=FLStudioMCP
# url=https://github.com/Arnau10a/fl-studio-mcp
"""FL Studio MIDI Controller Script for bidirectional MCP communication over SysEx."""

import json

import channels
import device
import general
import midi
import mixer
import patterns
import playlist
import plugins
import transport
import ui

SYSEX_HEADER = bytes([0xF0, 0x7D, 0x46, 0x4D])  # F0 7D 'F' 'M'
CHUNK_PAYLOAD_SIZE = 512  # hex chars per SysEx chunk
MAX_RX_BUFFERS = 32

_rx_buffers = {}


def _send_sysex_json(payload_dict):
    """Encode a dict as UTF-8 hex and send it in 7-bit safe SysEx chunks."""
    if not device.isAssigned():
        return
    raw_hex = json.dumps(payload_dict, ensure_ascii=True).encode("utf-8").hex()
    total = max(1, (len(raw_hex) + CHUNK_PAYLOAD_SIZE - 1) // CHUNK_PAYLOAD_SIZE)
    msg_id = int(payload_dict.get("id", 0)) & 0x3FFF
    id_hi = (msg_id >> 7) & 0x7F
    id_lo = msg_id & 0x7F

    for idx in range(total):
        chunk = raw_hex[idx * CHUNK_PAYLOAD_SIZE : (idx + 1) * CHUNK_PAYLOAD_SIZE]
        frame = (
            SYSEX_HEADER
            + bytes([id_hi, id_lo, idx & 0x7F, total & 0x7F])
            + chunk.encode("ascii")
            + b"\xf7"
        )
        device.midiOutSysex(frame)


def _cmd_ping(_params):
    return {
        "pong": True,
        "fl_version": ui.getVersion(),
        "bpm": mixer.getCurrentTempo(0) / 1000.0,
        "playing": bool(transport.isPlaying()),
        "recording": bool(transport.isRecording()),
        "loop_mode": "song" if transport.getLoopMode() == 1 else "pattern",
        "pattern": patterns.patternNumber(),
        "channel_count": channels.channelCount(),
        "mixer_track_count": mixer.trackCount(),
    }


def _cmd_transport(params):
    action = params.get("action", "")
    if action == "play":
        if not transport.isPlaying():
            transport.start()
    elif action == "stop":
        transport.stop()
    elif action == "pause":
        if transport.isPlaying():
            transport.start()
    elif action == "record":
        transport.record()
    elif action == "set_loop_mode":
        target = 1 if params.get("mode") == "song" else 0
        if transport.getLoopMode() != target:
            transport.setLoopMode()
    elif action == "set_bpm":
        bpm = float(params["bpm"])
        bpm = max(20.0, min(522.0, bpm))
        flags = midi.REC_Control | midi.REC_UpdateValue | midi.REC_UpdateControl
        general.processRECEvent(midi.REC_Tempo, int(round(bpm * 1000)), flags)
    elif action == "set_song_pos":
        pos = float(params.get("position", 0.0))
        transport.setSongPos(pos)
    else:
        raise ValueError(f"Unknown transport action: {action}")

    return {
        "playing": bool(transport.isPlaying()),
        "recording": bool(transport.isRecording()),
        "bpm": mixer.getCurrentTempo(0) / 1000.0,
        "loop_mode": "song" if transport.getLoopMode() == 1 else "pattern",
    }


def _parse_color(value):
    if isinstance(value, int):
        return value
    s = str(value).strip().lstrip("#")
    if len(s) != 6:
        raise ValueError(f"Expected #RRGGBB hex color or integer, got: {value}")
    r = int(s[0:2], 16)
    g = int(s[2:4], 16)
    b = int(s[4:6], 16)
    return (b << 16) | (g << 8) | r


def _format_color(bgr_int):
    v = int(bgr_int) & 0xFFFFFF
    r = v & 0xFF
    g = (v >> 8) & 0xFF
    b = (v >> 16) & 0xFF
    return f"#{r:02X}{g:02X}{b:02X}"


def _cmd_channels_list(_params):
    count = channels.channelCount()
    items = []
    for i in range(count):
        plugin_name = ""
        try:
            if plugins.isValid(i):
                plugin_name = plugins.getPluginName(i)
        except Exception:
            pass
        items.append(
            {
                "index": i,
                "name": channels.getChannelName(i),
                "plugin": plugin_name,
                "volume": round(channels.getChannelVolume(i), 4),
                "pan": round(channels.getChannelPan(i), 4),
                "muted": bool(channels.isChannelMuted(i)),
                "solo": bool(channels.isChannelSolo(i)),
                "mixer_track": channels.getTargetFxTrack(i),
                "selected": bool(channels.isChannelSelected(i)),
                "color": _format_color(channels.getChannelColor(i)),
            }
        )
    return {"channels": items}


def _cmd_channel_set(params):
    idx = int(params["index"])
    if "name" in params:
        channels.setChannelName(idx, str(params["name"]))
    if "volume" in params:
        channels.setChannelVolume(idx, max(0.0, min(1.0, float(params["volume"]))))
    if "pan" in params:
        channels.setChannelPan(idx, max(-1.0, min(1.0, float(params["pan"]))))
    if "color" in params:
        channels.setChannelColor(idx, _parse_color(params["color"]))
    if "muted" in params:
        want = bool(params["muted"])
        if bool(channels.isChannelMuted(idx)) != want:
            channels.muteChannel(idx)
    if "solo" in params:
        want = bool(params["solo"])
        if bool(channels.isChannelSolo(idx)) != want:
            channels.soloChannel(idx)
    if "mixer_track" in params:
        channels.setTargetFxTrack(idx, int(params["mixer_track"]))
    if "select" in params and params["select"]:
        channels.selectOneChannel(idx)
    return {
        "index": idx,
        "name": channels.getChannelName(idx),
        "volume": round(channels.getChannelVolume(idx), 4),
        "pan": round(channels.getChannelPan(idx), 4),
        "muted": bool(channels.isChannelMuted(idx)),
        "solo": bool(channels.isChannelSolo(idx)),
        "mixer_track": channels.getTargetFxTrack(idx),
        "color": _format_color(channels.getChannelColor(idx)),
    }


def _cmd_step_sequencer(params):
    idx = int(params["index"])
    steps = params.get("steps")
    clear_first = bool(params.get("clear_first", False))
    length = int(params.get("length", 16))

    if clear_first:
        for s in range(length):
            channels.setGridBit(idx, s, 0)

    if isinstance(steps, list):
        # Either list of 0/1 ints OR list of active step indices if mode=="indices"
        if params.get("mode") == "indices":
            active = set(int(x) for x in steps)
            for s in range(length):
                channels.setGridBit(idx, s, 1 if s in active else 0)
        else:
            for s, val in enumerate(steps):
                channels.setGridBit(idx, s, 1 if val else 0)

    current = [int(channels.getGridBit(idx, s)) for s in range(length)]
    return {"index": idx, "name": channels.getChannelName(idx), "steps": current}


def _cmd_step_sequencer_get(params):
    idx = int(params["index"])
    length = int(params.get("length", 16))
    current = [int(channels.getGridBit(idx, s)) for s in range(length)]
    return {"index": idx, "name": channels.getChannelName(idx), "steps": current}


def _cmd_channel_editor(params):
    idx = int(params["index"])
    state = 1 if params.get("open", True) else 0
    channels.showCSForm(idx, state)
    return {"index": idx, "name": channels.getChannelName(idx), "open": bool(state)}


def _cmd_patterns(params):
    action = params.get("action", "list")
    if action == "list":
        count = patterns.patternCount()
        items = []
        for p in range(1, count + 1):
            items.append(
                {
                    "index": p,
                    "name": patterns.getPatternName(p),
                    "length": patterns.getPatternLength(p),
                    "active": p == patterns.patternNumber(),
                }
            )
        return {"current": patterns.patternNumber(), "patterns": items}
    elif action == "select":
        p = int(params["index"])
        patterns.jumpToPattern(p)
        return {
            "current": patterns.patternNumber(),
            "name": patterns.getPatternName(patterns.patternNumber()),
        }
    elif action == "rename":
        p = int(params.get("index", patterns.patternNumber()))
        patterns.setPatternName(p, str(params["name"]))
        return {"index": p, "name": patterns.getPatternName(p)}
    elif action == "find_or_create":
        patterns.findFirstNextEmptyPat(midi.FFNEP_FindFirst | midi.FFNEP_DontPromptName)
        p = patterns.patternNumber()
        if "name" in params:
            patterns.setPatternName(p, str(params["name"]))
        return {"index": p, "name": patterns.getPatternName(p)}
    raise ValueError(f"Unknown pattern action: {action}")


def _safe_call(fn, *args, default=None):
    """Call an FL Studio API function and return default if unsupported or failing."""
    try:
        return fn(*args)
    except Exception:
        return default


def _read_mixer_track(t, include_fx=False):
    """Read mixer track state safely across FL Studio API versions."""
    sep_fn = getattr(mixer, "getTrackStereoSeparation", None) or getattr(
        mixer, "getTrackStereoSep", None
    )
    sep = _safe_call(sep_fn, t, default=0.0) if sep_fn else 0.0
    color_val = _safe_call(getattr(mixer, "getTrackColor", None), t, default=0)
    state = {
        "index": t,
        "name": _safe_call(getattr(mixer, "getTrackName", None), t, default=f"Insert {t}"),
        "volume": round(
            float(_safe_call(getattr(mixer, "getTrackVolume", None), t, default=0.8)), 4
        ),
        "pan": round(float(_safe_call(getattr(mixer, "getTrackPan", None), t, default=0.0)), 4),
        "stereo_separation": round(float(sep), 4),
        "muted": bool(_safe_call(getattr(mixer, "isTrackMuted", None), t, default=False)),
        "solo": bool(_safe_call(getattr(mixer, "isTrackSolo", None), t, default=False)),
        "armed": bool(_safe_call(getattr(mixer, "isTrackArmed", None), t, default=False)),
        "color": _format_color(int(color_val)),
    }
    if include_fx:
        fx = []
        for slot in range(10):
            try:
                if plugins.isValid(t, slot):
                    fx.append({"slot": slot, "name": plugins.getPluginName(t, slot)})
            except Exception:
                pass
        peak = _safe_call(getattr(mixer, "getTrackPeaks", None), t, 2, default=0.0)
        state["peak_lr"] = round(float(peak), 4)
        state["effects"] = fx
    return state


def _cmd_mixer_list(params):
    start = int(params.get("start", 0))
    end = min(mixer.trackCount(), int(params.get("end", 32)))
    tracks = [_read_mixer_track(t, include_fx=True) for t in range(start, end)]
    return {"tracks": tracks}


def _cmd_mixer_set(params):
    t = int(params["index"])
    if "name" in params:
        mixer.setTrackName(t, str(params["name"]))
    if "volume" in params:
        mixer.setTrackVolume(t, max(0.0, min(1.0, float(params["volume"]))))
    if "pan" in params:
        mixer.setTrackPan(t, max(-1.0, min(1.0, float(params["pan"]))))
    if "stereo_separation" in params:
        set_sep_fn = getattr(mixer, "setTrackStereoSeparation", None) or getattr(
            mixer, "setTrackStereoSep", None
        )
        if set_sep_fn:
            _safe_call(
                set_sep_fn,
                t,
                max(-1.0, min(1.0, float(params["stereo_separation"]))),
            )
    if "color" in params:
        mixer.setTrackColor(t, _parse_color(params["color"]))
    if "muted" in params:
        want = bool(params["muted"])
        if bool(mixer.isTrackMuted(t)) != want:
            mixer.muteTrack(t)
    if "solo" in params:
        want = bool(params["solo"])
        if bool(mixer.isTrackSolo(t)) != want:
            mixer.soloTrack(t)
    if "armed" in params:
        want = bool(params["armed"])
        if bool(mixer.isTrackArmed(t)) != want:
            mixer.armTrack(t)
    if "route_to" in params:
        dst = int(params["route_to"])
        val = 1 if params.get("route_active", True) else 0
        mixer.setRouteTo(t, dst, val)
    return _read_mixer_track(t, include_fx=False)


def _cmd_plugin_params(params):
    idx = int(params["index"])
    slot = int(params.get("slot", -1))
    if not plugins.isValid(idx, slot):
        raise ValueError(f"No valid plugin at index={idx}, slot={slot}")
    count = plugins.getParamCount(idx, slot)
    offset = int(params.get("offset", 0))
    limit = int(params.get("limit", 40))
    items = []
    for p in range(offset, min(count, offset + limit)):
        name = plugins.getParamName(p, idx, slot)
        if not name:
            continue
        items.append(
            {
                "param_index": p,
                "name": name,
                "value": round(plugins.getParamValue(p, idx, slot), 4),
                "display": plugins.getParamValueString(p, idx, slot),
            }
        )
    return {
        "plugin": plugins.getPluginName(idx, slot),
        "total_params": count,
        "params": items,
    }


def _cmd_plugin_set(params):
    idx = int(params["index"])
    slot = int(params.get("slot", -1))
    if not plugins.isValid(idx, slot):
        raise ValueError(f"No valid plugin at index={idx}, slot={slot}")

    action = params.get("action", "set_param")
    if action == "set_param":
        p_idx = int(params["param_index"])
        val = max(0.0, min(1.0, float(params["value"])))
        plugins.setParamValue(val, p_idx, idx, slot)
        return {
            "plugin": plugins.getPluginName(idx, slot),
            "param_index": p_idx,
            "name": plugins.getParamName(p_idx, idx, slot),
            "value": round(plugins.getParamValue(p_idx, idx, slot), 4),
            "display": plugins.getParamValueString(p_idx, idx, slot),
        }
    elif action == "next_preset":
        plugins.nextPreset(idx, slot)
        return {"plugin": plugins.getPluginName(idx, slot), "preset": "next"}
    elif action == "prev_preset":
        plugins.prevPreset(idx, slot)
        return {"plugin": plugins.getPluginName(idx, slot), "preset": "prev"}
    raise ValueError(f"Unknown plugin action: {action}")


def _cmd_midi_note(params):
    idx = int(params["index"])
    note = int(params["note"])
    vel = int(params.get("velocity", 100))
    channels.midiNoteOn(idx, note, vel)
    return {"index": idx, "note": note, "velocity": vel}


def _cmd_undo(params):
    direction = params.get("direction", "up")
    if direction == "up":
        general.undoUp()
    else:
        general.undoDown()
    return {"undo": direction}


def _cmd_mixer_eq(params):
    t = int(params["index"])
    band = int(params["band"])
    if band not in (0, 1, 2):
        raise ValueError("band must be 0 (Low), 1 (Mid), or 2 (High)")
    if "gain" in params:
        mixer.setEqGain(t, band, max(-1.0, min(1.0, float(params["gain"]))))
    if "frequency" in params:
        mixer.setEqFrequency(t, band, max(0.0, min(1.0, float(params["frequency"]))))
    if "bandwidth" in params:
        mixer.setEqBandwidth(t, band, max(0.0, min(1.0, float(params["bandwidth"]))))
    return {
        "index": t,
        "name": mixer.getTrackName(t),
        "band": band,
        "gain": round(mixer.getEqGain(t, band), 4),
        "frequency": round(mixer.getEqFrequency(t, band), 4),
        "bandwidth": round(mixer.getEqBandwidth(t, band), 4),
    }


def _cmd_playlist_list(params):
    start = max(1, int(params.get("start", 1)))
    end = min(playlist.trackCount(), int(params.get("end", 32)))
    tracks = []
    for t in range(start, end + 1):
        tracks.append(
            {
                "index": t,
                "name": playlist.getTrackName(t),
                "muted": bool(playlist.isTrackMuted(t)),
                "solo": bool(playlist.isTrackSolo(t)),
            }
        )
    return {"tracks": tracks}


def _cmd_playlist_set(params):
    t = int(params["index"])
    if "name" in params:
        playlist.setTrackName(t, str(params["name"]))
    if "muted" in params:
        want = bool(params["muted"])
        if bool(playlist.isTrackMuted(t)) != want:
            playlist.muteTrack(t)
    if "solo" in params:
        want = bool(params["solo"])
        if bool(playlist.isTrackSolo(t)) != want:
            playlist.soloTrack(t)
    return {
        "index": t,
        "name": playlist.getTrackName(t),
        "muted": bool(playlist.isTrackMuted(t)),
        "solo": bool(playlist.isTrackSolo(t)),
    }


def _cmd_ui_focus(params):
    win = params.get("window", "channel_rack")
    win_map = {
        "mixer": midi.widMixer,
        "channel_rack": midi.widChannelRack,
        "playlist": midi.widPlaylist,
        "piano_roll": midi.widPianoRoll,
        "browser": midi.widBrowser,
    }
    if win not in win_map:
        raise ValueError(f"Unknown window: {win}")
    wid = win_map[win]
    ui.showWindow(wid)
    ui.setFocused(wid)
    if win == "mixer" and "mixer_track" in params:
        mixer.setTrackNumber(int(params["mixer_track"]))
    return {"focused": win}


HANDLERS = {
    "ping": _cmd_ping,
    "transport": _cmd_transport,
    "channels_list": _cmd_channels_list,
    "channel_set": _cmd_channel_set,
    "step_sequencer": _cmd_step_sequencer,
    "step_sequencer_get": _cmd_step_sequencer_get,
    "channel_editor": _cmd_channel_editor,
    "patterns": _cmd_patterns,
    "mixer_list": _cmd_mixer_list,
    "mixer_set": _cmd_mixer_set,
    "mixer_eq": _cmd_mixer_eq,
    "playlist_list": _cmd_playlist_list,
    "playlist_set": _cmd_playlist_set,
    "ui_focus": _cmd_ui_focus,
    "plugin_params": _cmd_plugin_params,
    "plugin_set": _cmd_plugin_set,
    "midi_note": _cmd_midi_note,
    "undo": _cmd_undo,
}


def OnInit():
    print("FLStudioMCP controller initialized.")


def OnDeInit():
    print("FLStudioMCP controller deinitialized.")


def OnSysEx(event):
    data = event.sysex
    if not data or len(data) < 9 or not data.startswith(SYSEX_HEADER) or data[-1] != 0xF7:
        return

    event.handled = True
    msg_id = ((data[4] & 0x7F) << 7) | (data[5] & 0x7F)
    chunk_idx = data[6] & 0x7F
    total_chunks = data[7] & 0x7F
    chunk_hex = data[8:-1].decode("ascii", errors="ignore")

    if msg_id not in _rx_buffers and len(_rx_buffers) >= MAX_RX_BUFFERS:
        oldest_key = next(iter(_rx_buffers))
        _rx_buffers.pop(oldest_key, None)

    buf = _rx_buffers.setdefault(msg_id, {})
    buf[chunk_idx] = chunk_hex
    if len(buf) < total_chunks:
        return

    full_hex = "".join(buf[i] for i in range(total_chunks) if i in buf)
    _rx_buffers.pop(msg_id, None)

    req_id = msg_id
    try:
        req = json.loads(bytes.fromhex(full_hex).decode("utf-8"))
        req_id = req.get("id", msg_id)
        cmd = req.get("cmd", "")
        params = req.get("params", {})
        handler = HANDLERS.get(cmd)
        if handler is None:
            raise ValueError(f"Unknown command: {cmd}")
        result = handler(params)
        _send_sysex_json({"id": req_id, "ok": True, "result": result})
    except Exception as exc:
        _send_sysex_json({"id": req_id, "ok": False, "error": str(exc)})
