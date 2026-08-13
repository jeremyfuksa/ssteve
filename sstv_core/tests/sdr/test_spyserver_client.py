"""SpyServer client: handshake, tuning verification, failure reporting.

Runs against an in-process fake socket. The protocol has no error
message type -- a rejected tune is silent, and the next ClientSync is
the only evidence. Every test here exists because silence would
otherwise look like success.
"""

from __future__ import annotations

import struct
import threading
import time

import numpy as np
import pytest

from sstv_core.sdr.spyserver import protocol as p
from sstv_core.sdr.spyserver.client import (
    SpyServerClient,
    SpyServerError,
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

    def test_silent_mismatch_is_surfaced(self):
        """The server clamps and says nothing; ClientSync is the only truth."""
        script = _handshake() + _message(
            p.MSG_CLIENT_SYNC, _client_sync_bytes(iq_freq=7_171_000)
        )
        client, _ = _client(script)
        client.connect()
        with pytest.raises(SpyServerError, match="7171000|7,171,000|different"):
            client.tune(14_230_000)

    def test_out_of_range_is_refused_before_sending(self):
        client, sock = _client(_handshake())
        client.connect()
        with pytest.raises(SpyServerError, match="range"):
            client.tune(500_000_000)
        assert struct.pack("<II", p.SETTING_IQ_FREQUENCY, 500_000_000) not in sock.sent

    def test_unconfirmed_tune_times_out_rather_than_hanging(self):
        """A tune the server never acknowledges must fail, not block forever.

        The server stays connected and simply says nothing back, so this
        is distinct from the peer hanging up.
        """
        payload = struct.pack("<2h", 1000, 0)
        sock = SilentSocket(
            _handshake() + _message(p.MSG_INT16_IQ, payload, seq=0)
        )
        client = SpyServerClient(
            "example.test", sock_factory=lambda: sock, tune_timeout_sec=0.2
        )
        client.connect()
        client.start_streaming(lambda _: None)
        assert sock.recv_parked.wait(timeout=5.0)

        started = time.monotonic()
        with pytest.raises(SpyServerError, match="didn't confirm|confirm"):
            client.tune(14_230_000)
        assert time.monotonic() - started < 5.0
        client.close()


    def test_tune_fails_when_the_stream_ends_before_confirming(self):
        """The loop waking tune() on its way out is not a confirmation.

        The receive thread is held mid-stream so tune() genuinely takes
        the streaming path, then released so the loop exits while tune()
        is still waiting on its answer.
        """
        payload = struct.pack("<2h", 1000, 0)
        sock = SilentSocket(
            _handshake() + _message(p.MSG_INT16_IQ, payload, seq=0)
        )
        client = SpyServerClient(
            "example.test", sock_factory=lambda: sock, tune_timeout_sec=5.0
        )
        client.connect()
        client.start_streaming(lambda _: None)
        assert sock.recv_parked.wait(timeout=5.0)

        # Release the parked reader shortly after tune() starts waiting, so
        # the loop ends without ever sending a ClientSync.
        threading.Timer(0.2, sock.close).start()
        with pytest.raises(SpyServerError, match="stream ended|confirm"):
            client.tune(14_230_000)


class TestDecimationChoice:
    def test_picks_the_lowest_stage_at_or_above_the_target_rate(self):
        stage, rate = choose_decimation_stage(
            maximum_sample_rate=10_000_000, decimation_stage_count=9, min_iq_decimation=0
        )
        assert rate >= 48000
        assert 0 <= stage <= 9
        # Lower rate means less network traffic and less CPU, so the lowest
        # qualifying stage wins. 10 MHz >> 7 == 78125; >> 8 == 39062 (< 48000).
        assert rate == 78125
        assert stage == 7

    def test_honors_the_minimum_stage(self):
        stage, _ = choose_decimation_stage(
            maximum_sample_rate=10_000_000, decimation_stage_count=9, min_iq_decimation=3
        )
        assert stage >= 3

    def test_raises_when_no_stage_can_reach_the_target(self):
        with pytest.raises(SpyServerError, match="rate"):
            choose_decimation_stage(
                maximum_sample_rate=8000, decimation_stage_count=2, min_iq_decimation=0
            )


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
