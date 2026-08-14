"""SpyServerSource satisfies the contract RXManager already depends on."""

from __future__ import annotations

import socket
import time

import numpy as np
import pytest

from sstv_core.audio.ring_buffer import AudioRingBuffer
from sstv_core.sdr.demodulator import TARGET_RATE
from sstv_core.sdr.source import SpyServerSource
from sstv_core.sdr.spyserver.client import SpyServerError


class FakeClient:
    """Stands in for SpyServerClient; feeds IQ on demand."""

    def __init__(self, sample_rate: int = 192_000) -> None:
        self.sample_rate = sample_rate
        self.connected = False
        self.tuned_to: int | None = None
        self.streaming = False
        self.closed = False
        self.dropped_frames = 0
        self.stream_error: SpyServerError | None = None
        self.gain: int | None = None
        self._on_iq = None

    def connect(self) -> None:
        self.connected = True

    def tune(self, frequency_hz: int) -> None:
        self.tuned_to = frequency_hz

    def start_streaming(self, on_iq, gain: int = 0) -> None:
        self.streaming = True
        self.gain = gain
        self._on_iq = on_iq

    def stop_streaming(self) -> None:
        self.streaming = False

    def close(self) -> None:
        self.stop_streaming()
        self.closed = True

    def feed_tone(self, offset_hz: float = 1500.0, duration: float = 0.2) -> None:
        t = np.arange(int(self.sample_rate * duration)) / self.sample_rate
        self._on_iq(np.exp(2j * np.pi * offset_hz * t).astype(np.complex64))


def _source(client: FakeClient) -> SpyServerSource:
    return SpyServerSource("example.test", frequency_hz=14_230_000, client=client)


class TestContract:
    def test_exposes_the_four_methods_rxmanager_calls(self):
        src = _source(FakeClient())
        for name in (
            "start_input",
            "stop_input",
            "get_input_buffer",
            "get_input_levels",
        ):
            assert callable(getattr(src, name))

    def test_start_input_ignores_device_index(self):
        """RXManager passes device_index by keyword; a network source has none."""
        client = FakeClient()
        src = _source(client)
        src.start_input(device_index=7)
        assert client.connected and client.streaming
        src.stop_input()

    def test_sample_rate_is_always_the_engine_rate(self):
        assert _source(FakeClient()).sample_rate == TARGET_RATE

    def test_buffer_is_none_before_start(self):
        assert _source(FakeClient()).get_input_buffer() is None

    def test_levels_are_zero_before_any_audio(self):
        levels = _source(FakeClient()).get_input_levels()
        assert levels.rms == 0.0
        assert levels.peak == 0.0
        assert levels.is_clipping is False

    def test_rxmanager_accepts_it_without_a_sample_rate_conflict(self):
        """The seam's real test: RXManager builds around it unchanged."""
        from sstv_core.decode.rx_manager import RXManager

        rx = RXManager(stream_manager=_source(FakeClient()), sample_rate=TARGET_RATE)
        assert rx is not None


class TestAudioFlow:
    def test_iq_becomes_audio_in_the_ring_buffer(self):
        client = FakeClient()
        src = _source(client)
        src.start_input()
        client.feed_tone()
        buffer = src.get_input_buffer()
        assert isinstance(buffer, AudioRingBuffer)
        assert len(buffer) > 0
        samples = buffer.pop(len(buffer))
        assert samples.dtype == np.float32
        assert np.max(np.abs(samples)) > 0.01
        src.stop_input()

    def test_buffer_is_built_at_the_engine_rate(self):
        """A buffer mislabelled with the IQ rate would misreport duration."""
        client = FakeClient()
        src = _source(client)
        src.start_input()
        buffer = src.get_input_buffer()
        assert buffer is not None
        assert buffer.sample_rate == TARGET_RATE
        src.stop_input()

    def test_audio_arrives_at_the_engine_rate(self):
        """One second of IQ has to become one second of 48 kHz audio."""
        client = FakeClient()
        src = _source(client)
        src.start_input()
        client.feed_tone(duration=1.0)
        buffer = src.get_input_buffer()
        assert buffer is not None
        # Filter startup transients cost a few samples; the rate is what matters.
        assert abs(len(buffer) - TARGET_RATE) < TARGET_RATE * 0.02

    def test_blocks_are_demodulated_by_one_continuous_demodulator(self):
        """A per-block demodulator would restart filter state and click."""
        whole = FakeClient()
        src_whole = _source(whole)
        src_whole.start_input()
        whole.feed_tone(duration=0.4)
        buf_whole = src_whole.get_input_buffer()
        assert buf_whole is not None
        continuous = buf_whole.pop(len(buf_whole))

        split = FakeClient()
        src_split = _source(split)
        src_split.start_input()
        split.feed_tone(duration=0.2)
        split.feed_tone(duration=0.2)
        buf_split = src_split.get_input_buffer()
        assert buf_split is not None
        blocked = buf_split.pop(len(buf_split))

        n = min(len(continuous), len(blocked))
        assert n > TARGET_RATE // 4
        assert np.allclose(continuous[:n], blocked[:n], atol=1e-6)

    def test_levels_track_delivered_audio(self):
        client = FakeClient()
        src = _source(client)
        src.start_input()
        client.feed_tone()
        levels = src.get_input_levels()
        assert levels.rms > 0.0
        assert levels.peak > 0.0
        src.stop_input()

    def test_tunes_to_the_requested_frequency(self):
        client = FakeClient()
        src = _source(client)
        src.start_input()
        assert client.tuned_to == 14_230_000
        src.stop_input()

    def test_passes_the_configured_gain_through(self):
        client = FakeClient()
        src = SpyServerSource("example.test", gain=12, client=client)
        src.start_input()
        assert client.gain == 12
        src.stop_input()


class _DeviceInfoClient(FakeClient):
    """A client that reports DeviceInfo, like a real server does.

    maximum_gain_index 8 and gain_stage_count 0 are the Airspy HF+'s
    actual numbers (issue #90) -- deliberately non-correlating, because
    code that infers "no gain control" from 0 stages would refuse a radio
    that plainly has 8 gain steps.
    """

    def __init__(self, maximum_gain_index: int = 8, **kwargs) -> None:
        super().__init__(**kwargs)
        from sstv_core.sdr.spyserver.protocol import DeviceInfo

        self.device_info = DeviceInfo(
            device_type=1,
            device_serial=0,
            maximum_sample_rate=768_000,
            maximum_bandwidth=768_000,
            decimation_stage_count=8,
            gain_stage_count=0,
            maximum_gain_index=maximum_gain_index,
            minimum_frequency=0,
            maximum_frequency=31_000_000,
            resolution=16,
            min_iq_decimation=1,
            forced_iq_format=1,
        )


class TestGainAgainstTheDeviceLadder:
    """Gain is per-device, and only DeviceInfo knows the range (issue #90)."""

    def test_default_is_three_quarters_of_the_ladder_not_zero(self):
        """The old default of 0 measured as deaf on real hardware.

        On this device 0.75 * 8 == 6, which is the gain that produced a
        clean 155:1 WWV carrier in the issue's sweep.
        """
        client = _DeviceInfoClient(maximum_gain_index=8)
        src = SpyServerSource("example.test", client=client)
        src.start_input()
        assert client.gain == 6
        assert src.resolved_gain == 6
        src.stop_input()

    def test_an_explicit_gain_still_wins(self):
        client = _DeviceInfoClient(maximum_gain_index=8)
        src = SpyServerSource("example.test", gain=3, client=client)
        src.start_input()
        assert client.gain == 3
        src.stop_input()

    def test_zero_is_honored_when_the_operator_actually_asks_for_it(self):
        """0 is a legal gain. Only "unset" gets derived."""
        client = _DeviceInfoClient(maximum_gain_index=8)
        src = SpyServerSource("example.test", gain=0, client=client)
        src.start_input()
        assert client.gain == 0
        src.stop_input()

    def test_gain_above_the_device_maximum_is_refused_naming_the_real_range(self):
        """20 passed the old device-agnostic 0-63 check on an 8-step radio."""
        client = _DeviceInfoClient(maximum_gain_index=8)
        src = SpyServerSource("example.test", gain=20, client=client)
        with pytest.raises(SpyServerError) as excinfo:
            src.start_input()
        assert "0 to 8" in excinfo.value.message
        assert "0 and 8" in excinfo.value.suggested_action
        # Never started streaming with a gain the device can't take.
        assert client.gain is None

    def test_a_refused_gain_still_tears_the_connection_down(self):
        """Otherwise a rejected gain leaks a socket and a server slot."""
        client = _DeviceInfoClient(maximum_gain_index=8)
        src = SpyServerSource("example.test", gain=20, client=client)
        with pytest.raises(SpyServerError):
            src.start_input()
        assert client.closed

    @pytest.mark.parametrize(
        "maximum,expected", [(8, 6), (63, 47), (1, 1), (2, 2), (0, 0)]
    )
    def test_the_derived_default_never_exceeds_the_ladder(self, maximum, expected):
        """Rounding, not truncation: a 1-step ladder must not collapse to 0."""
        from sstv_core.sdr.source import default_gain_for

        assert default_gain_for(maximum) == expected
        assert default_gain_for(maximum) <= max(maximum, 0)

    def test_a_client_without_device_info_still_runs(self):
        """A server that never reported DeviceInfo leaves nothing to check."""
        client = FakeClient()  # no device_info attribute at all
        src = SpyServerSource("example.test", gain=12, client=client)
        src.start_input()
        assert client.gain == 12
        src.stop_input()

    def test_stop_input_closes_the_client(self):
        client = FakeClient()
        src = _source(client)
        src.start_input()
        src.stop_input()
        assert not client.streaming
        assert client.closed

    def test_stop_input_is_safe_before_start(self):
        """RXManager stops in a finally block, which can run before any start."""
        _source(FakeClient()).stop_input()

    def test_late_iq_after_stop_does_not_reach_the_buffer(self):
        """The receive thread can outlive stop_input() by a block."""
        client = FakeClient()
        src = _source(client)
        src.start_input()
        src.stop_input()
        client.feed_tone()
        buffer = src.get_input_buffer()
        assert buffer is not None
        assert len(buffer) == 0


class TestOverrun:
    def test_a_burst_degrades_like_a_sound_card_overrun(self):
        """Faster-than-realtime IQ must evict and count, not corrupt.

        A real server paces at realtime, but a post-stall catch-up burst can
        outrun the decoder. The ring buffer's own eviction is the whole
        mechanism -- no throttle is built here -- so what this pins is that
        the overflow is visible in dropped_samples rather than silent.
        """
        client = FakeClient()
        src = SpyServerSource("example.test", client=client)
        # A buffer far smaller than the audio about to arrive.
        src.start_input(buffer_size=TARGET_RATE // 2)
        client.feed_tone(duration=2.0)
        buffer = src.get_input_buffer()
        assert buffer is not None
        assert len(buffer) == TARGET_RATE // 2
        assert buffer.dropped_samples > 0


class TestFailureReporting:
    def test_stream_failure_is_exposed(self):
        client = FakeClient()
        src = _source(client)
        src.start_input()
        client.stream_error = SpyServerError("The stream dropped.", "Try again.")
        assert src.stream_failure is not None
        assert "dropped" in src.stream_failure.message.lower()
        src.stop_input()

    def test_stream_failure_survives_stop_input(self):
        """A dropped stream must never read as a weak signal.

        RXManager stops the source before the CLI reports; if the failure
        vanished with the client, TCP trouble would look like bad propagation.
        """
        client = FakeClient()
        src = _source(client)
        src.start_input()
        client.stream_error = SpyServerError("The stream dropped.", "Try again.")
        src.stop_input()
        assert src.stream_failure is not None
        assert "dropped" in src.stream_failure.message.lower()

    def test_dropped_frames_are_exposed(self):
        client = FakeClient()
        src = _source(client)
        src.start_input()
        client.dropped_frames = 4
        assert src.dropped_frames == 4
        src.stop_input()

    def test_dropped_frames_survive_stop_input(self):
        """Same reason as stream_failure: the CLI reports after the stop,
        and a count that reset to zero would hide a lossy link."""
        client = FakeClient()
        src = _source(client)
        src.start_input()
        client.dropped_frames = 4
        src.stop_input()
        assert src.dropped_frames == 4

    def test_time_since_last_iq_grows_before_data(self):
        client = FakeClient()
        src = _source(client)
        src.start_input()
        assert src.seconds_since_last_iq() >= 0.0
        src.stop_input()

    def test_a_wedged_teardown_is_reported_not_raised(self):
        """stop_streaming() can raise; RXManager stops in a finally block.

        Letting that escape would replace a real decode result -- or a real
        decode error -- with a teardown error. Report it, don't throw it.
        """

        class WedgedClient(FakeClient):
            def stop_streaming(self) -> None:
                raise SpyServerError(
                    "I couldn't stop the receive thread cleanly.",
                    "Restart SSTeVe if it persists.",
                )

            def close(self) -> None:
                self.stop_streaming()

        client = WedgedClient()
        src = _source(client)
        src.start_input()
        src.stop_input()  # must not raise
        assert src.stream_failure is not None
        assert "receive thread" in src.stream_failure.message.lower()

    def test_a_real_stream_failure_outranks_a_teardown_failure(self):
        """The operator needs to know the stream dropped, not that the
        wreckage was awkward to clear."""

        class WedgedClient(FakeClient):
            def stop_streaming(self) -> None:
                raise SpyServerError("I couldn't stop the receive thread.", "Restart.")

            def close(self) -> None:
                self.stop_streaming()

        client = WedgedClient()
        src = _source(client)
        src.start_input()
        client.stream_error = SpyServerError("The stream dropped.", "Try again.")
        src.stop_input()
        assert src.stream_failure is not None
        assert "dropped" in src.stream_failure.message.lower()

    def test_start_input_reports_a_connect_failure(self):
        class DeadClient(FakeClient):
            def connect(self) -> None:
                raise SpyServerError("I couldn't reach the SpyServer.", "Check host.")

        src = _source(DeadClient())
        with pytest.raises(SpyServerError):
            src.start_input()

    def test_a_failed_start_leaves_nothing_streaming(self):
        """A half-open connection after a failed tune would leak a socket."""

        class UntunableClient(FakeClient):
            def tune(self, frequency_hz: int) -> None:
                raise SpyServerError("That frequency is out of range.", "Pick another.")

        client = UntunableClient()
        src = _source(client)
        with pytest.raises(SpyServerError):
            src.start_input()
        assert client.closed
        assert not client.streaming

    def test_a_bad_sample_rate_still_closes_the_client(self):
        """The demodulator is built after connect() and tune() succeed.

        USBDemodulator raises ValueError on a non-positive rate, so a server
        reporting one leaves a connected socket open unless the teardown
        covers that path too -- the same leak as a failed tune.
        """

        class ZeroRateClient(FakeClient):
            def __init__(self) -> None:
                super().__init__(sample_rate=0)

        client = ZeroRateClient()
        src = _source(client)
        with pytest.raises(ValueError):
            src.start_input()
        assert client.closed
        assert not client.streaming

    def test_decoder_faults_do_not_silently_stop_the_stream(self):
        """_on_iq must never call stop_streaming: from inside the receive
        thread that self-joins and raises RuntimeError."""
        client = FakeClient()
        src = _source(client)
        src.start_input()

        stops: list[str] = []
        client.stop_streaming = lambda: stops.append("stop")  # type: ignore[method-assign]

        client.feed_tone()
        assert stops == []

    @pytest.mark.parametrize(
        ("name", "error"),
        [
            # An out-of-range gain packs badly. struct.error is NOT a
            # ValueError, so the old (SpyServerError, ValueError) catch
            # missed it entirely.
            ("struct.error", __import__("struct").error("bad gain")),
            # A server that accepts TCP but never sends DeviceInfo: the
            # handshake loop reads until the socket timeout, and raw
            # TimeoutError escapes.
            ("TimeoutError", TimeoutError("timed out")),
            # A header claiming an over-limit body size.
            ("ProtocolError", None),
        ],
    )
    def test_any_failure_after_connect_still_closes_the_client(self, name, error):
        """Teardown must not depend on enumerating exception types.

        Every one of these was measured escaping the old catch and leaking
        a connected socket -- which holds one of the server's client slots
        until the process dies.
        """
        if error is None:
            from sstv_core.sdr.spyserver import protocol as p

            error = p.ProtocolError("body size is over the limit")

        class ExplodingClient(FakeClient):
            def start_streaming(self, on_iq, gain: int = 0) -> None:
                raise error

        client = ExplodingClient()
        src = _source(client)
        with pytest.raises(type(error)):
            src.start_input()
        assert client.closed, f"{name} leaked a connected client"
        assert not client.streaming

    def test_a_failure_during_connect_still_closes_the_client(self):
        """The same guarantee for a failure in connect() itself."""

        class ExplodingClient(FakeClient):
            def connect(self) -> None:
                super().connect()
                raise TimeoutError("timed out waiting for DeviceInfo")

        client = ExplodingClient()
        src = _source(client)
        with pytest.raises(TimeoutError):
            src.start_input()
        assert client.closed


class TestAudioMonitor:
    """The optional monitor tee, and its promise not to cost a decode."""

    def test_absent_by_default(self):
        """The default path must be exactly what it was before the tee."""
        src = _source(FakeClient())
        assert src.audio_monitor is None

    def test_monitor_receives_the_same_audio_as_the_ring_buffer(self):
        client = FakeClient()
        src = SpyServerSource(
            "example.test", frequency_hz=14_230_000, client=client,
            monitor_port=0,
        )
        src.start_input()
        monitor = src.audio_monitor
        assert monitor is not None
        assert monitor.port > 0

        sock = socket.create_connection(("127.0.0.1", monitor.port), timeout=2.0)
        sock.settimeout(2.0)
        deadline = time.monotonic() + 2.0
        while monitor.client_count == 0 and time.monotonic() < deadline:
            time.sleep(0.01)
        try:
            client.feed_tone(duration=0.2)
            received = sock.recv(4096)
            # Real audio, not silence: the tone has to survive to the wire.
            assert len(received) > 0
            samples = np.frombuffer(received, dtype="<i2")
            assert np.max(np.abs(samples)) > 100
        finally:
            sock.close()
            src.stop_input()

    def test_ring_buffer_still_fills_with_a_monitor_attached(self):
        """The decode is the product; the tee must not divert its audio."""
        client = FakeClient()
        src = SpyServerSource(
            "example.test", frequency_hz=14_230_000, client=client,
            monitor_port=0,
        )
        src.start_input()
        client.feed_tone(duration=0.2)
        buffer = src.get_input_buffer()
        assert buffer is not None and len(buffer) > 0
        src.stop_input()

    def test_a_broken_monitor_does_not_stop_the_decode(self):
        """The whole reason the tee swallows its errors."""
        client = FakeClient()
        src = SpyServerSource(
            "example.test", frequency_hz=14_230_000, client=client,
            monitor_port=0,
        )
        src.start_input()

        class ExplodingMonitor:
            def broadcast(self, audio):
                raise RuntimeError("monitor fell over")

            def stop(self):
                pass

        src._monitor = ExplodingMonitor()  # type: ignore[assignment]
        client.feed_tone(duration=0.2)
        buffer = src.get_input_buffer()
        assert buffer is not None and len(buffer) > 0, (
            "a failing monitor stopped audio reaching the decoder"
        )
        src.stop_input()

    def test_stop_input_closes_the_monitor(self):
        client = FakeClient()
        src = SpyServerSource(
            "example.test", frequency_hz=14_230_000, client=client,
            monitor_port=0,
        )
        src.start_input()
        monitor = src.audio_monitor
        assert monitor is not None
        port = monitor.port
        src.stop_input()
        with pytest.raises(OSError):
            socket.create_connection(("127.0.0.1", port), timeout=1.0).close()
