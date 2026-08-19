"""Broadcast demodulated audio to listeners over TCP.

Lets an operator hear the band the decoder is hearing -- the same audio,
from the same demodulator, without a second connection to the SpyServer
(which serves one client at a time).

The hard constraint shapes everything here: `broadcast()` is called from
SpyServerSource._on_iq, which runs on the SpyServer client's receive
thread. That thread must keep consuming IQ or the stream stalls and the
decode dies. So broadcast() only appends to a bounded per-client queue and
returns; a sender thread does the socket writes. A listener that stops
reading loses samples -- it never applies backpressure to the radio.

Wire format: raw little-endian signed 16-bit mono PCM at the demodulator's
output rate (TARGET_RATE, 48 kHz). No header, no framing -- the consumer
knows the rate out of band. Audio monitoring is a diagnostic; the decode is
the product, and nothing in this module may endanger it.
"""

from __future__ import annotations

import logging
import socket
import threading
from collections import deque

import numpy as np

logger = logging.getLogger(__name__)

#: Blocks held per client before the oldest are dropped. At 48 kHz a block
#: is whatever one IQ callback produced -- order 1024-8192 samples, so this
#: is a few seconds of slack. Deep enough to ride out a browser's GC pause,
#: shallow enough that a dead listener can't grow the process without bound.
MAX_QUEUED_BLOCKS = 64

#: Full-scale for signed 16-bit. 32767 rather than 32768 so +1.0 and -1.0
#: map symmetrically and neither rail wraps.
INT16_SCALE = 32767


class _Client:
    """One connected listener and its pending audio."""

    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self.queue: deque[bytes] = deque(maxlen=MAX_QUEUED_BLOCKS)
        self.wake = threading.Event()
        self.alive = True


class AudioMonitorServer:
    """TCP server broadcasting int16 PCM to every connected listener.

    Not a general-purpose server: it never reads from its clients, and it
    drops audio rather than ever making the caller wait.
    """

    def __init__(self, port: int = 0, host: str = "127.0.0.1") -> None:
        """Bind on `port` when started; 0 lets the OS choose a free one.

        Defaults to loopback. This is an unauthenticated feed of whatever
        the radio hears, so it does not get offered to the network unless
        the caller explicitly asks for it.
        """
        self._host = host
        self._requested_port = port
        self._sock: socket.socket | None = None
        self._clients: list[_Client] = []
        self._lock = threading.Lock()
        self._running = False
        self._accept_thread: threading.Thread | None = None
        self._port = 0
        self._dropped_blocks = 0

    @property
    def port(self) -> int:
        """The bound port, or 0 before start()."""
        return self._port

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    @property
    def dropped_blocks(self) -> int:
        """Blocks discarded because a listener wasn't keeping up.

        Non-zero means someone heard a gap. It never means the decode was
        affected -- dropping here is what protects it.
        """
        return self._dropped_blocks

    def start(self) -> None:
        """Bind, listen, and accept clients in the background."""
        if self._running:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self._host, self._requested_port))
        sock.listen(8)
        # Bounded, so stop() can't hang forever waiting on accept().
        sock.settimeout(0.5)
        self._sock = sock
        self._port = sock.getsockname()[1]
        self._running = True
        self._accept_thread = threading.Thread(
            target=self._accept_loop, name="audio-monitor-accept", daemon=True
        )
        self._accept_thread.start()
        logger.info("Audio monitor listening on %s:%d", self._host, self._port)

    def _accept_loop(self) -> None:
        while self._running:
            sock = self._sock
            if sock is None:
                return
            try:
                conn, addr = sock.accept()
            except TimeoutError:
                continue
            except OSError:
                # Socket closed under us by stop(); that is the exit path.
                return
            # stop() may have run between accept() returning and here. Taking
            # the connection anyway registers a client on a stopped server and
            # starts a send thread nothing will join -- and the log line below
            # then fires during interpreter teardown, writing to a stream the
            # test harness has already closed ("I/O operation on closed file").
            if not self._running:
                try:
                    conn.close()
                except OSError:
                    pass
                return
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            client = _Client(conn)
            with self._lock:
                self._clients.append(client)
            threading.Thread(
                target=self._send_loop, args=(client,),
                name="audio-monitor-send", daemon=True,
            ).start()
            logger.info("Audio monitor client connected from %s", addr)

    def _send_loop(self, client: _Client) -> None:
        """Drain one client's queue onto its socket.

        Runs off the radio's thread on purpose: sendall() can block for as
        long as the listener's window stays full, and that wait must never
        be imposed on the caller of broadcast().
        """
        while self._running and client.alive:
            if not client.queue:
                # Timeout rather than a bare wait so shutdown is prompt.
                client.wake.wait(0.2)
                client.wake.clear()
                continue
            try:
                chunk = client.queue.popleft()
            except IndexError:
                continue
            try:
                client.sock.sendall(chunk)
            except OSError:
                break
        client.alive = False
        try:
            client.sock.close()
        except OSError:
            pass
        with self._lock:
            if client in self._clients:
                self._clients.remove(client)

    def broadcast(self, audio: np.ndarray) -> None:
        """Queue one block of float32 audio for every listener.

        Called from the SpyServer receive thread. Appends and returns --
        no socket I/O, no blocking, and no exception ever escapes. When a
        client's queue is full the oldest block is dropped: a stalled
        listener loses audio, the radio does not lose time.
        """
        try:
            if not self._running or len(audio) == 0:
                return
            with self._lock:
                clients = list(self._clients)
            if not clients:
                return

            pcm = self._to_pcm16(audio)
            for client in clients:
                if len(client.queue) == client.queue.maxlen:
                    self._dropped_blocks += 1
                # deque(maxlen=) discards the oldest itself; the count
                # above is only so the drop is observable.
                client.queue.append(pcm)
                client.wake.set()
        except Exception:
            # Deliberately swallowing: this runs on the thread that keeps
            # the SpyServer stream alive. A monitoring bug must never
            # surface there and cost an image.
            logger.debug("Audio monitor broadcast failed", exc_info=True)

    @staticmethod
    def _to_pcm16(audio: np.ndarray) -> bytes:
        """float32 in [-1, 1] to little-endian int16 bytes.

        The demodulator already clips to +/-1.0, but this clips again
        rather than trusting it: an unclipped 2.0 wraps to a large negative
        int16 and the listener hears a crack instead of loud audio.
        """
        clipped = np.clip(audio, -1.0, 1.0)
        return bytes((clipped * INT16_SCALE).astype("<i2").tobytes())

    def stop(self) -> None:
        """Close the listening socket and every client. Safe to call twice."""
        self._running = False
        sock = self._sock
        self._sock = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        with self._lock:
            clients = list(self._clients)
            self._clients.clear()
        for client in clients:
            client.alive = False
            client.wake.set()
            try:
                client.sock.close()
            except OSError:
                pass
        thread = self._accept_thread
        self._accept_thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
