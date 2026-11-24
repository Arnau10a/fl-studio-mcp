"""The Straikerz-style Xtra Raw / Uptempo (190 BPM, F Phrygian) 48-bar MIDI and WAV generator."""

from __future__ import annotations

from pathlib import Path
import wave

import mido
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
MIDI_OUT_DIR = BASE_DIR / "output" / "midi"
SAMPLE_OUT_DIR = BASE_DIR / "output" / "samples"

BPM = 190.0
TPB = 480  # ticks per quarter note
BAR_TICKS = TPB * 4  # 1920 ticks per 4/4 bar
STEP_TICKS = TPB // 4  # 120 ticks per 16th note
TOTAL_BARS = 48

# F Phrygian pitch classes: F, Gb, Ab, Bb, C, Db, Eb
F_PHRYGIAN = [0, 1, 3, 5, 7, 8, 10]


def _events_to_midi(
    events: list[tuple[int, str, int, int]],
    out_path: Path,
    bpm: float = BPM,
) -> Path:
    """Write sorted absolute-tick MIDI events to a single-track .mid file."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mid = mido.MidiFile(ticks_per_beat=TPB)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))

    # Order note_off before note_on at identical ticks to prevent stuck overlapping notes
    ordered = sorted(events, key=lambda ev: (ev[0], 0 if ev[1] == "note_off" else 1, ev[2]))
    last_tick = 0
    for tick, msg_type, note, vel in ordered:
        delta = max(0, tick - last_tick)
        track.append(mido.Message(msg_type, note=int(note), velocity=int(vel), time=delta))
        last_tick = tick

    mid.save(out_path)
    return out_path


def _add_note(events: list[tuple[int, str, int, int]], tick: int, note: int, dur: int, vel: int) -> None:
    events.append((tick, "note_on", note, max(1, min(127, vel))))
    events.append((tick + max(10, dur), "note_off", note, 0))


def _build_kick_events() -> list[tuple[int, str, int, int]]:
    """48-bar kick timeline: Intro, Break silence, Build roll, Fake Drop, Drop 1, Drop 2."""
    events: list[tuple[int, str, int, int]] = []
    c5, d_sharp5, f5 = 60, 63, 65

    # Bars 1-8 (Intro): 4x4 kick, bar 8 beat 4 double-kick fill
    for bar in range(0, 8):
        base = bar * BAR_TICKS
        for beat in range(4):
            _add_note(events, base + beat * TPB, c5, 220, 118)
        if bar == 7:
            _add_note(events, base + 3 * TPB + 2 * STEP_TICKS, c5, 160, 110)

    # Bars 9-16 (Break): silence

    # Bars 17-24 (Build-Up): accelerating kicks, dead silence at bar 24 beats 3-4, surprise hit on last 16th
    for bar in range(16, 24):
        base = bar * BAR_TICKS
        rel = bar - 16
        if rel in (0, 1):  # Bars 17-18: half notes
            for beat in (0, 2):
                _add_note(events, base + beat * TPB, c5, 240, 100)
        elif rel in (2, 3):  # Bars 19-20: quarters
            for beat in range(4):
                _add_note(events, base + beat * TPB, c5, 200, 108)
        elif rel in (4, 5):  # Bars 21-22: 8th notes
            for eighth in range(8):
                _add_note(events, base + eighth * (TPB // 2), c5, 140, 114)
        elif rel == 6:  # Bar 23: 16th notes
            for step in range(16):
                _add_note(events, base + step * STEP_TICKS, c5, 95, 118)
        elif rel == 7:  # Bar 24: beats 1-2 16ths, Fake Drop silence beats 3-4, surprise hit on step 15
            for step in range(8):
                _add_note(events, base + step * STEP_TICKS, c5, 95, 122)
            _add_note(events, base + 15 * STEP_TICKS, f5, 100, 127)

    # Bars 25-36 (Drop 1 — Straikerz Bouncy/Kloenk + kick rolls on bars 28, 32, 36)
    for bar in range(24, 36):
        base = bar * BAR_TICKS
        rel = bar - 24
        if rel in (3, 7, 11):  # Bar 28, 32, 36: beats 1-2 4x4, beats 3-4 signature syncopated kick roll
            _add_note(events, base + 0 * TPB, c5, 220, 124)
            _add_note(events, base + 1 * TPB, c5, 220, 124)
            roll_steps = [
                (8, c5, 120), (10, d_sharp5, 116), (11, c5, 112),
                (12, f5, 124), (13, c5, 118), (14, d_sharp5, 122), (15, f5, 127),
            ]
            for st, note, vel in roll_steps:
                _add_note(events, base + st * STEP_TICKS, note, 100, vel)
        else:
            for beat in range(4):
                note = d_sharp5 if (rel % 2 == 1 and beat == 3) else c5
                _add_note(events, base + beat * TPB, note, 230, 124)
            if rel % 2 == 1:  # off-beat bounce double-kick at end of even bars
                _add_note(events, base + 14 * STEP_TICKS, c5, 110, 115)

    # Bars 37-48 (Drop 2 — Switch-Up with rapid rolls every 2 bars & hard bar 48 finish)
    for bar in range(36, 48):
        base = bar * BAR_TICKS
        rel = bar - 36
        if bar == 47:  # Bar 48: hard closing hits
            _add_note(events, base + 0 * TPB, c5, 240, 127)
            _add_note(events, base + 1 * TPB, d_sharp5, 220, 124)
            _add_note(events, base + 2 * TPB, c5, 240, 127)
        elif rel % 2 == 1:  # Even bars in Drop 2: double-time bounce + 16th roll tail
            _add_note(events, base + 0 * TPB, c5, 200, 125)
            _add_note(events, base + 1 * TPB, c5, 200, 125)
            _add_note(events, base + 6 * STEP_TICKS, d_sharp5, 110, 118)
            for st, note in [(8, c5), (10, c5), (12, d_sharp5), (13, f5), (14, c5), (15, f5)]:
                _add_note(events, base + st * STEP_TICKS, note, 95, 124)
        else:
            for beat in range(4):
                _add_note(events, base + beat * TPB, c5, 220, 125)
            _add_note(events, base + 10 * STEP_TICKS, d_sharp5, 110, 116)

    return events


def _build_screech_events() -> list[tuple[int, str, int, int]]:
    """48-bar Serum screech: tease, Break melody, Build pitch climb, Fake Drop stab, Drops 1 & 2."""
    events: list[tuple[int, str, int, int]] = []
    # F4=65, Gb4=66, Ab4=68, Bb4=70, C5=72, Db5=73, Eb5=75, F5=77, Gb5=78

    # Bars 5-8 (Intro tease stabs)
    for bar in range(4, 8):
        base = bar * BAR_TICKS
        for st, note in [(2, 65), (6, 66), (10, 65), (14, 72)]:
            _add_note(events, base + st * STEP_TICKS, note, 140, 92 + (bar - 4) * 6)

    # Bars 9-16 (Break atmospheric dark melody)
    break_phrase = [
        (0, 77, 420), (4, 78, 420), (8, 77, 420), (12, 75, 420),
        (16, 73, 420), (20, 72, 420), (24, 68, 420), (28, 72, 420),
    ]
    for rep in range(4):  # 2 bars per phrase x 4 = 8 bars (bars 9-16)
        base = (8 + rep * 2) * BAR_TICKS
        for st, note, dur in break_phrase:
            _add_note(events, base + st * STEP_TICKS, note, dur, 102)

    # Bars 17-24 (Build-Up rising stabs + Fake Drop solo stab on bar 24 beat 3.5)
    for bar in range(16, 24):
        base = bar * BAR_TICKS
        rel = bar - 16
        pitch = 65 + (12 if rel >= 4 else 0) + (1 if rel in (3, 7) else 0)
        if rel < 7:
            step_inc = 4 if rel < 4 else 2
            for st in range(0, 16, step_inc):
                _add_note(events, base + st * STEP_TICKS, pitch, 140, 96 + rel * 4)
        else:  # Bar 24: 16ths on beats 1-2, then silence, then solo screaming stab at beat 3.5 (step 14)
            for st in range(0, 8, 2):
                _add_note(events, base + st * STEP_TICKS, 78, 120, 124)
            _add_note(events, base + 14 * STEP_TICKS, 89, 200, 127)

    # Bars 25-36 (Drop 1 — Straikerz bouncy screech riff)
    drop1_riff = [
        (2, 65, 180), (6, 66, 180), (10, 65, 160), (13, 77, 150), (15, 78, 130),
    ]
    for bar in range(24, 36):
        base = bar * BAR_TICKS
        shift = 1 if (bar - 24) % 4 == 3 else 0
        for st, note, dur in drop1_riff:
            _add_note(events, base + st * STEP_TICKS, note + shift, dur, 120)

    # Bars 37-48 (Drop 2 — Switch-Up octave-high relentless screech)
    drop2_riff = [
        (0, 77, 140), (3, 78, 140), (6, 77, 140), (8, 84, 140), (11, 78, 140), (14, 77, 160),
    ]
    for bar in range(36, 48):
        base = bar * BAR_TICKS
        if bar == 47:
            _add_note(events, base + 0 * TPB, 77, 300, 127)
            _add_note(events, base + 2 * TPB, 89, 420, 127)
            _add_note(events, base + 15 * STEP_TICKS, 77, 100, 120)
        else:
            shift = 1 if (bar - 36) % 2 == 1 else 0
            for st, note, dur in drop2_riff:
                _add_note(events, base + st * STEP_TICKS, note + shift, dur, 124)

    return events


def _build_hoover_events() -> list[tuple[int, str, int, int]]:
    """48-bar GMS hoover/rave stabs supporting Intro, Build, and both Drops."""
    events: list[tuple[int, str, int, int]] = []
    chords = [
        [53, 60, 65],  # Fm power
        [54, 61, 66],  # Gb power
        [56, 63, 68],  # Ab power
        [51, 58, 63],  # Eb power
    ]

    # Bars 1-8 (Intro): bar-start dark hits
    for bar in range(0, 8, 2):
        base = bar * BAR_TICKS
        for n in chords[0]:
            _add_note(events, base, n, 360, 96)

    # Bars 17-24 (Build-Up): beat-1 tension stabs through bar 24 beat 2
    for bar in range(16, 24):
        base = bar * BAR_TICKS
        ch = chords[(bar - 16) % len(chords)]
        for beat in (0, 2) if bar < 23 else (0, 1):
            for n in ch:
                _add_note(events, base + beat * TPB, n, 240, 104)

    # Bars 25-48 (Drops 1 & 2): driving off-beat & syncopated rave power stabs
    for bar in range(24, 48):
        base = bar * BAR_TICKS
        ch = chords[((bar - 24) // 2) % len(chords)]
        if bar == 47:
            for n in chords[0]:
                _add_note(events, base, n, 480, 122)
        else:
            for st in (0, 6, 10, 14):
                for n in ch:
                    _add_note(events, base + st * STEP_TICKS, n, 180, 114)

    return events


def _build_pad_events() -> list[tuple[int, str, int, int]]:
    """48-bar Sytrus dark F Phrygian pad for Intro, Break, and Build-Up tension."""
    events: list[tuple[int, str, int, int]] = []
    progression = [
        [53, 60, 65, 68],  # Fm
        [54, 61, 65, 68],  # GbMaj7
        [56, 63, 68, 72],  # Ab
        [51, 58, 63, 67],  # Eb
    ]

    # Bars 1-16 (Intro + Break): 2 bars per chord
    for idx in range(8):
        bar = idx * 2
        ch = progression[idx % len(progression)]
        base = bar * BAR_TICKS
        dur = 2 * BAR_TICKS - 60
        vel = 78 if bar < 8 else 96
        for n in ch:
            _add_note(events, base, n, dur, vel)

    # Bars 17-24 (Build-Up): octave-higher tension pad cutting sharply at bar 24 beat 2
    for idx in range(4):
        bar = 16 + idx * 2
        ch = [n + 12 for n in progression[idx % len(progression)]]
        base = bar * BAR_TICKS
        dur = (2 * BAR_TICKS - 60) if idx < 3 else (TPB * 2 - 40)
        for n in ch:
            _add_note(events, base, n, dur, 102)

    return events


def _build_perc_events() -> list[tuple[int, str, int, int]]:
    """48-bar FPC GM percussion: Crash (49), Snare roll (38), Closed Hat (42), Open Hat (46)."""
    events: list[tuple[int, str, int, int]] = []
    snare, closed_hat, open_hat, crash = 38, 42, 46, 49

    # Bars 1-8 (Intro): Crash on bar 1 + off-beat open hats + 16th closed hats
    _add_note(events, 0, crash, 480, 115)
    for bar in range(0, 8):
        base = bar * BAR_TICKS
        for step in range(16):
            if step % 4 == 2:
                _add_note(events, base + step * STEP_TICKS, open_hat, 120, 96)
            elif step % 2 == 1:
                _add_note(events, base + step * STEP_TICKS, closed_hat, 80, 72)

    # Bars 9-16 (Break): Crash on bar 9 + subtle hats on bars 13-16
    _add_note(events, 8 * BAR_TICKS, crash, 600, 110)
    for bar in range(12, 16):
        base = bar * BAR_TICKS
        for step in (2, 6, 10, 14):
            _add_note(events, base + step * STEP_TICKS, closed_hat, 90, 76)

    # Bars 17-24 (Build-Up): accelerating Snare Roll (quarters -> 8ths -> 16ths -> 32nds)
    for bar in range(16, 24):
        base = bar * BAR_TICKS
        rel = bar - 16
        if rel in (0, 1):
            for beat in range(4):
                _add_note(events, base + beat * TPB, snare, 120, 84 + rel * 6)
        elif rel in (2, 3):
            for eighth in range(8):
                _add_note(events, base + eighth * (TPB // 2), snare, 90, 92 + rel * 4)
        elif rel in (4, 5):
            for step in range(16):
                _add_note(events, base + step * STEP_TICKS, snare, 65, 104 + rel * 2)
        elif rel == 6:
            for sub in range(32):  # 32nd-note roll
                vel = min(127, 92 + sub)
                _add_note(events, base + sub * (STEP_TICKS // 2), snare, 40, vel)
        elif rel == 7:  # Bar 24: 32nd roll beats 1-2, then dead silence for Fake Drop
            for sub in range(16):
                _add_note(events, base + sub * (STEP_TICKS // 2), snare, 40, 118 + min(9, sub // 2))

    # Bars 25-48 (Drops 1 & 2): Crash at bar 25 & 37 + driving off-beat hats + clap/snare on 2 & 4
    _add_note(events, 24 * BAR_TICKS, crash, 480, 127)
    _add_note(events, 36 * BAR_TICKS, crash, 480, 127)
    for bar in range(24, 48):
        base = bar * BAR_TICKS
        if bar == 47:
            _add_note(events, base, crash, 600, 127)
            _add_note(events, base + 15 * STEP_TICKS, closed_hat, 90, 100)
        else:
            for beat in (1, 3):
                _add_note(events, base + beat * TPB, snare, 130, 118)
            for step in range(16):
                if step % 4 == 2:
                    _add_note(events, base + step * STEP_TICKS, open_hat, 120, 108)
                elif bar >= 36 and step % 2 == 1:
                    _add_note(events, base + step * STEP_TICKS, closed_hat, 70, 82)

    return events


def _write_wav(path: Path, samples: np.ndarray, sr: int = 44100) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return path


def generate_straikerz_samples(bpm: float = BPM) -> dict[str, Path]:
    """Synthesize Straikerz-style kloenk kick, zaag kick, and 8-bar riser WAVs at BPM."""
    sr = 44100
    beat_s = 60.0 / bpm

    # 1. Kloenk Kick (1 beat): resonant mid-high PVC/kloenk transient + clipped sub tail
    n_kick = int(sr * beat_s)
    t = np.arange(n_kick) / sr
    pitch_sweep = 54.0 + 480.0 * np.exp(-t / 0.014) + 1200.0 * np.exp(-t / 0.004)
    kloenk_ping = 0.65 * np.sin(2.0 * np.pi * 1650.0 * t) * np.exp(-t / 0.022)
    body = np.sin(2.0 * np.pi * np.cumsum(pitch_sweep) / sr)
    kloenk_raw = np.tanh((body * np.exp(-t / 0.24) + kloenk_ping) * 6.5)
    fade_out = np.minimum(1.0, (n_kick - np.arange(n_kick)) / (0.008 * sr))
    kloenk_path = _write_wav(SAMPLE_OUT_DIR / "straikerz_kloenk_kick_190.wav", kloenk_raw * fade_out * 0.92, sr)

    # 2. Zaag Kick (1 beat): aggressive saw-saturated punch + clipped sub
    saw_phase = (np.cumsum(np.full(n_kick, 56.0) + 220.0 * np.exp(-t / 0.012)) / sr) % 1.0
    saw = 2.0 * saw_phase - 1.0
    zaag_raw = np.tanh((0.55 * saw + 0.75 * body) * np.exp(-t / 0.22) * 8.0)
    zaag_path = _write_wav(SAMPLE_OUT_DIR / "straikerz_zaag_kick_190.wav", zaag_raw * fade_out * 0.92, sr)

    # 3. 8-bar Build-Up Riser (white noise sweep + rising synth pitch)
    n_riser = int(sr * beat_s * 4 * 8)
    tr = np.arange(n_riser) / sr
    prog = tr / (tr[-1] + 1e-9)
    rng = np.random.default_rng(190)
    noise = rng.normal(0.0, 0.35, n_riser)
    # Simple moving low-pass / brightness swell by mixing raw noise with rising sine/saw
    riser_freq = 110.0 * (2.0 ** (3.5 * prog))
    riser_tone = np.sin(2.0 * np.pi * np.cumsum(riser_freq) / sr)
    env = (prog ** 1.8) * np.minimum(1.0, (n_riser - np.arange(n_riser)) / (0.015 * sr))
    riser = np.tanh((0.65 * riser_tone + 0.55 * noise * prog) * 1.8) * env * 0.85
    riser_path = _write_wav(SAMPLE_OUT_DIR / "straikerz_riser_8bars_190.wav", riser, sr)

    return {
        "kloenk_kick": kloenk_path,
        "zaag_kick": zaag_path,
        "riser": riser_path,
    }


def generate_all() -> dict[str, str]:
    """Generate all 5 48-bar MIDI tracks and 3 WAV samples."""
    files = {
        "kick_midi": str(_events_to_midi(_build_kick_events(), MIDI_OUT_DIR / "straikerz_kick_48bars.mid")),
        "screech_midi": str(_events_to_midi(_build_screech_events(), MIDI_OUT_DIR / "straikerz_screech_48bars.mid")),
        "hoover_midi": str(_events_to_midi(_build_hoover_events(), MIDI_OUT_DIR / "straikerz_hoover_48bars.mid")),
        "pad_midi": str(_events_to_midi(_build_pad_events(), MIDI_OUT_DIR / "straikerz_pad_48bars.mid")),
        "perc_midi": str(_events_to_midi(_build_perc_events(), MIDI_OUT_DIR / "straikerz_perc_48bars.mid")),
    }
    for k, v in generate_straikerz_samples().items():
        files[k] = str(v)
    return files


if __name__ == "__main__":
    import json
    print(json.dumps(generate_all(), indent=2))
