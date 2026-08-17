"""AudioMonitorServer broadcasts audio without ever costing a decode.

The rule under test throughout: the tee runs on the SpyServer client's
receive thread, so it must never block, never raise into the caller, and
never let a slow listener apply backpressure to the radio. Every test here
is a variation on that one rule.
"""

from __future__ import annotations

import socket
import struct
import time

import numpy as np
import pytest

from sstv_core.sdr.audio_stream import AudioMonitorServer


def _connect(server: AudioMonitorServer, timeout: float = 2.0) -> socket.socket:
    """Connect a client and wait until the server has registered it."""
    sock = socket.create_connection(("127.0.0.1", server.port), timeout=timeout)
    sock.settimeout(timeout)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if server.client_count > 0:
            return sock
        time.sleep(0.01)
    sock.close()
    raise AssertionError("server never registered the client")


def _recv_exactly(sock: socket.socket, count: int) -> bytes:
    chunks: list[bytes] = []
    got = 0
    while got < count:
        chunk = sock.recv(count - got)
        if not chunk:
            break
        chunks.append(chunk)
        got += len(chunk)
    return b"".join(chunks)


@pytest.fixture
def server():
    srv = AudioMonitorServer(port=0)
    srv.start()
    yield srv
    srv.stop()


class TestLifecycle:
    def test_start_binds_a_port(self, server):
        assert server.port > 0

    def test_stop_is_idempotent(self, server):
        server.stop()
        server.stop()

    def test_port_zero_picks_a_free_port(self):
        a = AudioMonitorServer(port=0)
        b = AudioMonitorServer(port=0)
        a.start()
        b.start()
        try:
            assert a.port != b.port
        finally:
            a.stop()
            b.stop()


class TestBroadcast:
    def test_audio_reaches_a_connected_client(self, server):
        sock = _connect(server)
        try:
            # Full-scale positive and negative, so the int16 conversion is
            # checked at both rails rather than only near zero.
            server.broadcast(np.array([1.0, -1.0, 0.0], dtype=np.float32))
            data = _recv_exactly(sock, 6)
            assert struct.unpack("<3h", data) == (32767, -32767, 0)
        finally:
            sock.close()

    def test_samples_beyond_unity_clip_rather_than_wrap(self, server):
        sock = _connect(server)
        try:
            # Without an explicit clip these wrap to large negatives and the
            # listener hears a crack on every overdriven block.
            server.broadcast(np.array([2.0, -2.0], dtype=np.float32))
            data = _recv_exactly(sock, 4)
            assert struct.unpack("<2h", data) == (32767, -32767)
        finally:
            sock.close()

    def test_two_clients_both_receive(self, server):
        a = _connect(server)
        b = socket.create_connection(("127.0.0.1", server.port), timeout=2.0)
        b.settimeout(2.0)
        deadline = time.monotonic() + 2.0
        while server.client_count < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        try:
            server.broadcast(np.array([0.5], dtype=np.float32))
            assert len(_recv_exactly(a, 2)) == 2
            assert len(_recv_exactly(b, 2)) == 2
        finally:
            a.close()
            b.close()


class TestNeverCostsADecode:
    def test_broadcast_with_no_listener_is_a_noop(self, server):
        server.broadcast(np.ones(128, dtype=np.float32))

    def test_broadcast_before_start_does_not_raise(self):
        # The source builds the server before start_input succeeds; a
        # broadcast arriving in that window must be harmless.
        srv = AudioMonitorServer(port=0)
        srv.broadcast(np.ones(16, dtype=np.float32))

    def test_broadcast_after_stop_does_not_raise(self, server):
        server.stop()
        server.broadcast(np.ones(16, dtype=np.float32))

    def test_empty_block_is_a_noop(self, server):
        server.broadcast(np.array([], dtype=np.float32))

    def test_a_client_that_vanishes_mid_stream_does_not_raise(self, server):
        sock = _connect(server)
        sock.close()
        # The send fails somewhere in here; the caller must not see it.
        for _ in range(50):
            server.broadcast(np.ones(512, dtype=np.float32))

    def test_a_stalled_client_drops_samples_instead_of_blocking(self, server):
        """The decisive test: a listener that never reads must not stall
        the radio. Backpressure here would starve the decoder's ring
        buffer and cost images."""
        sock = _connect(server)
        try:
            # Far more than any socket buffer will hold, never read.
            started = time.monotonic()
            for _ in range(400):
                server.broadcast(np.ones(4096, dtype=np.float32))
            elapsed = time.monotonic() - started
            # Generous: the point is "returns promptly", not a benchmark.
            assert elapsed < 5.0, f"broadcast blocked for {elapsed:.1f}s"
            assert server.dropped_blocks > 0, "expected drops for a stalled client"
        finally:
            sock.close()
