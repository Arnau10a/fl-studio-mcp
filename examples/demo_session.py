"""Self-contained demo showcasing fl-studio-mcp in FL_MCP_MOCK=1 mode."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def run_demo() -> dict[str, object]:
    with tempfile.TemporaryDirectory() as tmp_dir:
        os.environ["FL_MCP_MOCK"] = "1"
        os.environ["FL_MCP_OUTPUT_DIR"] = tmp_dir

        from fl_studio_mcp import server as srv

        srv.bridge.close()
        srv.bridge._mock_runtime = None

        doctor = srv.fl_doctor()
        transport_bpm = srv.fl_transport("set_bpm", bpm=150.0)
        kick_wav = srv.ht_generate_kick_sample(bpm=150.0, drive=4.5, sub_freq=48.0)
        analysis = srv.fl_analyze_audio(kick_wav["wav_file"])
        acid_midi = srv.ht_generate_midi(
            style="acid_303", bpm=150.0, root_note="F", scale="phrygian", bars=4, seed=42
        )
        seq = srv.fl_step_sequencer(index=0, steps=[0, 4, 8, 12], mode="indices", length=16)
        mixer_eq = srv.fl_mixer_eq(index=1, band=0, gain=0.25, frequency=0.2, bandwidth=0.4)
        playing = srv.fl_transport("play")

        result = {
            "doctor_overall": doctor["overall"],
            "ping_ms": doctor["checks"]["sysex_ping"]["latency_ms"],
            "bpm": transport_bpm["bpm"],
            "kick_wav": Path(kick_wav["wav_file"]).name,
            "analysis": {
                "peak_dbfs": analysis["peak_dbfs"],
                "rms_dbfs": analysis["rms_dbfs"],
                "clipping_detected": analysis["clipping_detected"],
                "spectral_bands": analysis["spectral_bands"],
            },
            "acid_midi": Path(acid_midi["midi_file"]).name,
            "kick_steps": seq["steps"],
            "mixer_eq_low_gain": mixer_eq["gain"],
            "playing": playing["playing"],
        }
        srv.bridge.close()
        return result


if __name__ == "__main__":
    print(json.dumps(run_demo(), indent=2))
