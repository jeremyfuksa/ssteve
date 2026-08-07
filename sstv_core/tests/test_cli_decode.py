"""Tests for the CLI decode command.

The file-decode path is the one the CLI can actually exercise offline, and it
is what makes the reference corpus usable from a shell. The live-device path
is deliberately not implemented and must say so rather than pretend.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from sstv_core.cli.main import cmd_decode

REFERENCE = Path(__file__).parent / "reference" / "audio"


def make_args(**overrides) -> argparse.Namespace:
    defaults = {
        "mode": "ScottieS1",
        "device": None,
        "file": None,
        "timeout": 300,
        "output": None,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class TestDecodeFromFile:
    def test_decodes_a_reference_recording_to_an_image(self, tmp_path):
        """The happy path must write a real image and report the truth."""
        source = REFERENCE / "mmsstv" / "scottie_s1_winter_creek.wav"
        if not source.exists():
            pytest.skip("reference audio missing")

        output = tmp_path / "decoded.png"
        code = cmd_decode(make_args(file=str(source), output=str(output)))

        assert code == 0
        assert output.exists(), "decode reported success but wrote no file"
        assert output.stat().st_size > 10_000, "output is too small to be an image"

    def test_missing_file_is_an_error(self, tmp_path):
        code = cmd_decode(make_args(file=str(tmp_path / "nope.wav")))
        assert code == 1

    def test_unknown_mode_is_an_error(self, tmp_path):
        source = REFERENCE / "mmsstv" / "scottie_s1_winter_creek.wav"
        if not source.exists():
            pytest.skip("reference audio missing")

        code = cmd_decode(make_args(file=str(source), mode="PD120"))
        assert code == 1

    def test_audio_without_sstv_is_an_error(self, tmp_path):
        """Silence must fail rather than emit a blank image."""
        import wave

        import numpy as np

        path = tmp_path / "silence.wav"
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(22050)
            handle.writeframes(np.zeros(22050 * 3, dtype=np.int16).tobytes())

        assert cmd_decode(make_args(file=str(path))) == 1


class TestDecodeFromDevice:
    def test_requires_a_device_or_a_file(self):
        assert cmd_decode(make_args()) == 1

    def test_live_decode_reports_that_it_is_not_implemented(self, monkeypatch):
        """The live path must fail honestly.

        It previously emitted fabricated vis_detected, scanline_update, and
        decode_complete events naming a file it never wrote. In --json mode
        that told a screen-reader user a decode had succeeded when nothing
        had happened.
        """
        from sstv_core.audio import device_manager

        class FakeDevice:
            id = "fake"
            name = "Fake Input"
            is_default = True
            is_input = True

        class FakeManager:
            def list_all_devices(self):
                return [FakeDevice()]

        monkeypatch.setattr(device_manager, "AudioDeviceManager", FakeManager)

        code = cmd_decode(make_args(device="fake"))

        assert code == 2, "live decode should report not-implemented, not success"
