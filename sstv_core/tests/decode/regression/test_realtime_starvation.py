"""A real-time stream must decode as completely as a fast one (issue #99).

Found by replaying a known-good over-the-air transmission through the live
`AudioSource` seam at wall-clock rate. The same audio, same code, decoded
121/256 lines when fed at 8x and 4/256 when fed at 1x. Speed was the only
variable.

The cause is that `last_sync_time` is set when a sync pulse is *found*, not
when audio *arrives*, and the end-of-signal check keys off it:

    samples = ring_buffer.pop(len(ring_buffer))
    if len(samples) == 0:
        stalled_sec = time.monotonic() - last_sync_time
        if stalled_sec > 2.0 and line_number > 0:
            # signal has ended

Two things go wrong together on a real-time stream. An empty ring buffer is
normal -- the loop polls faster than any source delivers, so many turns
legitimately find nothing. And sync pulses are further apart than the
timeout: a Scottie S1 line is 428ms and Scottie DX is 1050ms, so with
detection latency more than 2 seconds routinely passes between syncs on a
perfectly healthy stream.

Feeding faster than real time hides both, which is why every earlier test
missed this: they either replayed a whole buffer at once or ran at 8x.

These tests pace the source at wall-clock rate deliberately. They are slower
than the rest of the suite for that reason -- the timing IS the test.
"""

from __future__ import annotations

import asyncio
import threading
import time

import numpy as np
import pytest

from sstv_core.audio.ring_buffer import AudioRingBuffer
from sstv_core.audio.stream_manager import AudioLevels
from sstv_core.decode.rx_manager import RXManager
from sstv_core.encode.scottie_encoder import ScottieS1Encoder, ScottieS2Encoder

SAMPLE_RATE = 48000


def _gradient(width: int, height: int) -> np.ndarray:
    x = np.linspace(0, 255, width)
    y = np.linspace(0, 255, height)
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:, :, 0] = np.tile(x, (height, 1)).astype(np.uint8)
    img[:, :, 1] = np.tile(y[:, None], (1, width)).astype(np.uint8)
    img[:, :, 2] = ((x[None, :] + y[:, None]) / 2).astype(np.uint8)
    return img


class RealtimeSource:
    """Feeds pre-encoded audio at a chosen multiple of wall-clock rate.

    Mirrors what a sound card or SpyServer does: an I/O thread pushes into a
    ring buffer that RXManager polls. `speed` scales the feed rate, which is
    the single knob that separated pass from fail in #99.
    """

    sample_rate = SAMPLE_RATE

    def __init__(self, audio: np.ndarray, *, speed: float = 1.0,
                 chunk_ms: float = 100.0) -> None:
        self._audio = np.asarray(audio, dtype=np.float32)
        self._speed = speed
        self._chunk = max(1, int(SAMPLE_RATE * chunk_ms / 1000.0))
        self._buffer: AudioRingBuffer | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.fed = 0

    def start_input(self, device_index=None, callback=None, buffer_size=None):
        # Generously sized: a drop would make the harness the thing under
        # test rather than the decoder.
        self._buffer = AudioRingBuffer(
            max_samples=len(self._audio) + SAMPLE_RATE,
            sample_rate=SAMPLE_RATE,
        )
        self._stop.clear()
        self._thread = threading.Thread(target=self._feed, daemon=True)
        self._thread.start()

    def _feed(self) -> None:
        assert self._buffer is not None
        # Pace against a fixed origin so per-chunk work does not accumulate
        # into drift, which would make the feed slower than it claims.
        origin = time.monotonic()
        while not self._stop.is_set() and self.fed < len(self._audio):
            block = self._audio[self.fed : self.fed + self._chunk]
            if not len(block):
                break
            self._buffer.add(block)
            self.fed += len(block)
            target = origin + (self.fed / SAMPLE_RATE) / self._speed
            delay = target - time.monotonic()
            if delay > 0:
                self._stop.wait(delay)

    def stop_input(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def get_input_buffer(self):
        assert self._buffer is not None
        return self._buffer

    def get_input_levels(self) -> AudioLevels:
        return AudioLevels(rms=0.2, peak=0.8)


async def _decode(audio: np.ndarray, mode: str, *, speed: float,
                  hard_limit: float) -> int:
    """Run one receive, returning lines actually decoded.

    The count comes from `scanline_confidences`, which gets one entry per
    decoded scanline. RXProgress.current_line is not usable here: the saving
    phase emits `current_line=total_lines` unconditionally for display, so a
    decode that gave up at line 4 still reports 256.
    """
    source = RealtimeSource(audio, speed=speed)
    rx = RXManager(stream_manager=source, sample_rate=SAMPLE_RATE)
    await asyncio.wait_for(
        rx.receive(mode=mode, timeout_sec=30.0, save_image=False),
        timeout=hard_limit,
    )
    metrics = rx.get_decode_metrics()
    return len(metrics.scanline_confidences) if metrics else 0


@pytest.mark.integration
async def test_realtime_decodes_a_full_scottie_s2_frame():
    """The regression gate for #99.

    Scottie S2 rather than S1 because it is the fastest full frame we can
    build (~71s of audio, replayed at 4x here), and #99 reproduced on S2's
    277ms lines as readily as S1's 428ms ones.

    4x rather than 1x keeps the test near a minute instead of past it. It is
    still far slower than the 8x that masked the bug, and slow enough that
    the ring buffer empties between polls -- which is the condition that
    triggers the defect. `test_slower_feed_decodes_no_worse` covers the
    true-realtime case directly.
    """
    enc = ScottieS2Encoder()
    audio = enc.encode_image(_gradient(enc.config.width, enc.config.height),
                             include_vis=True)

    lines = await _decode(audio, "ScottieS2", speed=4.0, hard_limit=120.0)

    assert lines >= 250, (
        f"decoded {lines}/256 lines from a complete, clean transmission -- "
        "the stream was starved of audio, not of signal (#99)"
    )


@pytest.mark.integration
async def test_slower_feed_decodes_no_worse():
    """Feed rate must not determine how much of a frame survives.

    This is the shape of #99 stated directly: the same audio at half the
    rate decoded 4/256 instead of 121/256. Comparing two speeds rather
    than asserting an absolute line count means the test keeps its meaning
    if decode quality changes for unrelated reasons.
    """
    enc = ScottieS2Encoder()
    audio = enc.encode_image(_gradient(enc.config.width, enc.config.height),
                             include_vis=True)

    fast = await _decode(audio, "ScottieS2", speed=8.0, hard_limit=60.0)
    slow = await _decode(audio, "ScottieS2", speed=2.0, hard_limit=120.0)

    assert slow >= fast * 0.9, (
        f"decoded {slow} lines at 2x but {fast} at 8x -- feed rate is "
        "deciding how much of the frame survives (#99)"
    )


@pytest.mark.integration
async def test_end_of_signal_still_terminates():
    """The fix must not cost us end-of-signal detection.

    #99's cause is a stall timer that fires too eagerly; the obvious
    over-correction is one that never fires, which would hang every decode
    that ends early. Here the transmission is cut off halfway, so a decoder
    that cannot tell "ended" from "starved" runs to the hard limit.
    """
    enc = ScottieS1Encoder()
    audio = enc.encode_image(_gradient(enc.config.width, enc.config.height),
                             include_vis=True)
    truncated = audio[: len(audio) // 2]

    start = time.monotonic()
    lines = await _decode(truncated, "ScottieS1", speed=8.0, hard_limit=90.0)
    elapsed = time.monotonic() - start

    assert 50 < lines < 250, (
        f"decoded {lines} lines from half a transmission; expected roughly half"
    )
    # Generous: this asserts termination, not latency.
    assert elapsed < 60.0, (
        f"took {elapsed:.1f}s to notice a transmission had ended"
    )
