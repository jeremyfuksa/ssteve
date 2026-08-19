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


class TestShutdownRace:
    """A connection accepted as stop() runs must not outlive the server."""

    def test_a_client_accepted_during_stop_is_dropped(self):
        """Seen in CI on 2026-08-19 as a logging error during teardown.

        `_accept_loop` did four things between `accept()` returning and its
        next `_running` check: set a socket option, build a `_Client`, append
        it under the lock, and start a send thread. A client that arrived in
        that window was registered on a server `stop()` had already drained,
        so both it and its thread survived shutdown -- and the "client
        connected" log line fired late enough to write to a stream pytest had
        closed, printing `ValueError: I/O operation on closed file`.

        Winning that race by timing alone is not reproducible, so this drives
        it directly: hand the loop a live connection and flip `_running` off
        underneath it, which is exactly the state stop() leaves behind.
        """
        srv = AudioMonitorServer(port=0)
        srv.start()
        client_sock = _connect(srv)
        try:
            # One real client, registered normally.
            deadline = time.monotonic() + 2.0
            while not srv._clients and time.monotonic() < deadline:
                time.sleep(0.01)
            assert srv._clients, "fixture connection never registered"

            srv.stop()
            assert srv._clients == [], "stop() left clients behind"

            # Now the window itself: a connection that reaches the loop after
            # _running has gone false. Feed it straight to the accept path.
            left, right = socket.socketpair()
            try:
                # The loop tests _running before calling accept(), so the race
                # is not "stopped before entry" -- it is "stopped while blocked
                # in accept()". The stub flips the flag as it hands back the
                # connection, which is exactly what stop() does underneath a
                # parked accept().
                srv._running = True
                srv._sock = _OneShotAcceptor(
                    right, on_accept=lambda: setattr(srv, "_running", False)
                )
                srv._accept_loop()
                assert srv._clients == [], (
                    "a connection accepted after stop() was registered anyway"
                )
            finally:
                left.close()
                right.close()
        finally:
            client_sock.close()
            srv.stop()


class _OneShotAcceptor:
    """Minimal stand-in for a listening socket: yields one connection, then EOF."""

    def __init__(self, conn: socket.socket, on_accept=None):
        self._conn = conn
        self._served = False
        self._on_accept = on_accept

    def accept(self):
        if self._served:
            raise OSError("listening socket closed")
        self._served = True
        if self._on_accept is not None:
            # Stand in for stop() running while the real loop is parked here.
            self._on_accept()
        return self._conn, ("127.0.0.1", 0)

    def close(self) -> None:
        """No-op: stop() closes whatever is in _sock.

        The stub owns no listening socket, so there is nothing to release.
        """
