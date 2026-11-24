"""Hard Techno MIDI & WAV sample generators for remix workflows."""

from pathlib import Path
import random
import wave

import mido
import numpy as np

BASE_DIR = Path(__file__).resolve().parent
MIDI_OUT_DIR = BASE_DIR / "output" / "midi"
SAMPLE_OUT_DIR = BASE_DIR / "output" / "samples"

NOTE_MAP = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
    "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}

SCALES = {
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "harmonic_minor": [0, 2, 3, 5, 7, 8, 11],
    "locrian": [0, 1, 3, 5, 6, 8, 10],
}


def _parse_root(root_note: str, octave: int) -> int:
    clean = root_note.strip()
    if len(clean) >= 2 and clean[1] in ("#", "b"):
        pitch = NOTE_MAP[clean[:2].capitalize()]
    else:
        pitch = NOTE_MAP[clean[0].upper()]
    return (octave + 1) * 12 + pitch


def generate_hard_techno_midi(
    style: str,
    bpm: float = 150.0,
    root_note: str = "F",
    scale: str = "phrygian",
    bars: int = 4,
    seed: int | None = None,
    filename: str | None = None,
) -> Path:
    """Generate a Hard Techno MIDI file ready to drop into FL Studio's Piano Roll."""
    MIDI_OUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)

    intervals = SCALES.get(scale.lower(), SCALES["phrygian"])
    tpb = 480  # ticks per quarter note
    step_ticks = tpb // 4  # 16th note = 120 ticks

    mid = mido.MidiFile(ticks_per_beat=tpb)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))

    # Build a timeline of (tick, type, note, velocity) events
    events: list[tuple[int, str, int, int]] = []
    total_steps = bars * 16

    if style == "rumble_bass":
        base = _parse_root(root_note, 1)
        for s in range(total_steps):
            if s % 4 == 0:
                continue  # leave space on the downbeat for the kick
            t = s * step_ticks
            note = base if s % 4 != 2 else base + intervals[1]
            vel = 115 if s % 4 == 2 else 82
            dur = int(step_ticks * 0.85)
            events.append((t, "note_on", note, vel))
            events.append((t + dur, "note_off", note, 0))

    elif style == "acid_303":
        base = _parse_root(root_note, 2)
        motif = [0, 0, 1, 0, 4, 3, 1, 0, 0, 1, 0, 5, 4, 1, 3, 1]
        for s in range(total_steps):
            if rng.random() < 0.15 and s % 4 != 0:
                continue
            deg = motif[s % len(motif)]
            octave_jump = 12 if (s % 8 == 6 or rng.random() < 0.2) else 0
            note = base + intervals[deg % len(intervals)] + octave_jump
            accent = (s % 4 == 2) or (rng.random() < 0.25)
            slide = rng.random() < 0.28
            vel = 124 if accent else 86
            dur = int(step_ticks * (1.25 if slide else 0.7))
            t = s * step_ticks
            events.append((t, "note_on", note, vel))
            events.append((t + dur, "note_off", note, 0))

    elif style == "rave_stab":
        base = _parse_root(root_note, 3)
        stab_steps = [0, 3, 6, 10, 12, 14]
        for bar in range(bars):
            for s_in_bar in stab_steps:
                t = (bar * 16 + s_in_bar) * step_ticks
                shift = intervals[1] if (bar % 2 == 1 and s_in_bar >= 12) else 0
                chord = [base + shift, base + shift + 3, base + shift + 7]
                dur = int(step_ticks * 1.4)
                for n in chord:
                    events.append((t, "note_on", n, 112))
                    events.append((t + dur, "note_off", n, 0))

    elif style == "schranz_perc":
        # C3=36 kick trigger, F#3=42 closed hat, A#3=46 open hat, D#3=39 clap
        for s in range(total_steps):
            t = s * step_ticks
            if s % 4 == 0:
                events.append((t, "note_on", 36, 127))
                events.append((t + 90, "note_off", 36, 0))
            if s % 4 == 2:
                events.append((t, "note_on", 46, 110))
                events.append((t + 100, "note_off", 46, 0))
            else:
                events.append((t, "note_on", 42, 75 if s % 2 == 1 else 55))
                events.append((t + 60, "note_off", 42, 0))
            if s % 8 == 4:
                events.append((t, "note_on", 39, 118))
                events.append((t + 90, "note_off", 39, 0))
    else:
        raise ValueError(f"Unknown style '{style}'. Choose: rumble_bass, acid_303, rave_stab, schranz_perc")

    events.sort(key=lambda e: (e[0], 0 if e[1] == "note_off" else 1))
    last_tick = 0
    for tick, kind, note, vel in events:
        delta = max(0, tick - last_tick)
        track.append(mido.Message(kind, note=note, velocity=vel, time=delta))
        last_tick = tick

    out_name = filename or f"{style}_{int(bpm)}bpm_{root_note}_{scale}.mid"
    out_path = MIDI_OUT_DIR / out_name
    mid.save(out_path)
    return out_path


def generate_hard_techno_kick_wav(
    bpm: float = 150.0,
    drive: float = 4.5,
    sub_freq: float = 48.0,
    include_rumble: bool = True,
    filename: str | None = None,
) -> Path:
    """Synthesize a 1-bar distorted Hard Techno kick (+ optional rumble) WAV synced to BPM."""
    SAMPLE_OUT_DIR.mkdir(parents=True, exist_ok=True)
    sr = 44100
    beat_sec = 60.0 / bpm
    bar_samples = int(sr * beat_sec * 4)
    beat_samples = int(sr * beat_sec)

    # 1-beat punchy kick
    t = np.arange(beat_samples, dtype=np.float64) / sr
    freq_env = sub_freq + (190.0 - sub_freq) * np.exp(-t / 0.022) + 900.0 * np.exp(-t / 0.003)
    phase = 2.0 * np.pi * np.cumsum(freq_env) / sr
    amp_env = np.exp(-t / 0.16) * (1.0 - np.exp(-t / 0.0015))
    kick = np.tanh(np.sin(phase) * drive) * amp_env

    # Tile 4 beats into 1 bar
    audio = np.zeros(bar_samples, dtype=np.float64)
    for b in range(4):
        start = b * beat_samples
        end = min(bar_samples, start + beat_samples)
        audio[start:end] += kick[: end - start]

    if include_rumble:
        # Filtered/saturated low-end rumble ducked on each beat
        t_bar = np.arange(bar_samples, dtype=np.float64) / sr
        noise = np.random.default_rng(42).normal(0.0, 1.0, bar_samples)
        # Simple 2-pole lowpass via exponential smoothing
        alpha = 0.035
        lp = np.zeros_like(noise)
        acc = 0.0
        for i in range(bar_samples):
            acc += alpha * (noise[i] - acc)
            lp[i] = acc
        sub = np.sin(2.0 * np.pi * sub_freq * t_bar)
        rumble = np.tanh((lp * 3.5 + sub * 0.45) * 2.2)

        # Sidechain ducking envelope per beat
        beat_phase = (np.arange(bar_samples) % beat_samples) / beat_samples
        duck = np.clip((beat_phase - 0.12) / 0.35, 0.0, 1.0) ** 1.5
        audio = np.tanh(audio + rumble * duck * 0.42)

    audio = audio / max(1e-6, np.max(np.abs(audio))) * 0.92
    pcm = (audio * 32767.0).astype(np.int16)

    out_name = filename or f"hard_techno_kick_{int(bpm)}bpm.wav"
    out_path = SAMPLE_OUT_DIR / out_name
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return out_path
