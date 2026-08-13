"""SpyServer client: connection, tuning, and IQ streaming.

The protocol has no error message type. A rejected or out-of-range tune
is never reported -- the server clamps or ignores it and the next
ClientSync reflects reality. So every setting is verified against the
sync that follows it, and never assumed.
"""

from __future__ import annotations

import logging
import socket
import threading
from collections.abc import Callable
from typing import Protocol

import numpy as np

from sstv_core.sdr.spyserver import protocol as p

logger = logging.getLogger(__name__)


class _Socket(Protocol):
    """The socket surface this client uses, so tests can supply a fake."""

    def connect(self, address: tuple[str, int], /) -> None: ...
    def sendall(self, data: bytes, /) -> None: ...
    def recv(self, size: int, /) -> bytes: ...
    def settimeout(self, timeout: float | None, /) -> None: ...
    def close(self) -> None: ...

#: The demodulator cannot resample upward into a passband that isn't
#: there, so this is a hard floor on the IQ rate we can accept.
MINIMUM_IQ_RATE = 48000


class SpyServerError(Exception):
    """A SpyServer failure, carrying copy fit for the operator."""

    def __init__(self, message: str, suggested_action: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.suggested_action = suggested_action


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
    """Pick the lowest IQ rate that still clears the audio rate.

    Decimation is a stage index, not a rate:
    rate = maximum_sample_rate / (1 << stage). A lower rate means less
    data over the network and less CPU, so the lowest qualifying stage
    wins. The demodulator resamples whatever arrives down to 48 kHz, so
    the rate need not divide evenly -- it only has to be high enough to
    still contain the passband.
    """
    best: tuple[int, int] | None = None
    for stage in range(min_iq_decimation, decimation_stage_count + 1):
        rate = maximum_sample_rate >> stage
        if rate < target_rate:
            continue
        if best is None or rate < best[1]:
            best = (stage, rate)
    if best is None:
        raise SpyServerError(
            f"This server's sample rate never gets above {target_rate} Hz "
            f"(its maximum is {maximum_sample_rate} Hz), so there's no usable "
            f"rate for me to work with.",
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
        tune_timeout_sec: float = 5.0,
        sock_factory: Callable[[], _Socket] | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._client_name = client_name
        self._stall_timeout_sec = stall_timeout_sec
        self._tune_timeout_sec = tune_timeout_sec
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
        # Retune handshake. Once the receive thread starts it owns the
        # socket's read side, so tune() publishes a request here and waits
        # for the loop to hand back the ClientSync it saw.
        self._tune_lock = threading.Lock()
        self._tune_pending: int | None = None
        self._tune_seen: p.ClientSync | None = None
        self._tune_answered = threading.Event()
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

    def _verify_tuned(self, sync: p.ClientSync, frequency_hz: int) -> None:
        """Reject a tune the server silently clamped."""
        actual = sync.iq_center_frequency
        if actual != frequency_hz:
            raise SpyServerError(
                f"I asked for {frequency_hz} Hz but the server put me on {actual} Hz.",
                suggested_action=(
                    "This server may be locked to one frequency by its owner."
                ),
            )

    def tune(self, frequency_hz: int) -> None:
        sync = self._client_sync
        if sync is None:
            raise SpyServerError(
                "I'm not connected yet.", suggested_action="Connect first."
            )
        low, high = sync.minimum_iq_center_frequency, sync.maximum_iq_center_frequency
        if not (low <= frequency_hz <= high):
            raise SpyServerError(
                f"{frequency_hz} Hz is outside this server's range "
                f"({low}-{high} Hz).",
                suggested_action=f"Pick a frequency between {low} and {high} Hz.",
            )

        # While streaming, the receive thread is the only reader. Register
        # the request before sending so the reply cannot arrive first.
        if self._streaming:
            with self._tune_lock:
                self._tune_pending = frequency_hz
                self._tune_seen = None
                self._tune_answered.clear()
            self._send(p.build_set_setting(p.SETTING_IQ_FREQUENCY, frequency_hz))
            if not self._tune_answered.wait(self._tune_timeout_sec):
                with self._tune_lock:
                    self._tune_pending = None
                raise SpyServerError(
                    f"I asked for {frequency_hz} Hz but the server didn't confirm "
                    f"the change.",
                    suggested_action=(
                        "Check the connection is still up, then try tuning again."
                    ),
                )
            with self._tune_lock:
                seen = self._tune_seen
                self._tune_pending = None
            if seen is None:
                # The loop ended before any ClientSync arrived, so it woke
                # us on its way out. Unverified is not tuned.
                raise SpyServerError(
                    f"I asked for {frequency_hz} Hz but the stream ended before "
                    f"the server confirmed the change.",
                    suggested_action=(
                        "Check the connection is still up, then try tuning again."
                    ),
                )
            self._verify_tuned(seen, frequency_hz)
            return

        self._send(p.build_set_setting(p.SETTING_IQ_FREQUENCY, frequency_hz))
        header, body = self._read_message()
        if header.msg_type == p.MSG_CLIENT_SYNC:
            self._client_sync = p.parse_client_sync(body)
            self._verify_tuned(self._client_sync, frequency_hz)
        else:
            raise SpyServerError(
                f"I asked for {frequency_hz} Hz but the server didn't confirm "
                f"the change.",
                suggested_action=(
                    "Check the connection is still up, then try tuning again."
                ),
            )

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
        self._send(p.build_set_setting(p.SETTING_IQ_FORMAT, p.FORMAT_INT16))
        self._send(p.build_set_setting(p.SETTING_IQ_DECIMATION, self._decimation_stage))
        self._send(p.build_set_setting(p.SETTING_STREAMING_MODE, p.STREAM_MODE_IQ_ONLY))
        self._send(p.build_set_setting(p.SETTING_GAIN, gain))
        # Digital gain semantics differ across reference clients; send 0 and do
        # any gain in our own DSP where it is testable.
        self._send(p.build_set_setting(p.SETTING_IQ_DIGITAL_GAIN, 0))
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
        sync = p.parse_client_sync(body)
        self._client_sync = sync
        with self._tune_lock:
            if self._tune_pending is not None:
                self._tune_seen = sync
                self._tune_answered.set()

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
            self.stream_error = SpyServerError(
                "The stream dropped: the server closed the connection.",
                suggested_action="Check the network, then try again.",
            )
        except SpyServerError as exc:
            self.stream_error = exc
        except (OSError, p.ProtocolError) as exc:
            self.stream_error = SpyServerError(
                f"The stream dropped: {exc}",
                suggested_action="Check the network, then try again.",
            )
        finally:
            # Never leave tune() parked on a stream that has ended.
            self._tune_answered.set()
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
            if not self._ended.wait(timeout=1.0):
                self._close_socket()
            thread.join(timeout=2.0)
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
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass

    def close(self) -> None:
        self.stop_streaming()
        self._close_socket()
        self._sock = None
