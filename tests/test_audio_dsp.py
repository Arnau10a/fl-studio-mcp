"""Tests for Hard Techno MIDI/WAV synthesis, DSP invariants, and audio analysis."""

from __future__ import annotations

import wave
from pathlib import Path
from unittest.mock import patch

import mido
import numpy as np
import pytest

from examples import uptempo_190bpm
from fl_studio_mcp import hard_techno
from fl_studio_mcp.audio_analysis import analyze_wav


def _write_test_wav(path: Path, samples: np.ndarray, sr: int = 44100) -> Path:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return path


def test_generate_all_midi_styles(tmp_path: Path) -> None:
    with patch.object(hard_techno, "MIDI_OUT_DIR", tmp_path):
        for style in ("rumble_bass", "acid_303", "rave_stab", "schranz_perc"):
            out = hard_techno.generate_hard_techno_midi(
                style=style,
                bpm=150.0,
                root_note="F",
                scale="phrygian",
                bars=2,
                seed=42,
            )
            assert out.exists()
            mid = mido.MidiFile(out)
            note_ons = [m for m in mid.tracks[0] if m.type == "note_on"]
            assert len(note_ons) > 0


def test_invalid_midi_style_raises(tmp_path: Path) -> None:
    with (
        patch.object(hard_techno, "MIDI_OUT_DIR", tmp_path),
        pytest.raises(ValueError, match="Unknown style"),
    ):
        hard_techno.generate_hard_techno_midi(style="unknown")


def test_kick_wav_dsp_invariants_and_analysis(tmp_path: Path) -> None:
    with patch.object(hard_techno, "SAMPLE_OUT_DIR", tmp_path):
        wav_path = hard_techno.generate_hard_techno_kick_wav(
            bpm=150.0,
            drive=4.5,
            sub_freq=48.0,
            include_rumble=True,
        )
        assert wav_path.exists()
        analysis = analyze_wav(wav_path)
        assert analysis["sample_rate"] == 44100
        assert analysis["channels"] == 1
        assert analysis["frame_count"] == int(44100 * (60.0 / 150.0) * 4)
        assert 0.5 < analysis["peak_linear"] <= 0.95
        assert analysis["clipping_detected"] is False
        # Sub + bass energy should dominate a Hard Techno kick + rumble
        low_end = (
            analysis["spectral_bands"]["sub_20_60hz_pct"]
            + analysis["spectral_bands"]["bass_60_250hz_pct"]
        )
        assert low_end > 50.0


def test_analyze_wav_spectral_separation_and_clipping(tmp_path: Path) -> None:
    sr = 44100
    t = np.arange(sr, dtype=np.float64) / sr

    # Clean 45 Hz sub sine
    sub_wav = _write_test_wav(tmp_path / "sub45.wav", 0.5 * np.sin(2.0 * np.pi * 45.0 * t), sr)
    sub_res = analyze_wav(sub_wav)
    assert sub_res["spectral_bands"]["sub_20_60hz_pct"] > 95.0
    assert sub_res["clipping_detected"] is False
    assert pytest.approx(sub_res["peak_dbfs"], abs=0.2) == -6.02

    # Clipped 2 kHz signal
    hot = np.clip(2.0 * np.sin(2.0 * np.pi * 2000.0 * t), -1.0, 1.0)
    clip_wav = _write_test_wav(tmp_path / "clipped.wav", hot, sr)
    clip_res = analyze_wav(clip_wav)
    assert clip_res["clipping_detected"] is True
    assert clip_res["clipped_samples"] > 1000
    assert clip_res["spectral_bands"]["high_mid_1k_4khz_pct"] > 50.0


def test_uptempo_example_generate_all(tmp_path: Path) -> None:
    with (
        patch.object(uptempo_190bpm, "MIDI_OUT_DIR", tmp_path / "midi"),
        patch.object(uptempo_190bpm, "SAMPLE_OUT_DIR", tmp_path / "samples"),
    ):
        files = uptempo_190bpm.generate_all()
        assert len(files) == 8
        for p in files.values():
            assert Path(p).exists()
