"""SpyServer client: handshake, tuning verification, failure reporting.

Runs against an in-process fake socket. The protocol has no error
message type -- a rejected tune is silent, and the next ClientSync is
the only evidence. Every test here exists because silence would
otherwise look like success.
"""

from __future__ import annotations

import socket
import struct
import threading
import time

import numpy as np
import pytest

from sstv_core.sdr.demodulator import SLOWER_THAN_REALTIME_RATES
from sstv_core.sdr.spyserver import protocol as p
from sstv_core.sdr.spyserver.client import (
    SpyServerClient,
    SpyServerError,
    StreamStalledError,
    choose_decimation_stage,
)


def _device_info_bytes(
    max_rate: int = 10_000_000,
    stages: int = 9,
    min_decim: int = 0,
    forced_format: int = 0,
    min_freq: int = 1_000_000,
    max_freq: int = 30_000_000,
) -> bytes:
    return struct.pack(
        "<12I", 3, 0xDEADBEEF, max_rate, 8_000_000, stages, 1, 49,
        min_freq, max_freq, 8, min_decim, forced_format,
    )


def _client_sync_bytes(iq_freq: int = 14_230_000, can_control: int = 1) -> bytes:
    return struct.pack(
        "<9I", can_control, 20, iq_freq, iq_freq, iq_freq,
        1_000_000, 30_000_000, 1_000_000, 30_000_000,
    )


def _message(message_type: int, body: bytes, seq: int = 0) -> bytes:
    return struct.pack(
        "<IIIII", p.PROTOCOL_VERSION, message_type, 1, seq, len(body)
    ) + body


def _handshake() -> bytes:
    return _message(p.MSG_DEVICE_INFO, _device_info_bytes()) + _message(
        p.MSG_CLIENT_SYNC, _client_sync_bytes()
    )


class FakeSocket:
    """Scripted server: hands back queued bytes, records what was sent."""

    def __init__(self, script: bytes = b"") -> None:
        self._script = script
        self._pos = 0
        self.sent = b""
        self.closed = False
        self._lock = threading.Lock()

    def connect(self, address) -> None:
        pass

    def sendall(self, data: bytes) -> None:
        with self._lock:
            self.sent += data

    def recv(self, size: int) -> bytes:
        with self._lock:
            if self._pos >= len(self._script):
                return b""  # peer closed
            chunk = self._script[self._pos : self._pos + size]
            self._pos += len(chunk)
            return chunk

    def settimeout(self, timeout) -> None:
        pass

    def shutdown(self, how) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class SilentSocket(FakeSocket):
    """A server that stops talking mid-stream without ever closing.

    The realistic hang: TCP still open, no data, no FIN. Models a wedged
    server or a black-holing path. recv() parks until close() releases
    it, which is what a real socket does when another thread closes the
    fd underneath a blocked reader.
    """

    def __init__(self, script: bytes = b"") -> None:
        super().__init__(script)
        self._released = threading.Event()
        self.recv_parked = threading.Event()

    def recv(self, size: int) -> bytes:
        with self._lock:
            if self._pos < len(self._script):
                chunk = self._script[self._pos : self._pos + size]
                self._pos += len(chunk)
                return chunk
        self.recv_parked.set()
        self._released.wait(timeout=30.0)
        return b""

    def close(self) -> None:
        self.closed = True
        self._released.set()


class UninterruptibleByCloseSocket(FakeSocket):
    """A socket that close() does NOT wake, the way BSD really behaves.

    SilentSocket releases its parked reader on close(), which is the
    assumption that hid issue #89: on macOS a close() from another thread
    left the reader blocked until the socket timeout fired. Only
    shutdown() interrupts it. This models that, so a client relying on
    close() alone is held until the timeout and fails the test.

    The waits are bounded so a failing test times out rather than hanging.
    """

    def __init__(self, script: bytes = b"", timeout_sec: float = 5.0) -> None:
        super().__init__(script)
        self._shutdown = threading.Event()
        self._timeout_sec = timeout_sec
        self.recv_parked = threading.Event()
        self.shutdown_calls: list[int] = []

    def recv(self, size: int) -> bytes:
        with self._lock:
            if self._pos < len(self._script):
                chunk = self._script[self._pos : self._pos + size]
                self._pos += len(chunk)
                return chunk
        self.recv_parked.set()
        # Only shutdown() releases early; otherwise this is the socket
        # timeout elapsing, which is what made the bug look like a wedge.
        if self._shutdown.wait(timeout=self._timeout_sec):
            return b""
        raise TimeoutError("timed out")

    def shutdown(self, how: int) -> None:
        self.shutdown_calls.append(how)
        self._shutdown.set()

    def close(self) -> None:
        self.closed = True  # deliberately does not wake a parked recv


class InterleavingSocket(FakeSocket):
    """A socket with no whole-message atomicity, like a real one.

    FakeSocket holds its lock across the entire recv, so two threads can
    never split a message between them. A real socket offers no such
    guarantee: the kernel hands bytes to whichever thread asks. This
    yields mid-read so a header taken by one thread can be followed by a
    body taken by another -- the corruption defect C is about.

    Delivery pauses at ``gate_at`` until ``release()``, which pins the
    stream mid-flight so a retune happens while IQ is genuinely in
    motion rather than racing the end of the script.
    """

    def __init__(self, script: bytes, gate_at: int) -> None:
        super().__init__(script)
        self._gate_at = gate_at
        self._gate = threading.Event()

    def release(self) -> None:
        self._gate.set()

    def recv(self, size: int) -> bytes:
        with self._lock:
            if self._pos >= len(self._script):
                return b""
            if self._pos >= self._gate_at and not self._gate.is_set():
                gated = True
            else:
                gated = False
                chunk = self._script[self._pos : self._pos + size]
                self._pos += len(chunk)
        if gated:
            self._gate.wait(timeout=10.0)
            with self._lock:
                chunk = self._script[self._pos : self._pos + size]
                self._pos += len(chunk)
        time.sleep(0)  # scheduler yield mid-message
        return chunk


def _client(script: bytes, **kwargs) -> tuple[SpyServerClient, FakeSocket]:
    sock = FakeSocket(script)
    client = SpyServerClient("example.test", sock_factory=lambda: sock, **kwargs)
    return client, sock


class TestHandshake:
    def test_connect_sends_hello_and_stores_server_state(self):
        client, sock = _client(_handshake())
        client.connect()
        cmd_type, _ = struct.unpack("<II", sock.sent[:8])
        assert cmd_type == p.CMD_HELLO
        assert client.device_info is not None
        assert client.device_info.maximum_sample_rate == 10_000_000
        assert client.client_sync is not None
        assert client.client_sync.can_control == 1

    def test_version_mismatch_is_rejected(self):
        body = _device_info_bytes()
        bad = struct.pack("<IIIII", 0x01000000, p.MSG_DEVICE_INFO, 1, 0, len(body)) + body
        client, _ = _client(bad)
        with pytest.raises(SpyServerError, match="version"):
            client.connect()

    def test_immediate_close_is_reported_not_hung(self):
        client, _ = _client(b"")
        with pytest.raises(SpyServerError, match="closed|reach"):
            client.connect()


class TestTuning:
    def test_tune_sends_frequency_and_accepts_matching_sync(self):
        script = _handshake() + _message(
            p.MSG_CLIENT_SYNC, _client_sync_bytes(iq_freq=14_230_000)
        )
        client, sock = _client(script)
        client.connect()
        client.tune(14_230_000)
        assert struct.pack("<II", p.SETTING_IQ_FREQUENCY, 14_230_000) in sock.sent

    def test_tune_returns_promptly_when_the_server_never_answers(self):
        """Real firmware sends no sync for IQ_FREQUENCY (issue #89).

        The Airspy HF+ answers the tune command with nothing at all, so
        anything that waits for confirmation cannot tune this radio.
        """
        client, sock = _client(_handshake())
        client.connect()
        started = time.monotonic()
        client.tune(14_230_000)
        elapsed = time.monotonic() - started
        assert elapsed < 1.0, f"tune() blocked for {elapsed:.1f}s with no answer"
        assert struct.pack("<II", p.SETTING_IQ_FREQUENCY, 14_230_000) in sock.sent

    def test_a_silent_server_is_not_treated_as_an_error(self):
        """No answer is this firmware's normal behavior, not a failure."""
        payload = struct.pack("<2h", 1000, 0)
        script = _handshake() + b"".join(
            _message(p.MSG_INT16_IQ, payload, seq=i) for i in range(4)
        )
        client, _ = _client(script)
        client.connect()
        received: list[np.ndarray] = []
        client.start_streaming(received.append)
        client.tune(14_230_000)
        client.wait_for_stream_end(timeout=5.0)
        # The stream carries on; the only error is the scripted disconnect.
        assert len(received) == 4
        assert client.stream_error is not None
        assert "dropped" in client.stream_error.message.lower()

    def test_the_stream_survives_a_tune_the_server_ignores(self):
        """Tuning must not disturb IQ delivery when the server stays quiet."""
        payload = struct.pack("<64h", *([1000] * 64))
        blocks = 40
        script = _handshake() + b"".join(
            _message(p.MSG_INT16_IQ, payload, seq=i) for i in range(blocks)
        )
        client, _ = _client(script)
        client.connect()
        received: list[np.ndarray] = []
        client.start_streaming(received.append)
        client.tune(7_171_000)
        client.wait_for_stream_end(timeout=5.0)
        assert len(received) == blocks
        assert client.dropped_frames == 0

    def test_out_of_range_is_refused_before_sending(self):
        client, sock = _client(_handshake())
        client.connect()
        with pytest.raises(SpyServerError, match="range"):
            client.tune(500_000_000)
        assert struct.pack("<II", p.SETTING_IQ_FREQUENCY, 500_000_000) not in sock.sent

    def test_tune_returns_promptly_against_a_wedged_server(self):
        """A server that goes silent mid-stream must not stall a retune.

        This is the case that hung against real hardware: the reader is
        parked with nothing arriving, and tuning has to stay usable.
        """
        payload = struct.pack("<2h", 1000, 0)
        sock = SilentSocket(_handshake() + _message(p.MSG_INT16_IQ, payload, seq=0))
        client = SpyServerClient("example.test", sock_factory=lambda: sock)
        client.connect()
        client.start_streaming(lambda _: None)
        assert sock.recv_parked.wait(timeout=5.0)

        started = time.monotonic()
        client.tune(14_230_000)
        elapsed = time.monotonic() - started
        assert elapsed < 1.0, f"tune() blocked for {elapsed:.1f}s against a wedged server"
        client.close()

    def test_teardown_is_quiet_after_a_tune_the_server_ignored(self):
        """issue #89: a wedged tune also made stop_streaming() raise.

        That was downstream of tune() blocking. With tuning no longer
        waiting, teardown should be clean.
        """
        payload = struct.pack("<2h", 1000, 0)
        sock = SilentSocket(_handshake() + _message(p.MSG_INT16_IQ, payload, seq=0))
        client = SpyServerClient("example.test", sock_factory=lambda: sock)
        client.connect()
        client.start_streaming(lambda _: None)
        assert sock.recv_parked.wait(timeout=5.0)
        client.tune(14_230_000)
        client.close()  # must not raise


class TestBatchedSyncs:
    """issue #89: at stream start this server sends the stale sync, then the new one."""

    def test_a_stale_sync_before_the_real_one_is_not_a_mistune(self):
        payload = struct.pack("<2h", 1000, 0)
        script = (
            _handshake()
            # Exactly the observed order: the old frequency, then the one
            # our pre-streaming tune asked for.
            + _message(p.MSG_CLIENT_SYNC, _client_sync_bytes(iq_freq=100_000_000))
            + _message(p.MSG_CLIENT_SYNC, _client_sync_bytes(iq_freq=14_230_000))
            + _message(p.MSG_INT16_IQ, payload, seq=0)
        )
        client, _ = _client(script)
        client.connect()
        client.tune(14_230_000)
        client.start_streaming(lambda _: None)
        client.wait_for_stream_end(timeout=5.0)
        assert client.stream_error is not None
        assert "put me on" not in client.stream_error.message

    def test_a_mistune_is_still_caught_when_it_arrives_second(self):
        payload = struct.pack("<2h", 1000, 0)
        script = (
            _handshake()
            + _message(p.MSG_CLIENT_SYNC, _client_sync_bytes(iq_freq=100_000_000))
            + _message(p.MSG_CLIENT_SYNC, _client_sync_bytes(iq_freq=7_171_000))
            + _message(p.MSG_INT16_IQ, payload, seq=0)
        )
        client, _ = _client(script)
        client.connect()
        client.tune(14_230_000)
        client.start_streaming(lambda _: None)
        client.wait_for_stream_end(timeout=5.0)
        assert client.stream_error is not None
        assert "7171000" in client.stream_error.message


class TestForcedFormat:
    def test_a_pinned_format_is_requested_rather_than_int16(self):
        """issue #89: the Airspy HF+ forces UINT8 and ignores our request."""
        info = _device_info_bytes(forced_format=p.FORMAT_UINT8)
        script = _message(p.MSG_DEVICE_INFO, info) + _message(
            p.MSG_CLIENT_SYNC, _client_sync_bytes()
        )
        client, sock = _client(script)
        client.connect()
        client.start_streaming(lambda _: None)
        client.wait_for_stream_end(timeout=5.0)
        assert struct.pack("<II", p.SETTING_IQ_FORMAT, p.FORMAT_UINT8) in sock.sent
        assert struct.pack("<II", p.SETTING_IQ_FORMAT, p.FORMAT_INT16) not in sock.sent

    def test_int16_is_still_requested_when_nothing_is_pinned(self):
        client, sock = _client(_handshake())
        client.connect()
        client.start_streaming(lambda _: None)
        client.wait_for_stream_end(timeout=5.0)
        assert struct.pack("<II", p.SETTING_IQ_FORMAT, p.FORMAT_INT16) in sock.sent


class TestDecimationChoice:
    def test_picks_the_lowest_stage_at_or_above_the_target_rate(self):
        """An Airspy R2: lowest rate wins, since it costs the least."""
        stage, rate = choose_decimation_stage(
            maximum_sample_rate=10_000_000, decimation_stage_count=9, min_iq_decimation=0
        )
        assert rate >= 48000
        assert 0 <= stage <= 9
        # 10 MHz >> 7 == 78125; >> 8 == 39062, below the 48 kHz floor. There
        # is no divisibility requirement -- 78125 is not a multiple of 48000
        # and the demodulator resamples it anyway.
        assert (stage, rate) == (7, 78125)

    def test_honors_the_minimum_stage(self):
        stage, _ = choose_decimation_stage(
            maximum_sample_rate=10_000_000, decimation_stage_count=9, min_iq_decimation=3
        )
        assert stage >= 3

    def test_skips_rates_that_cannot_run_in_realtime(self):
        """625000 and 312500 demodulate correctly but at ~0.5x realtime.

        This fixture stops at stage 5, so the lowest rate by arithmetic
        alone is 312500. Taking it would hand the decoder correct audio
        too late to use, so the next fastest stage wins instead.
        """
        stage, rate = choose_decimation_stage(
            maximum_sample_rate=10_000_000, decimation_stage_count=5, min_iq_decimation=0
        )
        assert rate not in SLOWER_THAN_REALTIME_RATES
        assert (stage, rate) == (3, 1_250_000)

    def test_never_returns_a_too_slow_rate_for_any_airspy_r2_stage_count(self):
        for stages in range(10):
            try:
                _, rate = choose_decimation_stage(
                    maximum_sample_rate=10_000_000,
                    decimation_stage_count=stages,
                    min_iq_decimation=0,
                )
            except SpyServerError:
                continue
            assert rate not in SLOWER_THAN_REALTIME_RATES, (
                f"stage_count={stages} selected {rate} Hz"
            )

    def test_raises_when_no_stage_can_reach_the_target(self):
        with pytest.raises(SpyServerError, match="rate"):
            choose_decimation_stage(
                maximum_sample_rate=8000, decimation_stage_count=2, min_iq_decimation=0
            )

    def test_a_too_slow_only_server_is_not_blamed_on_the_floor(self):
        """625000 clears 48 kHz, so "I need at least 48000" would misdirect.

        No real device lands here -- it takes a server offering stage 4 of
        a 10 MHz radio and nothing else -- but the wrong sentence would
        send someone hunting a rate problem that isn't there.
        """
        with pytest.raises(SpyServerError, match="fast enough|keep up") as caught:
            choose_decimation_stage(
                maximum_sample_rate=10_000_000,
                decimation_stage_count=4,
                min_iq_decimation=4,
            )
        assert "48000" not in caught.value.message


class TestStreamFailures:
    def test_sequence_gap_counts_dropped_frames(self):
        payload = struct.pack("<2h", 1000, 0)
        script = (
            _handshake()
            + _message(p.MSG_INT16_IQ, payload, seq=0)
            + _message(p.MSG_INT16_IQ, payload, seq=5)  # gap: 1-4 lost
        )
        client, _ = _client(script)
        client.connect()
        received: list[np.ndarray] = []
        client.start_streaming(received.append)
        client.wait_for_stream_end(timeout=5.0)
        assert client.dropped_frames == 4
        assert len(received) == 2

    def test_disconnect_mid_stream_is_recorded(self):
        payload = struct.pack("<2h", 1000, 0)
        script = _handshake() + _message(p.MSG_INT16_IQ, payload, seq=0)
        client, _ = _client(script)
        client.connect()
        client.start_streaming(lambda _: None)
        client.wait_for_stream_end(timeout=5.0)
        assert client.stream_error is not None
        assert "dropped" in client.stream_error.message.lower()

    def test_gain_in_high_bits_is_applied_to_delivered_iq(self):
        payload = struct.pack("<2h", 16384, 0)
        gained_type = (20 << 16) | p.MSG_INT16_IQ
        script = _handshake() + _message(gained_type, payload, seq=0)
        client, _ = _client(script)
        client.connect()
        received: list[np.ndarray] = []
        client.start_streaming(received.append)
        client.wait_for_stream_end(timeout=5.0)
        assert len(received) == 1
        assert received[0][0].real == pytest.approx(0.5 * 10.0, rel=1e-3)

    def test_a_second_session_does_not_inherit_the_first_sequence(self):
        payload = struct.pack("<2h", 1000, 0)
        client, _ = _client(_handshake())
        client.connect()
        client._sock = FakeSocket(_message(p.MSG_INT16_IQ, payload, seq=0))
        client.start_streaming(lambda _: None)
        client.wait_for_stream_end(timeout=5.0)
        assert client.dropped_frames == 0

        # A reconnected server restarts its own numbering, so the second
        # session opens above where the first left off. Without a reset
        # the difference reads as frames that were never sent.
        client._sock = FakeSocket(_message(p.MSG_INT16_IQ, payload, seq=40))
        client.start_streaming(lambda _: None)
        client.wait_for_stream_end(timeout=5.0)
        assert client.dropped_frames == 0


class TestThreadLifecycle:
    """Defect A: a thread that outlives stop_streaming() while reporting success."""

    def test_stop_streaming_does_not_abandon_a_parked_thread(self):
        payload = struct.pack("<2h", 1000, 0)
        sock = SilentSocket(_message(p.MSG_INT16_IQ, payload, seq=0))
        client = SpyServerClient("example.test", sock_factory=lambda: sock)
        client._sock = sock
        client._device_info = p.parse_device_info(_device_info_bytes())
        client._client_sync = p.parse_client_sync(_client_sync_bytes())
        client._decimation_stage = 0

        client.start_streaming(lambda _: None)
        assert sock.recv_parked.wait(timeout=5.0), "never reached the blocking recv"
        thread = client._thread
        assert thread is not None

        started = time.monotonic()
        client.stop_streaming()
        elapsed = time.monotonic() - started

        assert elapsed < 5.0, f"stop_streaming took {elapsed:.1f}s"
        assert not thread.is_alive(), "receive thread outlived stop_streaming()"
        assert client._thread is None


class TestParkedReaderTeardown:
    """issue #89: close() alone left the reader blocked until the timeout."""

    def _streaming_client(
        self, sock: UninterruptibleByCloseSocket
    ) -> SpyServerClient:
        client = SpyServerClient(
            "example.test", sock_factory=lambda: sock, stall_timeout_sec=5.0
        )
        client.connect()
        client.start_streaming(lambda _: None)
        assert sock.recv_parked.wait(timeout=5.0), "never reached the blocking recv"
        return client

    def test_stop_streaming_interrupts_a_parked_reader(self):
        payload = struct.pack("<2h", 1000, 0)
        sock = UninterruptibleByCloseSocket(
            _handshake() + _message(p.MSG_INT16_IQ, payload, seq=0)
        )
        client = self._streaming_client(sock)
        thread = client._thread
        assert thread is not None

        started = time.monotonic()
        client.stop_streaming()
        elapsed = time.monotonic() - started

        # The whole bug: this took ~3s and raised, because it waited out
        # the join instead of interrupting the reader.
        assert elapsed < 2.0, f"stop_streaming took {elapsed:.2f}s"
        assert not thread.is_alive(), "receive thread survived stop_streaming()"
        assert client._thread is None
        assert sock.shutdown_calls, "close() alone will not wake a parked recv"

    def test_close_is_quiet_with_a_parked_reader(self):
        payload = struct.pack("<2h", 1000, 0)
        sock = UninterruptibleByCloseSocket(
            _handshake() + _message(p.MSG_INT16_IQ, payload, seq=0)
        )
        client = self._streaming_client(sock)
        started = time.monotonic()
        client.close()  # must not raise
        assert time.monotonic() - started < 2.0

    def test_a_stalled_stream_is_still_reported_as_a_stall(self):
        """Interrupting teardown must not relabel a genuine stall."""
        payload = struct.pack("<2h", 1000, 0)
        sock = UninterruptibleByCloseSocket(
            _handshake() + _message(p.MSG_INT16_IQ, payload, seq=0),
            timeout_sec=0.2,
        )
        client = SpyServerClient(
            "example.test", sock_factory=lambda: sock, stall_timeout_sec=0.2
        )
        client.connect()
        client.start_streaming(lambda _: None)
        assert client.wait_for_stream_end(timeout=5.0)
        assert isinstance(client.stream_error, StreamStalledError)
        client.close()


class TestCallbackFailure:
    """Defect B: a decoder exception that reads as a clean end of stream."""

    def test_callback_exception_is_recorded_not_silent(self):
        payload = struct.pack("<2h", 1000, 0)
        script = (
            _handshake()
            + _message(p.MSG_INT16_IQ, payload, seq=0)
            + _message(p.MSG_INT16_IQ, payload, seq=1)
        )
        client, _ = _client(script)
        client.connect()

        def boom(_: np.ndarray) -> None:
            raise ValueError("decoder blew up")

        client.start_streaming(boom)
        assert client.wait_for_stream_end(timeout=5.0)
        assert client.stream_error is not None, (
            "a stream that died on block one reported a clean end"
        )
        assert "decoder blew up" in str(client.stream_error)

    def test_callback_failure_is_distinguishable_from_a_network_drop(self):
        payload = struct.pack("<2h", 1000, 0)
        script = _handshake() + _message(p.MSG_INT16_IQ, payload, seq=0)

        client, _ = _client(script)
        client.connect()
        client.start_streaming(lambda _: None)
        client.wait_for_stream_end(timeout=5.0)
        network = client.stream_error

        client2, _ = _client(script)
        client2.connect()

        def boom(_: np.ndarray) -> None:
            raise ValueError("decoder blew up")

        client2.start_streaming(boom)
        client2.wait_for_stream_end(timeout=5.0)
        decoder = client2.stream_error

        assert network is not None and decoder is not None
        assert network.message != decoder.message
        assert "dropped" in network.message.lower()
        assert "process" in decoder.message.lower()


class TestRetuneRace:
    """Defect C: tune() and the receive loop reading one socket concurrently."""

    def test_retune_while_streaming_loses_no_frames(self):
        payload = struct.pack("<64h", *([1000] * 64))
        blocks = 200
        script = (
            b"".join(
                _message(p.MSG_INT16_IQ, payload, seq=i) for i in range(blocks)
            )
            + _message(p.MSG_CLIENT_SYNC, _client_sync_bytes(iq_freq=7_100_000))
            + b"".join(
                _message(p.MSG_INT16_IQ, payload, seq=i)
                for i in range(blocks, blocks * 2)
            )
        )

        # Hold the stream partway through the first half so the retune
        # lands while IQ is genuinely in flight, not after the script ran
        # out. Both threads are then live on one socket at once, which is
        # the only condition under which the race can show up.
        first_half = len(_message(p.MSG_INT16_IQ, payload, seq=0)) * blocks
        gate_at = first_half // 2

        for trial in range(10):
            sock = InterleavingSocket(script, gate_at=gate_at)
            client = SpyServerClient("example.test", sock_factory=lambda s=sock: s)
            client._sock = sock
            client._device_info = p.parse_device_info(_device_info_bytes())
            client._client_sync = p.parse_client_sync(_client_sync_bytes())
            client._decimation_stage = 0

            received: list[np.ndarray] = []
            client.start_streaming(received.append)
            threading.Timer(0.05, sock.release).start()
            client.tune(7_100_000)
            client.wait_for_stream_end(timeout=10.0)

            assert client.stream_error is not None
            assert "dropped" in client.stream_error.message.lower(), (
                f"trial {trial}: framing corrupted -- {client.stream_error.message}"
            )
            assert len(received) == blocks * 2, (
                f"trial {trial}: got {len(received)} of {blocks * 2} blocks; "
                "tune() ate frames off the shared socket"
            )
            assert client.dropped_frames == 0, (
                f"trial {trial}: {client.dropped_frames} phantom drops"
            )

    def test_silent_mismatch_is_surfaced_while_streaming(self):
        """The clamp check must hold on the retune path, not just at connect.

        Retuning mid-stream is the documented normal path, and it is the
        one where a clamped frequency is least visible: IQ keeps flowing,
        the images keep decoding, and they are of the wrong band. The
        non-streaming test cannot cover this -- it exercises the other
        branch entirely.
        """
        payload = struct.pack("<64h", *([1000] * 64))
        blocks = 50
        script = (
            b"".join(_message(p.MSG_INT16_IQ, payload, seq=i) for i in range(blocks))
            # The server clamps to a frequency we did not ask for and says
            # nothing about it. This sync is the only evidence.
            + _message(p.MSG_CLIENT_SYNC, _client_sync_bytes(iq_freq=7_171_000))
            + b"".join(
                _message(p.MSG_INT16_IQ, payload, seq=i)
                for i in range(blocks, blocks * 2)
            )
        )
        gate_at = len(_message(p.MSG_INT16_IQ, payload, seq=0)) * blocks // 2

        sock = InterleavingSocket(script, gate_at=gate_at)
        client = SpyServerClient("example.test", sock_factory=lambda: sock)
        client._sock = sock
        client._device_info = p.parse_device_info(_device_info_bytes())
        client._client_sync = p.parse_client_sync(_client_sync_bytes())
        client._decimation_stage = 0

        client.start_streaming(lambda _: None)
        threading.Timer(0.05, sock.release).start()
        client.tune(14_230_000)
        client.wait_for_stream_end(timeout=10.0)

        # tune() has already returned, so a clamp cannot be raised out of
        # it. It surfaces the way other stream failures do.
        assert client.stream_error is not None
        assert "7171000" in client.stream_error.message
        assert "14230000" in client.stream_error.message


class TestStall:
    """spec.md:269 -- stall is 'Connected but silent past timeout'.

    It must stay distinct from a disconnect. spec.md:278 keeps three gap
    causes apart because they point at different fixes; collapsing stall
    into "the stream dropped" sends an operator whose antenna relay hung
    off to debug a network that is fine.
    """

    class TimingOutSocket(FakeSocket):
        """A server that holds the connection open and says nothing.

        What a real socket does once settimeout() is set: recv raises
        socket.timeout rather than parking forever or returning b"".
        """

        def recv(self, size: int) -> bytes:
            with self._lock:
                if self._pos < len(self._script):
                    chunk = self._script[self._pos : self._pos + size]
                    self._pos += len(chunk)
                    return chunk
            raise socket.timeout("timed out")

    def _client(self, sock):
        client = SpyServerClient("example.test", sock_factory=lambda: sock)
        client._sock = sock
        client._device_info = p.parse_device_info(_device_info_bytes())
        client._client_sync = p.parse_client_sync(_client_sync_bytes())
        client._decimation_stage = 0
        return client

    def test_stall_is_reported_in_the_specs_words(self):
        payload = struct.pack("<2h", 1000, 0)
        sock = self.TimingOutSocket(_message(p.MSG_INT16_IQ, payload, seq=0))
        client = self._client(sock)

        client.start_streaming(lambda _: None)
        client.wait_for_stream_end(timeout=5.0)

        assert client.stream_error is not None
        message = client.stream_error.message
        assert "silent" in message.lower(), message
        assert "dropped" not in message.lower(), (
            "a stall must not be reported as a dropped stream"
        )
        assert client.stream_error.suggested_action

    def test_stall_and_disconnect_are_different_errors(self):
        """The distinction spec.md:278 requires, asserted directly."""
        payload = struct.pack("<2h", 1000, 0)

        stalled = self._client(
            self.TimingOutSocket(_message(p.MSG_INT16_IQ, payload, seq=0))
        )
        stalled.start_streaming(lambda _: None)
        stalled.wait_for_stream_end(timeout=5.0)

        dropped = self._client(FakeSocket(_message(p.MSG_INT16_IQ, payload, seq=0)))
        dropped.start_streaming(lambda _: None)
        dropped.wait_for_stream_end(timeout=5.0)

        assert stalled.stream_error is not None
        assert dropped.stream_error is not None
        assert stalled.stream_error.message != dropped.stream_error.message
        assert (
            stalled.stream_error.suggested_action
            != dropped.stream_error.suggested_action
        ), "the two point at different fixes, so they need different advice"


class TestDigitalGain:
    """The --gain flag has to reach the samples, not just the analog stage."""

    def test_gain_sets_both_the_analog_and_the_digital_stage(self):
        """issue: --gain moved only SETTING_GAIN, leaving digital gain at 0.

        Measured against a live Airspy HF+ on 2026-08-19, mean |IQ| over the
        same signal: digital gain 0 gave 0.0067, gain 8 gave 0.0436, gain 16
        gave 0.147. Pinning it at 0 cost roughly 22 dB of the signal the
        operator asked for, and WWV 10 MHz read 'silent' at 0.000433 where
        the same run with digital gain applied read 'healthy' at 0.006324.

        Three nights of band recordings were written at that level and read
        as a dead antenna.
        """
        sock = FakeSocket(_handshake())
        client = SpyServerClient("example.test", sock_factory=lambda: sock)
        client.connect()

        client.start_streaming(lambda _: None, gain=8)

        assert struct.pack("<II", p.SETTING_GAIN, 8) in sock.sent, (
            "analog gain was not sent"
        )
        assert struct.pack("<II", p.SETTING_IQ_DIGITAL_GAIN, 8) in sock.sent, (
            "digital gain was not sent -- the samples stay at the server's floor"
        )
        client.close()

    def test_gain_zero_is_still_gain_zero(self):
        """Asking for no gain must not become an implicit default."""
        sock = FakeSocket(_handshake())
        client = SpyServerClient("example.test", sock_factory=lambda: sock)
        client.connect()

        client.start_streaming(lambda _: None, gain=0)

        assert struct.pack("<II", p.SETTING_IQ_DIGITAL_GAIN, 0) in sock.sent
        client.close()
