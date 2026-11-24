"""Unit tests for Hard Techno and Uptempo MIDI/WAV generators."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

import mido

import hard_techno
from examples import uptempo_190bpm


class TestHardTechnoGenerators(unittest.TestCase):
    def test_generate_all_midi_styles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            with patch.object(hard_techno, "MIDI_OUT_DIR", tmp_dir):
                for style in ("rumble_bass", "acid_303", "rave_stab", "schranz_perc"):
                    out = hard_techno.generate_hard_techno_midi(
                        style=style,
                        bpm=150.0,
                        root_note="F",
                        scale="phrygian",
                        bars=2,
                        seed=42,
                    )
                    self.assertTrue(out.exists())
                    mid = mido.MidiFile(out)
                    note_ons = [m for m in mid.tracks[0] if m.type == "note_on"]
                    self.assertGreater(len(note_ons), 0)

    def test_invalid_style_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(hard_techno, "MIDI_OUT_DIR", Path(tmp)):
                with self.assertRaises(ValueError):
                    hard_techno.generate_hard_techno_midi(style="unknown")

    def test_generate_kick_wav(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            with patch.object(hard_techno, "SAMPLE_OUT_DIR", tmp_dir):
                wav_path = hard_techno.generate_hard_techno_kick_wav(
                    bpm=150.0,
                    drive=4.5,
                    sub_freq=48.0,
                    include_rumble=True,
                )
                self.assertTrue(wav_path.exists())
                with wave.open(str(wav_path), "rb") as wf:
                    self.assertEqual(wf.getnchannels(), 1)
                    self.assertEqual(wf.getsampwidth(), 2)
                    self.assertEqual(wf.getframerate(), 44100)
                    # 1 bar at 150 BPM = 1.6s = 70560 frames
                    self.assertEqual(wf.getnframes(), int(44100 * (60.0 / 150.0) * 4))


class TestUptempoExampleGenerator(unittest.TestCase):
    def test_generate_all_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            with (
                patch.object(uptempo_190bpm, "MIDI_OUT_DIR", tmp_root / "midi"),
                patch.object(uptempo_190bpm, "SAMPLE_OUT_DIR", tmp_root / "samples"),
            ):
                files = uptempo_190bpm.generate_all()
                self.assertEqual(len(files), 8)
                for p in files.values():
                    self.assertTrue(Path(p).exists(), f"Missing generated file: {p}")


if __name__ == "__main__":
    unittest.main()
