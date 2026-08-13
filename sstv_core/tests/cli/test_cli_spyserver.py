"""decode --spyserver: argument handling and honest failures.

Nothing here touches a real network. The source is monkeypatched at the
MODULE, not imported by name -- `_decode_spyserver` looks
`SpyServerSource` up on the module at call time, so a fake substituted
here is the one it builds. A direct `from ... import SpyServerSource` in
the CLI would silently defeat every one of these tests and dial out for
real.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from sstv_core.cli.main import BAND_PRESETS, main
from sstv_core.sdr.spyserver.client import SpyServerError


class TestBandPresets:
    def test_hf_presets_match_product_md(self):
        assert BAND_PRESETS["20m"] == 14_230_000
        assert BAND_PRESETS["40m"] == 7_171_000
        assert BAND_PRESETS["15m"] == 21_340_000
        assert BAND_PRESETS["10m"] == 28_680_000
        assert BAND_PRESETS["80m"] == 3_845_000

    def test_fm_presets_are_absent_because_fm_is_out_of_scope(self):
        assert "2m" not in BAND_PRESETS


class _FakeSource:
    """The duck type RXManager really touches, so the fake fails where the
    real one would.

    RXManager.receive() calls get_input_levels() BEFORE start_input(), so a
    fake without it dies of AttributeError and the test proves nothing
    about the error it claims to cover.
    """

    sample_rate = 48000

    def __init__(self, start_error=None, stream_failure=None, dropped_frames=0):
        self._start_error = start_error
        self.stream_failure = stream_failure
        self.dropped_frames = dropped_frames
        self.stopped = False

    def start_input(self, device_index=None, callback=None, buffer_size=480000):
        if self._start_error is not None:
            raise self._start_error

    def stop_input(self):
        self.stopped = True

    def get_input_buffer(self):
        from sstv_core.audio.ring_buffer import AudioRingBuffer

        return AudioRingBuffer(max_samples=48000)

    def get_input_levels(self):
        return SimpleNamespace(rms=0.0, peak=0.0, is_clipping=False)


@pytest.fixture
def patched_source(monkeypatch):
    """Install a fake SpyServerSource and hand back the instance built."""
    import sstv_core.sdr.source as source_module

    built = {}

    def install(fake):
        def factory(*args, **kwargs):
            built["kwargs"] = kwargs
            built["source"] = fake
            return fake

        monkeypatch.setattr(source_module, "SpyServerSource", factory)
        return built

    return install


class TestArgumentHandling:
    def test_spyserver_and_device_together_is_an_error(self):
        assert main(["decode", "--spyserver", "host:5555", "--device", "ca_Test"]) == 1

    def test_spyserver_and_file_together_is_an_error(self):
        assert main(["decode", "--spyserver", "host:5555", "--file", "x.wav"]) == 1

    def test_unknown_band_is_rejected(self):
        """Exit 1, not argparse's SystemExit(2).

        `choices=` on the argument would make argparse abort the process
        before main() can return anything, so the band is checked in code
        where it can produce a branded error and an exit code.
        """
        assert main(["decode", "--spyserver", "host:5555", "--band", "6m"]) == 1

    def test_fm_band_is_rejected_as_out_of_scope(self):
        """2m is FM; mis-demodulating it silently would be worse than a no."""
        assert main(["decode", "--spyserver", "host:5555", "--band", "2m"]) == 1

    def test_unreadable_port_is_rejected(self):
        assert main(["decode", "--spyserver", "host:notaport"]) == 1

    def test_band_selects_the_preset_frequency(self, patched_source, tmp_path):
        built = patched_source(_FakeSource())
        main(
            ["decode", "--spyserver", "host:1234", "--band", "40m",
             "--timeout", "1", "--output", str(tmp_path / "o.png")]
        )
        assert built["kwargs"]["frequency_hz"] == 7_171_000
        assert built["kwargs"]["host"] == "host"
        assert built["kwargs"]["port"] == 1234

    def test_explicit_frequency_overrides_band(self, patched_source, tmp_path):
        built = patched_source(_FakeSource())
        main(
            ["decode", "--spyserver", "host", "--band", "40m",
             "--frequency", "14233000", "--timeout", "1",
             "--output", str(tmp_path / "o.png")]
        )
        assert built["kwargs"]["frequency_hz"] == 14_233_000
        # Bare host means the default port.
        assert built["kwargs"]["port"] == 5555

    def test_default_frequency_is_the_20m_calling_frequency(
        self, patched_source, tmp_path
    ):
        built = patched_source(_FakeSource())
        main(
            ["decode", "--spyserver", "host", "--timeout", "1",
             "--output", str(tmp_path / "o.png")]
        )
        assert built["kwargs"]["frequency_hz"] == 14_230_000


class TestFailureReporting:
    def test_connection_failure_exits_one_not_zero(self, patched_source):
        """An unreachable server must never look like a successful run."""
        patched_source(
            _FakeSource(
                start_error=SpyServerError(
                    "I couldn't reach the SpyServer at nowhere.test:5555.",
                    suggested_action="Check the host and port.",
                )
            )
        )
        rc = main(
            ["decode", "--spyserver", "nowhere.test:5555", "--band", "20m",
             "--timeout", "1"]
        )
        assert rc == 1

    def test_dropped_stream_is_exit_1_not_a_quiet_band(self, patched_source, caplog):
        """The single most important behavior in this command.

        RXManager.receive() returns None on timeout, and a stream that
        dropped mid-decode returns None too. Checking `result is None`
        first would report a dead TCP link as "I didn't hear a
        transmission" -- a network fault dressed up as a quiet band.
        """
        patched_source(
            _FakeSource(
                stream_failure=SpyServerError(
                    "The stream from the SpyServer dropped.",
                    suggested_action="Check the network, then try again.",
                )
            )
        )
        with caplog.at_level("INFO"):
            rc = main(
                ["decode", "--spyserver", "host", "--band", "20m", "--timeout", "1"]
            )
        assert rc == 1, "a dropped stream must not exit 2 like a quiet band"
        assert "dropped" in caplog.text
        assert "didn't hear" not in caplog.text

    def test_quiet_band_is_exit_2(self, patched_source, caplog):
        """With the stream healthy, no signal really is exit 2."""
        patched_source(_FakeSource())
        with caplog.at_level("INFO"):
            rc = main(
                ["decode", "--spyserver", "host", "--band", "20m", "--timeout", "1"]
            )
        assert rc == 2
        assert "didn't hear" in caplog.text

    def test_dropped_frames_are_reported_as_a_stream_problem(
        self, patched_source, caplog
    ):
        """Gaps from a lossy link must not be blamed on the signal."""
        patched_source(_FakeSource(dropped_frames=42))
        with caplog.at_level("INFO"):
            main(["decode", "--spyserver", "host", "--timeout", "1"])
        assert "42" in caplog.text
