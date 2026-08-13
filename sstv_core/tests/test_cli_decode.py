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
        "spyserver": None,
        "band": None,
        "frequency": None,
        "gain": None,
        "timeout": 300,
        "output": None,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_make_args_matches_the_real_parser_defaults():
    """The hand-built Namespace has to match the real parser.

    These tests call cmd_decode() directly, so a flag added to the parser
    but not here makes every one of them die of AttributeError instead of
    testing anything. Adding --spyserver did exactly that.

    Defaults are compared too, not just names: --gain's default later
    changed from 0 to None (0 is a legal gain, so it can't mean "unset"),
    and a names-only check let that divergence route real --file runs down
    the SpyServer path instead.
    """
    from sstv_core.cli.main import create_parser

    parsed = vars(create_parser().parse_args(["decode"]))
    # verbose/json exist twice over: once from the top-level parser
    # (*_global) and once from the subparser, so --verbose works on either
    # side of the subcommand (issue #91). main() merges them.
    for key in ("command", "verbose", "json", "verbose_global", "json_global"):
        parsed.pop(key, None)
    # mode is the one deliberate difference: the parser defaults it to
    # None (auto-detect) while these tests pin a mode to decode with.
    parsed.pop("mode")
    defaults = vars(make_args())
    defaults.pop("mode")
    assert parsed == defaults


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

    def test_live_decode_timeout_fails_honestly(self, monkeypatch):
        """No signal before the timeout must be a nonzero exit, never a
        fabricated success.

        (History: this path once emitted fake decode_complete events; then
        it was an honest not-wired-up error; as of 2026-08-08 it runs the
        real RX pipeline, so the honest failure is the no-signal timeout.)
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

            def get_device_index(self, device_id):
                return 0

        monkeypatch.setattr(device_manager, "AudioDeviceManager", FakeManager)

        import sstv_core.decode.rx_manager as rx_module

        class NoSignalRX:
            def __init__(self, *args, **kwargs):
                pass

            def set_progress_callback(self, cb):
                pass

            async def receive(self, **kwargs):
                return None  # VIS timeout: nothing heard

        monkeypatch.setattr(rx_module, "RXManager", NoSignalRX)

        code = cmd_decode(make_args(device="fake"))

        assert code == 2, "no-signal timeout should exit 2, not fake success"
