"""SpyServer client: connection, tuning, and IQ streaming.

The protocol has no error message type. A rejected or out-of-range tune
is never reported -- the server clamps or ignores it, and a ClientSync
is the only evidence of what actually happened.

Real firmware will not always give us even that. The Airspy HF+ answers
IQ_FREQUENCY with nothing at all (issue #89), so tuning cannot wait on a
confirmation and still work. Requests are sent and checked against
whatever sync later arrives: a contradicting one is a real mistune and
gets reported, while silence is normal and is not an error.
"""

from __future__ import annotations

import logging
import socket
import threading
from collections.abc import Callable
from typing import Protocol

import numpy as np

from sstv_core.sdr.demodulator import SLOWER_THAN_REALTIME_RATES, TARGET_RATE
from sstv_core.sdr.spyserver import protocol as p

logger = logging.getLogger(__name__)


class _Socket(Protocol):
    """The socket surface this client uses, so tests can supply a fake."""

    def connect(self, address: tuple[str, int], /) -> None: ...
    def sendall(self, data: bytes, /) -> None: ...
    def recv(self, size: int, /) -> bytes: ...
    def settimeout(self, timeout: float | None, /) -> None: ...
    def shutdown(self, how: int, /) -> None: ...
    def close(self) -> None: ...

#: The demodulator cannot resample upward into a passband that isn't
#: there, so this is a hard floor on the IQ rate we can accept.
MINIMUM_IQ_RATE = TARGET_RATE

#: Slack for a stream to end on its own before its socket is torn down,
#: and for a woken thread to finish unwinding after it is.
_GRACE_SEC = 1.0


class SpyServerError(Exception):
    """A SpyServer failure, carrying copy fit for the operator."""

    def __init__(self, message: str, suggested_action: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.suggested_action = suggested_action


class StreamStalledError(SpyServerError):
    """The server held the connection open and stopped sending.

    Public and typed so the reporting layer can tell a stall from a
    disconnect without matching on message text. spec.md:278 keeps the
    gap causes distinct because they point at different fixes, and a
    caller that can only see "some SpyServerError" is forced to flatten
    them again -- which is exactly what the CLI did.
    """

    def __init__(self) -> None:
        super().__init__(
            "Connected but silent past the timeout -- the server stopped sending.",
            suggested_action=(
                "The connection is fine, so check the radio end: the receiver, "
                "the antenna, and whether the server still has a device attached."
            ),
        )


class _PeerClosedError(SpyServerError):
    """The server hung up.

    Its operator-facing copy depends on when it happened -- during the
    handshake it's "I couldn't connect", mid-stream it's "the stream
    dropped" -- so the reader raises this and each caller words it.
    """

    def __init__(self) -> None:
        super().__init__(
            "The server closed the connection.",
            suggested_action="Check the server is still up, then try again.",
        )


def choose_decimation_stage(
    maximum_sample_rate: int,
    decimation_stage_count: int,
    min_iq_decimation: int,
    target_rate: int = MINIMUM_IQ_RATE,
) -> tuple[int, int]:
    """Pick the lowest IQ rate the demodulator can keep up with.

    Decimation is a stage index, not a rate:
    rate = maximum_sample_rate / (1 << stage). A lower rate means less
    data over the network and less CPU, so the lowest qualifying stage
    wins. The demodulator resamples fractionally, so the rate need not
    divide evenly into the audio rate -- it only has to clear the floor
    and not be one of the rates that runs slower than realtime.
    """
    best: tuple[int, int] | None = None
    skipped_for_speed = False
    for stage in range(min_iq_decimation, decimation_stage_count + 1):
        rate = maximum_sample_rate >> stage
        if rate < target_rate:
            continue
        if rate in SLOWER_THAN_REALTIME_RATES:
            # Correct output arriving at half speed is no use on a live
            # signal. Every device offering these has a faster stage.
            skipped_for_speed = True
            continue
        if best is None or rate < best[1]:
            best = (stage, rate)
    if best is None and skipped_for_speed:
        # Blaming the floor here would misdirect: the rate cleared it and
        # was skipped for being too slow to keep up.
        raise SpyServerError(
            "The only sample rates this server offers me are ones I can't "
            "decode fast enough to keep up with the signal.",
            suggested_action="Try a different SpyServer.",
        )
    if best is None:
        raise SpyServerError(
            f"I couldn't find a usable sample rate on this server "
            f"(its maximum is {maximum_sample_rate} Hz, and I need at least "
            f"{target_rate} Hz).",
            suggested_action="Try a different SpyServer.",
        )
    return best


class SpyServerClient:
    """One connection to one SpyServer."""

    def __init__(
        self,
        host: str,
        port: int = p.DEFAULT_PORT,
        client_name: str = "SSTeVe",
        stall_timeout_sec: float = 5.0,
        sock_factory: Callable[[], _Socket] | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._client_name = client_name
        self._stall_timeout_sec = stall_timeout_sec
        self._sock_factory = sock_factory or (
            lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        )
        self._sock: _Socket | None = None
        self._device_info: p.DeviceInfo | None = None
        self._client_sync: p.ClientSync | None = None
        self._sample_rate = MINIMUM_IQ_RATE
        self._decimation_stage = 0
        self._on_iq: Callable[[np.ndarray], None] | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._ended = threading.Event()
        self._last_sequence: int | None = None
        # The frequency most recently asked for and not yet seen echoed
        # back. Checked against each arriving ClientSync; see tune().
        self._tune_lock = threading.Lock()
        self._tune_pending: int | None = None
        # Whether any sync has arrived since the pending tune was sent.
        # Without it a stale sync would be mistaken for an answer.
        self._tune_answered = False
        self.dropped_frames = 0
        self.stream_error: SpyServerError | None = None

    @property
    def device_info(self) -> p.DeviceInfo | None:
        return self._device_info

    @property
    def client_sync(self) -> p.ClientSync | None:
        return self._client_sync

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def _streaming(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _require_sock(self) -> _Socket:
        sock = self._sock
        if sock is None:
            raise SpyServerError(
                "I'm not connected yet.", suggested_action="Connect first."
            )
        return sock

    def _recv_exactly(self, size: int) -> bytes:
        sock = self._require_sock()
        buf = b""
        while len(buf) < size:
            chunk = sock.recv(size - len(buf))
            if not chunk:
                raise _PeerClosedError()
            buf += chunk
        return buf

    def _read_message(self) -> tuple[p.MessageHeader, bytes]:
        header = p.parse_message_header(self._recv_exactly(p.HEADER_SIZE))
        body = self._recv_exactly(header.body_size) if header.body_size else b""
        return header, body

    def connect(self) -> None:
        try:
            self._sock = self._sock_factory()
            self._sock.settimeout(self._stall_timeout_sec)
            self._sock.connect((self._host, self._port))
            self._sock.sendall(p.build_hello(self._client_name))
        except SpyServerError:
            raise
        except OSError as exc:
            raise SpyServerError(
                f"I couldn't reach the SpyServer at {self._host}:{self._port}.",
                suggested_action="Check the host and port, and that the server is running.",
            ) from exc

        while self._device_info is None or self._client_sync is None:
            header, body = self._read_message()
            self._check_version(header)
            if header.msg_type == p.MSG_DEVICE_INFO:
                self._device_info = p.parse_device_info(body)
            elif header.msg_type == p.MSG_CLIENT_SYNC:
                self._client_sync = p.parse_client_sync(body)

        stage, rate = choose_decimation_stage(
            self._device_info.maximum_sample_rate,
            self._device_info.decimation_stage_count,
            self._device_info.min_iq_decimation,
        )
        self._decimation_stage = stage
        self._sample_rate = rate

    def _check_version(self, header: p.MessageHeader) -> None:
        theirs, ours = header.protocol_id, p.PROTOCOL_VERSION
        if (theirs >> 24) != (ours >> 24) or ((theirs >> 16) & 0xFF) != (
            (ours >> 16) & 0xFF
        ):
            raise SpyServerError(
                f"This server speaks protocol version {theirs:#x}, and I speak "
                f"{ours:#x}.",
                suggested_action="Try a server running a current SpyServer build.",
            )

    def _mistune_error(self, requested: int, actual: int) -> SpyServerError:
        return SpyServerError(
            f"I asked for {requested} Hz but the server put me on {actual} Hz.",
            suggested_action=(
                "This server may be locked to one frequency by its owner."
            ),
        )

    def tune(self, frequency_hz: int) -> None:
        """Ask the server for a frequency. Does not wait for confirmation.

        Real firmware (Airspy HF+, issue #89) sends no ClientSync in
        answer to IQ_FREQUENCY -- not idle, not streaming. It sends one
        only when streaming is first enabled. Blocking on a confirmation
        this server never sends made tuning impossible, so the request is
        fire-and-return and the check moves to whatever sync does arrive.
        """
        sync = self._client_sync
        if sync is None:
            raise SpyServerError(
                "I'm not connected yet.", suggested_action="Connect first."
            )
        # The range check needs no cooperation from the server, so it is
        # still an immediate error rather than a deferred one.
        low, high = sync.minimum_iq_center_frequency, sync.maximum_iq_center_frequency
        if not (low <= frequency_hz <= high):
            raise SpyServerError(
                f"{frequency_hz} Hz is outside this server's range "
                f"({low}-{high} Hz).",
                suggested_action=f"Pick a frequency between {low} and {high} Hz.",
            )

        # Record before sending: while streaming the receive thread may see
        # the answering sync before sendall() has even returned.
        with self._tune_lock:
            self._tune_pending = frequency_hz
            self._tune_answered = False
        self._send(p.build_set_setting(p.SETTING_IQ_FREQUENCY, frequency_hz))

    def _send(self, data: bytes) -> None:
        self._require_sock().sendall(data)

    def start_streaming(
        self, on_iq: Callable[[np.ndarray], None], gain: int = 0
    ) -> None:
        if self._device_info is None:
            raise SpyServerError(
                "I'm not connected yet.", suggested_action="Connect first."
            )
        self._on_iq = on_iq
        # INT16 has the dynamic range weak-signal HF work wants, but a
        # server can pin the format and ignore the request -- the Airspy
        # HF+ forces UINT8 and sends it regardless (issue #89). Ask for
        # what we will actually receive. The receive loop dispatches on
        # each message's own type either way, so this changes the request
        # rather than the decoding.
        iq_format = self._device_info.forced_iq_format or p.FORMAT_INT16
        self._send(p.build_set_setting(p.SETTING_IQ_FORMAT, iq_format))
        self._send(p.build_set_setting(p.SETTING_IQ_DECIMATION, self._decimation_stage))
        self._send(p.build_set_setting(p.SETTING_STREAMING_MODE, p.STREAM_MODE_IQ_ONLY))
        # Both stages, or the operator's --gain does almost nothing. The
        # comment that stood here promised to do gain "in our own DSP where it
        # is testable" and no such stage was ever written, so digital gain sat
        # pinned at 0. Measured against a live Airspy HF+ (2026-08-19), mean
        # |IQ| over the same signal: 0.0067 at digital gain 0, 0.0436 at 8,
        # 0.147 at 16. Three nights of band recordings were written at the
        # floor and read as a dead antenna.
        self._send(p.build_set_setting(p.SETTING_GAIN, gain))
        self._send(p.build_set_setting(p.SETTING_IQ_DIGITAL_GAIN, gain))
        self._send(p.build_set_setting(p.SETTING_STREAMING_ENABLED, 1))
        # A fresh session starts a fresh sequence. Carrying the previous
        # one over reports a gap that never happened.
        self._last_sequence = None
        self.dropped_frames = 0
        self.stream_error = None
        self._stop.clear()
        self._ended.clear()
        self._thread = threading.Thread(target=self._receive_loop, daemon=True)
        self._thread.start()

    def _note_client_sync(self, body: bytes) -> None:
        """Record a sync. A matching one settles any tune still pending.

        This server batches syncs at stream start -- the stale frequency
        first, then the current one (issue #89). Judging on the first
        would call every such pair a mistune, so a match clears the
        pending tune and anything else is left for _settle_pending_tune()
        to rule on once the batch is over.
        """
        sync = p.parse_client_sync(body)
        self._client_sync = sync
        with self._tune_lock:
            if self._tune_pending is None:
                return
            self._tune_answered = True
            if sync.iq_center_frequency == self._tune_pending:
                self._tune_pending = None

    def _settle_pending_tune(self) -> None:
        """Rule on a tune once the syncs have stopped arriving.

        Called at the first IQ message after a sync, which is where the
        batch ends. A frequency still pending here was contradicted by
        every sync in it, so the server really did put us elsewhere.

        A tune the server has not answered at all is left pending rather
        than judged: this firmware usually says nothing (issue #89), and
        the stale sync from before the request is no evidence about it.
        """
        with self._tune_lock:
            pending = self._tune_pending
            if pending is None or not self._tune_answered:
                return
            self._tune_pending = None
            self._tune_answered = False
            current = self._client_sync
            if current is None or current.iq_center_frequency == pending:
                return
            mismatch = self._mistune_error(pending, current.iq_center_frequency)
        # Reported like any other stream failure: tune() has long since
        # returned, so there is no call left to raise out of.
        logger.warning("SpyServer %s", mismatch.message)
        self._report_stream_error(mismatch)

    def _report_stream_error(self, error: SpyServerError) -> None:
        """Keep the first failure reported, not the last.

        A mistune is followed by the stream ending like any other, and
        "the stream dropped" would otherwise overwrite the reason it
        dropped. The first error is the diagnosis; the rest is fallout.
        """
        if self.stream_error is None:
            self.stream_error = error

    def _receive_loop(self) -> None:
        try:
            while not self._stop.is_set():
                header, body = self._read_message()
                if header.msg_type == p.MSG_CLIENT_SYNC:
                    self._note_client_sync(body)
                    continue
                if header.msg_type not in (
                    p.MSG_UINT8_IQ,
                    p.MSG_INT16_IQ,
                    p.MSG_FLOAT_IQ,
                    p.MSG_INT24_IQ,
                ):
                    continue
                # IQ resuming means the sync batch is over, so whatever
                # tune is still outstanding can now be judged.
                self._settle_pending_tune()
                if self._last_sequence is not None:
                    gap = header.sequence_number - self._last_sequence - 1
                    if gap > 0:
                        self.dropped_frames += gap
                        logger.warning("SpyServer dropped %d frames", gap)
                self._last_sequence = header.sequence_number
                iq = p.iq_bytes_to_complex(body, header.msg_type, header.gain_db)
                if self._on_iq is not None:
                    self._deliver(iq)
        except _PeerClosedError:
            # Mid-stream this is a dropped stream, not the connect-time
            # "server closed" case. The distinction is what stops a lost
            # link from reading as a weak signal.
            self._report_stream_error(
                SpyServerError(
                    "The stream dropped: the server closed the connection.",
                    suggested_action="Check the network, then try again.",
                )
            )
        except SpyServerError as exc:
            self._report_stream_error(exc)
        except TimeoutError:
            # A stall, not a disconnect: the connection is fine and the
            # server simply stopped sending. socket.timeout IS an
            # OSError, so without this branch it fell into the handler
            # below and read as "the stream dropped" -- sending an
            # operator whose antenna relay or upstream SDR hung off to
            # debug a network that was never the problem. spec.md:278
            # keeps the gap causes distinct because the fixes differ.
            self._report_stream_error(StreamStalledError())
        except (OSError, p.ProtocolError) as exc:
            self._report_stream_error(
                SpyServerError(
                    f"The stream dropped: {exc}",
                    suggested_action="Check the network, then try again.",
                )
            )
        finally:
            self._ended.set()

    def _deliver(self, iq: np.ndarray) -> None:
        """Hand a block downstream, turning a decoder blow-up into state.

        Letting the callback's exception escape would kill this thread
        with stream_error unset, so a caller that waits for the end and
        finds no error would read a stream that died on its first block
        as a clean finish.
        """
        on_iq = self._on_iq
        if on_iq is None:
            return
        try:
            on_iq(iq)
        except Exception as exc:
            raise SpyServerError(
                f"I couldn't process the audio coming off this stream: {exc}",
                suggested_action=(
                    "This is a fault on my side, not the radio's. "
                    "Check the log, then start the stream again."
                ),
            ) from exc

    def wait_for_stream_end(self, timeout: float | None = None) -> bool:
        return self._ended.wait(timeout)

    def stop_streaming(self) -> None:
        self._stop.set()
        thread = self._thread
        if self._sock is not None:
            try:
                self._send(p.build_set_setting(p.SETTING_STREAMING_ENABLED, 0))
            except OSError:
                pass
        if thread is not None:
            # A reader parked in recv() never sees the stop flag, so close
            # the socket first to force it to return. Without this the
            # join times out and the thread outlives the call.
            if not self._ended.wait(timeout=_GRACE_SEC):
                self._close_socket()
            # shutdown() should wake the reader immediately, so this budget
            # is slack rather than the expected wait. It still clears the
            # socket timeout, because that is how long the thread needs to
            # notice on its own if shutdown ever fails to interrupt it --
            # a shorter budget turns that fallback into a false alarm.
            thread.join(timeout=self._stall_timeout_sec + _GRACE_SEC)
            if thread.is_alive():
                # Say so through state rather than dropping the handle and
                # reporting success -- a leaked thread that looks stopped is
                # worse than a visible failure.
                logger.error("SpyServer receive thread did not stop")
                raise SpyServerError(
                    "I couldn't stop the receive thread cleanly.",
                    suggested_action=(
                        "The connection may be wedged. Restart SSTeVe if it persists."
                    ),
                )
            self._thread = None

    def _close_socket(self) -> None:
        sock = self._sock
        if sock is None:
            return
        # shutdown() before close(), because the receive thread holds its
        # own reference to this socket and close() alone does not reliably
        # wake a reader already parked in recv() on macOS or BSD -- it
        # stayed blocked until the 5s socket timeout fired, outliving the
        # join and reporting a wedged thread that was merely slow (#89).
        # shutdown() tears down the connection itself, so the parked call
        # returns at once.
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            # Already closed, never connected, or the peer beat us to it.
            pass
        try:
            sock.close()
        except OSError:
            pass

    def close(self) -> None:
        self.stop_streaming()
        self._close_socket()
        self._sock = None
