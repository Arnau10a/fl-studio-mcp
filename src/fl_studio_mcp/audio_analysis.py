"""Audio DSP analysis for closed-loop level, clipping, and spectral feedback."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any

import numpy as np

from fl_studio_mcp.paths import get_output_dir


def _resolve_audio_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate
    if candidate.exists():
        return candidate.resolve()
    out_candidate = get_output_dir() / candidate
    if out_candidate.exists():
        return out_candidate.resolve()
    samples_candidate = get_output_dir() / "samples" / candidate
    if samples_candidate.exists():
        return samples_candidate.resolve()
    return candidate.resolve()


def _pcm_bytes_to_float(raw: bytes, sample_width: int, channels: int) -> np.ndarray:
    if sample_width == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float64) - 128.0) / 128.0
    elif sample_width == 2:
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    elif sample_width == 3:
        raw_u8 = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        signed = (
            raw_u8[:, 0].astype(np.int32)
            | (raw_u8[:, 1].astype(np.int32) << 8)
            | (raw_u8[:, 2].astype(np.int32) << 16)
        )
        signed = np.where(signed & 0x800000, signed - 0x1000000, signed)
        data = signed.astype(np.float64) / 8388608.0
    elif sample_width == 4:
        data = np.frombuffer(raw, dtype=np.int32).astype(np.float64) / 2147483648.0
    else:
        raise ValueError(f"Unsupported WAV sample width: {sample_width} bytes")

    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data


def _to_dbfs(linear: float) -> float:
    return round(float(20.0 * np.log10(max(linear, 1e-12))), 2)


def analyze_wav(path: str | Path) -> dict[str, Any]:
    """Analyze a WAV file for dynamics, headroom, clipping, and spectral band balance."""
    resolved = _resolve_audio_path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"Audio file not found: {resolved}")

    with wave.open(str(resolved), "rb") as wf:
        channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        sample_rate = wf.getframerate()
        frame_count = wf.getnframes()
        raw = wf.readframes(frame_count)

    if frame_count == 0:
        raise ValueError(f"Audio file is empty: {resolved}")

    mono = _pcm_bytes_to_float(raw, sample_width, channels)
    duration_sec = round(frame_count / float(sample_rate), 4)

    peak_linear = float(np.max(np.abs(mono)))
    rms_linear = float(np.sqrt(np.mean(mono * mono)))
    peak_dbfs = _to_dbfs(peak_linear)
    rms_dbfs = _to_dbfs(rms_linear)
    crest_factor_db = round(peak_dbfs - rms_dbfs, 2)
    dc_offset = round(float(np.mean(mono)), 6)
    clipped_samples = int(np.sum(np.abs(mono) >= 0.999))

    # Spectral band energy using Hann-windowed real FFT
    window = np.hanning(len(mono))
    spectrum = np.abs(np.fft.rfft(mono * window)) ** 2
    freqs = np.fft.rfftfreq(len(mono), d=1.0 / sample_rate)
    total_energy = float(np.sum(spectrum)) + 1e-18

    def _band_pct(lo: float, hi: float) -> float:
        mask = (freqs >= lo) & (freqs < hi)
        return round(float(np.sum(spectrum[mask]) / total_energy) * 100.0, 2)

    bands = {
        "sub_20_60hz_pct": _band_pct(20.0, 60.0),
        "bass_60_250hz_pct": _band_pct(60.0, 250.0),
        "low_mid_250_1000hz_pct": _band_pct(250.0, 1000.0),
        "high_mid_1k_4khz_pct": _band_pct(1000.0, 4000.0),
        "high_4k_plus_pct": _band_pct(4000.0, sample_rate / 2.0 + 1.0),
    }

    return {
        "file": str(resolved),
        "sample_rate": sample_rate,
        "channels": channels,
        "bit_depth": sample_width * 8,
        "frame_count": frame_count,
        "duration_sec": duration_sec,
        "peak_linear": round(peak_linear, 5),
        "peak_dbfs": peak_dbfs,
        "rms_dbfs": rms_dbfs,
        "crest_factor_db": crest_factor_db,
        "dc_offset": dc_offset,
        "clipped_samples": clipped_samples,
        "clipping_detected": clipped_samples > 0,
        "spectral_bands": bands,
    }
