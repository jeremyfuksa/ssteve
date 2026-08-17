"""SpyServerSource: a network IQ source shaped like an audio input.

RXManager depends on four methods -- start_input, stop_input,
get_input_buffer, get_input_levels -- and never imports sounddevice.
Implementing those is the whole seam; the decode stack is unchanged.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Protocol

import numpy as np

from sstv_core.audio.ring_buffer import AudioRingBuffer
from sstv_core.audio.stream_manager import AudioLevels
from sstv_core.sdr.audio_stream import AudioMonitorServer
from sstv_core.sdr.demodulator import TARGET_RATE, USBDemodulator
from sstv_core.sdr.spyserver.client import SpyServerClient, SpyServerError

logger = logging.getLogger(__name__)

CLIP_THRESHOLD = 0.99

#: Fraction of the device's own gain ladder to use when the operator names
#: no gain. A hardcoded index cannot be right for every radio -- the ladder
#: length is per-device -- so the default is a position on it instead.
#:
#: 0.75 is calibrated on the Airspy HF+ (issue #90), which reports
#: maximum_gain_index 8. It puts the default at index 6, measured on WWV
#: 10 MHz as the cleanest of the sweep:
#:
#:     gain=0  rms=0.000231  peak/mean=  4.5   (deaf -- indistinguishable
#:                                              from noise, and the old
#:                                              default)
#:     gain=4  rms=0.000721  peak/mean=158.8
#:     gain=6  rms=0.004929  peak/mean=154.6   <- 0.75 * 8
#:     gain=8  rms=0.006439  peak/mean=118.9   (peak/mean falling: the
#:                                              front end is starting to
#:                                              compress)
#:
#: Below the top of the ladder on purpose. Headroom matters more than raw
#: level on HF, where a nearby signal has to be able to rise without
#: driving the front end into compression.
DEFAULT_GAIN_FRACTION = 0.75


def default_gain_for(maximum_gain_index: int) -> int:
    """Derive the gain to use when the operator named none.

    Rounds rather than truncates so short ladders don't collapse to 0 --
    the exact failure issue #90 reported. Never returns above the maximum.
    """
    if maximum_gain_index <= 0:
        return 0
    return min(maximum_gain_index, round(maximum_gain_index * DEFAULT_GAIN_FRACTION))


class _Client(Protocol):
    """The client surface this source uses, so tests can supply a fake.

    The three attributes are read-only properties, not settable variables:
    this source only ever reads them, and SpyServerClient exposes
    sample_rate as a property, which a settable declaration would reject.
    """

    @property
    def sample_rate(self) -> int: ...
    @property
    def dropped_frames(self) -> int: ...
    @property
    def stream_error(self) -> SpyServerError | None: ...
    @property
    def device_info(self) -> object | None: ...

    def connect(self) -> None: ...
    def tune(self, frequency_hz: int) -> None: ...
    def start_streaming(
        self, on_iq: Callable[[np.ndarray], None], gain: int = 0
    ) -> None: ...
    def stop_streaming(self) -> None: ...
    def close(self) -> None: ...


class SpyServerSource:
    """Feeds demodulated SpyServer audio into a ring buffer.

    Args:
        host: SpyServer hostname or IP.
        port: SpyServer port.
        frequency_hz: Frequency to tune, in Hz.
        gain: Device RF/IF gain index, or None to derive one from the
            device's own maximum_gain_index once connected.
        stall_timeout_sec: Seconds without IQ before the stream counts as stalled.
        client: Injected client (tests); a real one is built when omitted.

    """

    def __init__(
        self,
        host: str,
        port: int = 5555,
        frequency_hz: int = 14_230_000,
        gain: int | None = None,
        stall_timeout_sec: float = 5.0,
        client: _Client | None = None,
        monitor_port: int | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._frequency_hz = frequency_hz
        self._gain = gain
        # None means no tee at all -- the default path is unchanged. 0 asks
        # the OS for a free port, which is what the tests use.
        self._monitor_port = monitor_port
        self._monitor: AudioMonitorServer | None = None
        # What we actually sent, once connect() has told us the ladder.
        # Read by the CLI so it can report the derived number rather than
        # "None".
        self.resolved_gain: int | None = None
        self._stall_timeout_sec = stall_timeout_sec
        self._client = client
        self._demod: USBDemodulator | None = None
        self._buffer: AudioRingBuffer | None = None
        self._levels = AudioLevels()
        self._last_iq_at = 0.0
        self._running = False
        # Latched locally rather than read off the client on demand: the
        # client is dropped at teardown and its stream_error is cleared by
        # the next start_streaming(), but RXManager stops the source before
        # the CLI reports. A failure that vanished on stop would let a lost
        # TCP link read as a weak signal.
        self._failure: SpyServerError | None = None
        self._dropped_frames = 0

    @property
    def sample_rate(self) -> int:
        """Always the engine rate -- the demodulator resamples to it."""
        return TARGET_RATE

    @property
    def audio_monitor(self) -> AudioMonitorServer | None:
        """The live-audio tee, or None when monitoring wasn't asked for.

        Exposed so the caller can report the bound port -- with
        monitor_port=0 the OS picks it, and it isn't known until start.
        """
        return self._monitor

    @property
    def stream_failure(self) -> SpyServerError | None:
        """The stream's failure, if it had one.

        Prefers a live client's error so a drop is seen the moment it
        happens, and falls back to the latched one after teardown.
        """
        live = getattr(self._client, "stream_error", None)
        if live is not None:
            self._failure = live
        return self._failure

    @property
    def dropped_frames(self) -> int:
        """Frames the server dropped, latched like stream_failure.

        Same reason: the client handle is gone after stop_input, and a count
        that reset to zero at teardown would hide a lossy link from the
        report that comes after it.
        """
        live = getattr(self._client, "dropped_frames", None)
        if live is not None:
            self._dropped_frames = int(live)
        return self._dropped_frames

    def _resolve_gain(self, client: _Client) -> int:
        """Settle the gain index against the device's own ladder.

        Only correct after connect(): maximum_gain_index arrives in
        DeviceInfo, so nothing before that knows the real range. The CLI
        keeps a cheap sanity check on the flag for obvious nonsense, but
        this is the authoritative one -- a device-agnostic 0-63 bound
        accepted 20 on a radio whose ladder stops at 8 (issue #90).

        gain_stage_count is deliberately not consulted: this device
        reports 0 stages alongside a maximum_gain_index of 8, so the two
        do not correlate and treating a 0 there as "no gain control"
        would refuse a working radio.
        """
        info = getattr(client, "device_info", None)
        maximum = getattr(info, "maximum_gain_index", None)
        if not isinstance(maximum, int):
            # A client that never reports DeviceInfo (a fake, or a server
            # that skipped it) leaves nothing to validate against. Sending
            # an explicit gain unchanged beats refusing to run.
            return self._gain if self._gain is not None else 0

        if self._gain is None:
            gain = default_gain_for(maximum)
            logger.info(
                "No gain given; using %d of this device's 0-%d range.", gain, maximum
            )
            return gain

        if not 0 <= self._gain <= maximum:
            raise SpyServerError(
                f"I can't set the gain to {self._gain} -- this device's range "
                f"is 0 to {maximum}.",
                suggested_action=f"Use --gain between 0 and {maximum}.",
            )
        return self._gain

    def seconds_since_last_iq(self) -> float:
        if not self._last_iq_at:
            return 0.0
        return time.monotonic() - self._last_iq_at

    def start_input(
        self,
        device_index: int | None = None,
        callback: Callable | None = None,
        buffer_size: int = AudioRingBuffer.DEFAULT_MAX_SAMPLES,
    ) -> None:
        """Connect, tune, and start filling the ring buffer.

        `device_index` and `callback` are accepted and ignored: RXManager
        passes device_index by keyword, and a network source has no device
        to select. The signature matches AudioStreamManager.start_input so
        the duck type is drop-in.
        """
        client = self._client
        if client is None:
            fresh: _Client = SpyServerClient(
                self._host, self._port, stall_timeout_sec=self._stall_timeout_sec
            )
            client = fresh
            self._client = fresh
        self._failure = None
        self._dropped_frames = 0
        try:
            client.connect()
            # After connect (DeviceInfo is in hand) and before streaming
            # (the gain goes out with the stream settings).
            gain = self._resolve_gain(client)
            self.resolved_gain = gain
            client.tune(self._frequency_hz)
            # One demodulator per stream. It carries filter state, mixer
            # phase, and resampling phase between blocks, so building one
            # here -- not in _on_iq -- is what keeps the audio continuous.
            self._demod = USBDemodulator(input_rate=client.sample_rate)
            self._buffer = AudioRingBuffer(
                max_samples=buffer_size, sample_rate=TARGET_RATE
            )
            # Before start_streaming, so the first block already has
            # somewhere to go. Inside the try: a monitor that can't bind
            # its port tears the client down like any other startup
            # failure rather than leaving a half-open connection.
            if self._monitor_port is not None:
                monitor = AudioMonitorServer(port=self._monitor_port)
                monitor.start()
                self._monitor = monitor
            self._last_iq_at = time.monotonic()
            self._running = True
            client.start_streaming(self._on_iq, gain=gain)
        except BaseException:
            # A half-open connection would leak a socket and hold one of
            # the server's client slots until this process dies. Tear it
            # down before the error escapes, whatever the error was.
            #
            # Deliberately not a list of exception types. That list was
            # wrong twice: SpyServerError alone missed the ValueError
            # USBDemodulator raises on a bogus sample rate, and adding
            # ValueError still missed struct.error from an out-of-range
            # gain (struct.error is not a ValueError), raw TimeoutError
            # from a server that accepts TCP but never sends DeviceInfo,
            # and ProtocolError from an over-large body size. Each leaked
            # a connected socket. Guaranteeing teardown matters more than
            # naming the cause, so this catches everything and re-raises
            # unchanged -- callers still see the original exception, and
            # the specific handling that turns known errors into good
            # messages is untouched.
            self._running = False
            self._teardown()
            raise

    def _on_iq(self, iq: np.ndarray) -> None:
        """Demodulate one block into the ring buffer.

        Runs on the client's receive thread. It must never stop the stream:
        stop_streaming() joins that same thread, which from in here raises
        RuntimeError: cannot join current thread. Failures are the client's
        to record; this only produces audio.
        """
        if not self._running or self._demod is None or self._buffer is None:
            return
        audio = self._demod.demodulate(iq)
        if len(audio) == 0:
            return
        self._last_iq_at = time.monotonic()
        self._levels = self._calculate_levels(audio)
        self._buffer.add(audio)
        # After the ring buffer, never before: the decoder is the product
        # and gets the audio first. broadcast() neither blocks nor raises
        # (see audio_stream), so this can't cost an image -- but the
        # ordering means even a future bug there can't get in front of the
        # decode. The try is belt-and-braces for a monitor swapped in from
        # outside this class.
        monitor = self._monitor
        if monitor is not None:
            try:
                monitor.broadcast(audio)
            except Exception:
                logger.debug("Audio monitor failed; continuing", exc_info=True)

    @staticmethod
    def _calculate_levels(samples: np.ndarray) -> AudioLevels:
        if len(samples) == 0:
            return AudioLevels()
        rms = float(np.sqrt(np.mean(samples**2)))
        peak = float(np.max(np.abs(samples)))
        return AudioLevels(rms=rms, peak=peak, is_clipping=peak >= CLIP_THRESHOLD)

    def _teardown(self) -> None:
        """Close the client, recording rather than raising any failure.

        close() calls stop_streaming(), which raises when a receive thread
        refuses to die. RXManager stops the source from a finally block, so
        letting that escape would replace the decode's real result -- or its
        real error -- with a teardown error. A live stream failure outranks
        it: the operator needs to know the stream dropped, not that clearing
        the wreckage was awkward.
        """
        # Before the client check, which returns early when there is no
        # client: a monitor that bound its port and then hit a startup
        # failure would otherwise keep the port held for the life of the
        # process, and the next cycle couldn't bind it.
        monitor = self._monitor
        self._monitor = None
        if monitor is not None:
            try:
                monitor.stop()
            except Exception:
                logger.debug("Audio monitor teardown failed", exc_info=True)

        client = self._client
        if client is None:
            return
        try:
            client.close()
        except SpyServerError as exc:
            logger.error("SpyServer teardown failed: %s", exc.message)
            if self.stream_failure is None:
                self._failure = exc
        except OSError as exc:
            logger.error("SpyServer teardown failed: %s", exc)

    def stop_input(self) -> None:
        """Stop streaming and close the connection.

        Never raises: AudioStreamManager.stop_input doesn't, and RXManager
        calls this from a finally block. A teardown failure lands in
        stream_failure instead.
        """
        # Latch the client's error and drop count before the handle goes
        # away, so a stream that dropped is still reportable afterwards.
        _ = self.stream_failure
        _ = self.dropped_frames
        self._running = False
        self._teardown()
        self._client = None
        self._demod = None

    def get_input_buffer(self) -> AudioRingBuffer | None:
        return self._buffer

    def get_input_levels(self) -> AudioLevels:
        return self._levels
