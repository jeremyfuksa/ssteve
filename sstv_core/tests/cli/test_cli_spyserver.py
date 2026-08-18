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

    def __init__(
        self,
        start_error=None,
        stream_failure=None,
        dropped_frames=0,
        rms=0.0,
        resolved_gain=6,
    ):
        self._start_error = start_error
        self.stream_failure = stream_failure
        self.dropped_frames = dropped_frames
        self.stopped = False
        self._rms = rms
        self.resolved_gain = resolved_gain

    def start_input(self, device_index=None, callback=None, buffer_size=480000):
        if self._start_error is not None:
            raise self._start_error

    def stop_input(self):
        self.stopped = True

    def get_input_buffer(self):
        from sstv_core.audio.ring_buffer import AudioRingBuffer

        return AudioRingBuffer(max_samples=48000)

    def get_input_levels(self):
        return SimpleNamespace(rms=self._rms, peak=self._rms * 4, is_clipping=False)


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


@pytest.fixture
def stored_config(monkeypatch, tmp_path):
    """Point the CLI at a real throwaway database and seed spyserver values.

    A real SQLite file, not a stubbed ConfigManager: the point of the
    fallback is that values an operator saved once are actually read back,
    and only a real round trip proves that.
    """

    def install(**values):
        from sstv_core.database import init_database

        db_path = tmp_path / "config.db"
        monkeypatch.setenv("SSTVE_DB_PATH", str(db_path))
        _engine, factory = init_database(db_path=db_path)
        if values:
            from sstv_core.config.manager import ConfigManager

            session = factory()
            ConfigManager(session).update(
                {f"spyserver.{k}": v for k, v in values.items()}
            )
            session.commit()
            session.close()
        return db_path

    return install


class TestConfigFallback:
    """Flags win; stored settings fill the gaps."""

    def test_flags_only_with_no_config_still_works(
        self, patched_source, monkeypatch, tmp_path
    ):
        """A fully-specified command must not depend on a database at all."""
        monkeypatch.setenv("SSTVE_DB_PATH", str(tmp_path / "absent.db"))
        built = patched_source(_FakeSource())
        main(
            ["decode", "--spyserver", "flag.host:1234", "--band", "40m",
             "--gain", "7", "--timeout", "1"]
        )
        assert built["kwargs"]["host"] == "flag.host"
        assert built["kwargs"]["port"] == 1234
        assert built["kwargs"]["frequency_hz"] == 7_171_000
        assert built["kwargs"]["gain"] == 7

    def test_config_only_with_no_flags(self, patched_source, stored_config):
        """The whole point: stop retyping the host and frequency."""
        stored_config(
            host="stored.example.test",
            port=6000,
            frequency_hz=21_340_000,
            gain=12,
            stall_timeout_sec=9.5,
        )
        built = patched_source(_FakeSource())
        rc = main(["decode", "--timeout", "1"])
        assert rc == 2, "should have run and heard nothing, not failed to start"
        assert built["kwargs"]["host"] == "stored.example.test"
        assert built["kwargs"]["port"] == 6000
        assert built["kwargs"]["frequency_hz"] == 21_340_000
        assert built["kwargs"]["gain"] == 12

    def test_stall_timeout_reaches_the_source(self, patched_source, stored_config):
        """It has no flag, so config is its only route out of dead-config land."""
        stored_config(host="stored.example.test", stall_timeout_sec=11.25)
        built = patched_source(_FakeSource())
        main(["decode", "--timeout", "1"])
        assert built["kwargs"]["stall_timeout_sec"] == 11.25

    def test_flag_overrides_a_differing_stored_value(
        self, patched_source, stored_config
    ):
        stored_config(
            host="stored.example.test", port=6000, frequency_hz=21_340_000, gain=12
        )
        built = patched_source(_FakeSource())
        main(
            ["decode", "--spyserver", "flag.host:1234", "--frequency", "14233000",
             "--gain", "3", "--timeout", "1"]
        )
        assert built["kwargs"]["host"] == "flag.host"
        assert built["kwargs"]["port"] == 1234
        assert built["kwargs"]["frequency_hz"] == 14_233_000
        assert built["kwargs"]["gain"] == 3

    def test_band_flag_overrides_stored_frequency(
        self, patched_source, stored_config
    ):
        stored_config(host="stored.example.test", frequency_hz=21_340_000)
        built = patched_source(_FakeSource())
        main(["decode", "--band", "80m", "--timeout", "1"])
        assert built["kwargs"]["frequency_hz"] == 3_845_000

    def test_spyserver_flag_with_no_host_anywhere_is_an_honest_error(
        self, stored_config, caplog
    ):
        """--band asked for the SDR path, so name the missing piece."""
        stored_config()  # database exists, host still ""
        with caplog.at_level("INFO"):
            rc = main(["decode", "--band", "20m", "--timeout", "1"])
        assert rc == 1
        assert "which server" in caplog.text

    def test_bare_decode_with_nothing_stored_asks_for_a_source(
        self, stored_config, caplog
    ):
        """No source named and none saved: the sound-card error is the
        accurate one -- --device and --file are the likelier intent, and
        it now mentions --spyserver too."""
        stored_config()
        with caplog.at_level("INFO"):
            rc = main(["decode", "--timeout", "1"])
        assert rc == 1
        assert "--device" in caplog.text
        assert "spyserver.host" in caplog.text

    def test_gain_alone_does_not_hijack_a_file_decode(self, caplog):
        """--gain is too weak a signal of intent to reroute a --file run.

        It briefly did, which sent every --file test down the SpyServer
        path. The file decode still runs; the ignored flag is announced.
        """
        with caplog.at_level("INFO"):
            rc = main(["decode", "--file", "nope.wav", "--gain", "5"])
        assert rc == 1
        assert "couldn't find" in caplog.text, "should be a file error, not an SDR one"
        assert "only applies to --spyserver" in caplog.text

    def test_unreadable_config_does_not_kill_a_flag_only_run(
        self, patched_source, monkeypatch, tmp_path
    ):
        """A broken database must not stop a command that needs nothing from it."""
        # importlib, not `import sstv_core.cli.main as cli_main`: this
        # module does `from sstv_core.cli.main import main`, so that form
        # binds the FUNCTION and the setattr lands on the wrong object.
        import importlib

        cli_main = importlib.import_module("sstv_core.cli.main")

        def explode(*a, **k):
            raise RuntimeError("database is on fire")

        monkeypatch.setattr(cli_main, "_read_spyserver_config", explode)
        built = patched_source(_FakeSource())
        rc = main(
            ["decode", "--spyserver", "flag.host:1234", "--band", "40m",
             "--gain", "7", "--timeout", "1"]
        )
        assert rc == 2, "flag-only run must survive a config read failure"
        assert built["kwargs"]["host"] == "flag.host"
        assert built["kwargs"]["frequency_hz"] == 7_171_000


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

    @pytest.mark.parametrize("gain", [-1, 64, 99999])
    def test_obviously_bogus_gain_is_rejected_before_connecting(self, gain, caplog):
        """A cheap pre-flight check, kept so nonsense costs no round trip.

        Unvalidated, -1 raised a bare struct.error (which is NOT a
        ValueError) and 99999 went silently onto the wire as garbage. The
        AUTHORITATIVE range is the device's own maximum_gain_index and is
        enforced after connect -- see tests/sdr/test_source.py -- so this
        message deliberately no longer promises a fixed 0-63.
        """
        with caplog.at_level("INFO"):
            rc = main(["decode", "--spyserver", "host", "--gain", str(gain)])
        assert rc == 1
        assert f"can't set the gain to {gain}" in caplog.text
        assert "once I connect" in caplog.text

    @pytest.mark.parametrize("gain", [0, 63])
    def test_gain_at_the_boundaries_is_accepted(self, gain, patched_source, tmp_path):
        built = patched_source(_FakeSource())
        main(
            ["decode", "--spyserver", "host", "--gain", str(gain), "--timeout", "1",
             "--output", str(tmp_path / "o.png")]
        )
        assert built["kwargs"]["gain"] == gain

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

    def test_a_stall_is_not_reported_as_a_network_problem(
        self, patched_source, caplog
    ):
        """A stall's three lines must not contradict each other.

        The hardcoded detail asserted "that's a network problem" for
        every failure. Once stall became distinct, a stalled stream said
        the network both was and wasn't at fault -- the same collapse
        spec.md:278 exists to prevent, one layer up in the reporting.
        """
        from sstv_core.sdr.spyserver.client import StreamStalledError

        patched_source(_FakeSource(stream_failure=StreamStalledError()))
        with caplog.at_level("INFO"):
            rc = main(["decode", "--spyserver", "host", "--timeout", "1"])

        assert rc == 1
        assert "network problem" not in caplog.text, (
            "a stall is not a network problem -- the connection is fine"
        )
        # The load-bearing part survives: still explicitly not a weak signal.
        assert "weak signal" in caplog.text
        assert "silent" in caplog.text.lower()

    def test_a_disconnect_still_names_the_network(self, patched_source, caplog):
        """The original detail was right for this case; keep it."""
        patched_source(
            _FakeSource(
                stream_failure=SpyServerError(
                    "The stream dropped: the server closed the connection.",
                    suggested_action="Check the network, then try again.",
                )
            )
        )
        with caplog.at_level("INFO"):
            rc = main(["decode", "--spyserver", "host", "--timeout", "1"])

        assert rc == 1
        assert "network problem" in caplog.text
        assert "weak signal" in caplog.text

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


class TestListeningLevel:
    """A quiet band and a deaf receiver must not read the same (issue #90).

    The RMS figures are the ones measured on an Airspy HF+ against WWV
    10 MHz: 0.000231 at the old default gain of 0, and 0.004929/0.006439
    at the gains that produced a clean carrier.
    """

    def test_the_listening_level_is_reported_while_listening(
        self, patched_source, caplog
    ):
        """Otherwise the operator watches a blank terminal for 120 seconds."""
        patched_source(_FakeSource(rms=0.006439))
        with caplog.at_level("INFO"):
            main(["decode", "--spyserver", "host", "--timeout", "1"])
        assert "listening_level" in caplog.text

    def test_a_deaf_receiver_reads_as_silent_not_as_a_bare_number(
        self, patched_source, caplog
    ):
        """"0.000231" tells a human nothing; "silent" does."""
        patched_source(_FakeSource(rms=0.000231))
        with caplog.at_level("INFO"):
            main(["decode", "--spyserver", "host", "--timeout", "1"])
        assert "'signal_level': 'silent'" in caplog.text

    def test_a_working_level_reads_as_healthy(self, patched_source, caplog):
        patched_source(_FakeSource(rms=0.006439))
        with caplog.at_level("INFO"):
            main(["decode", "--spyserver", "host", "--timeout", "1"])
        assert "'signal_level': 'healthy'" in caplog.text

    def test_the_level_event_does_not_shadow_the_log_severity(self):
        """`level` is JSONFormatter's own key for INFO/WARNING/ERROR.

        Naming the audio reading `level` overwrote the severity with
        "silent", so a screen reader parsing severity got the wrong field.
        """
        import json
        import logging

        from sstv_core.cli.main import JSONFormatter

        record = logging.LogRecord(
            "t", logging.INFO, "p", 1, "listening_level", None, None
        )
        record.event_type = "listening_level"
        record.data = {"signal_level": "silent", "rms": 0.000231}
        payload = json.loads(JSONFormatter().format(record))
        assert payload["level"] == "INFO"
        assert payload["signal_level"] == "silent"

    def test_a_deaf_timeout_says_so_and_points_at_the_gain(
        self, patched_source, caplog
    ):
        """The message that cost the live session its first decode."""
        patched_source(_FakeSource(rms=0.000231, resolved_gain=6))
        with caplog.at_level("INFO"):
            rc = main(["decode", "--spyserver", "host", "--timeout", "1"])
        assert rc == 2
        assert "barely heard anything at all" in caplog.text
        assert "deaf receiver rather than a quiet band" in caplog.text
        assert "Raise --gain" in caplog.text
        assert "I used 6" in caplog.text

    def test_a_healthy_timeout_keeps_the_original_wording(
        self, patched_source, caplog
    ):
        """When the level is fine, "raise the gain" would be bad advice."""
        patched_source(_FakeSource(rms=0.006439))
        with caplog.at_level("INFO"):
            rc = main(["decode", "--spyserver", "host", "--timeout", "1"])
        assert rc == 2
        assert "didn't hear an SSTV transmission before the timeout." in caplog.text
        assert "Raise --gain" not in caplog.text
        assert "Check the frequency and the band" in caplog.text

    def test_the_two_timeouts_do_not_read_the_same(self, patched_source, caplog):
        """The whole defect in one assertion."""
        patched_source(_FakeSource(rms=0.000231))
        with caplog.at_level("INFO"):
            main(["decode", "--spyserver", "host", "--timeout", "1"])
        deaf = caplog.text
        caplog.clear()

        patched_source(_FakeSource(rms=0.006439))
        with caplog.at_level("INFO"):
            main(["decode", "--spyserver", "host", "--timeout", "1"])
        healthy = caplog.text

        assert deaf != healthy

    def test_the_heartbeat_does_not_spam_a_long_listen(self, patched_source, caplog):
        """A line per progress callback is unusable over ten minutes.

        The loop polls every 100 ms, so an unthrottled report would emit
        ~10 lines a second. The heartbeat is on a 5-second timer.
        """
        patched_source(_FakeSource(rms=0.006439))
        with caplog.at_level("INFO"):
            main(["decode", "--spyserver", "host", "--timeout", "3"])
        emitted = caplog.text.count("listening_level")
        assert emitted <= 3, f"{emitted} level lines in a 3-second listen is spam"


class TestMonitorStreamFlag:
    """--monitor-stream reaches the source, and its absence changes nothing."""

    def test_flag_is_passed_through_as_monitor_port(self, patched_source, stored_config):
        stored_config(host="airspy.local")
        built = patched_source(_FakeSource())
        main(["decode", "--spyserver", "host:5555", "--monitor-stream", "8781",
              "--timeout", "0"])
        assert built["kwargs"]["monitor_port"] == 8781

    def test_absent_flag_means_no_monitor(self, patched_source, stored_config):
        """The default decode path must be untouched by this feature."""
        stored_config(host="airspy.local")
        built = patched_source(_FakeSource())
        main(["decode", "--spyserver", "host:5555", "--timeout", "0"])
        assert built["kwargs"]["monitor_port"] is None

    def test_port_zero_is_passed_through_not_treated_as_absent(
        self, patched_source, stored_config
    ):
        """0 means "pick a port for me", which is a different request from
        no flag at all. A falsy check here would silently disable the tee."""
        stored_config(host="airspy.local")
        built = patched_source(_FakeSource())
        main(["decode", "--spyserver", "host:5555", "--monitor-stream", "0",
              "--timeout", "0"])
        assert built["kwargs"]["monitor_port"] == 0


class TestDeafReceiverAdvice:
    """"Raise the gain" is only useful when there is gain left to raise.

    A live 20m session on 2026-08-17 sat at 0.0004 RMS for 90 seconds and
    was told to raise --gain from 8 -- which is this Airspy's maximum. The
    advice was unfollowable, and it aimed the operator at the receiver
    while the real fault was upstream of it. WWV at the same gain measured
    0.019, so the chain was fine and the band was empty.
    """

    def test_below_the_ceiling_still_says_raise_the_gain(self):
        from sstv_core.cli.main import _deaf_receiver_action

        action = _deaf_receiver_action(SimpleNamespace(resolved_gain=6, max_gain=8))
        assert "Raise --gain" in action
        assert "6" in action

    def test_at_the_ceiling_stops_recommending_the_knob(self):
        from sstv_core.cli.main import _deaf_receiver_action

        action = _deaf_receiver_action(SimpleNamespace(resolved_gain=8, max_gain=8))
        assert "Raise --gain" not in action
        assert "maximum" in action
        assert "antenna" in action

    def test_at_the_ceiling_names_the_gain_it_actually_used(self):
        from sstv_core.cli.main import _deaf_receiver_action

        action = _deaf_receiver_action(SimpleNamespace(resolved_gain=8, max_gain=8))
        assert "8" in action

    def test_an_unknown_ceiling_keeps_the_old_advice(self):
        """A device that never reported DeviceInfo gives nothing to compare."""
        from sstv_core.cli.main import _deaf_receiver_action

        action = _deaf_receiver_action(SimpleNamespace(resolved_gain=4, max_gain=None))
        assert "Raise --gain" in action

    def test_an_unresolved_gain_does_not_print_none(self):
        """Failing before connect() leaves resolved_gain unset."""
        from sstv_core.cli.main import _deaf_receiver_action

        action = _deaf_receiver_action(SimpleNamespace(resolved_gain=None, max_gain=None))
        assert "None" not in action
        assert "Raise --gain" in action
