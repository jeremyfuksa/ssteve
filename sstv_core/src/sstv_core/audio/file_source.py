"""FileSource: a recording, replayed as though it were arriving live (#61).

Implements the four methods RXManager uses -- start_input, stop_input,
get_input_buffer, get_input_levels -- like SpyServerSource does, so a file
decode runs the same pipeline a live one does: VIS, progressive scanlines,
waterfall, levels, the lot. That is the point. The shell is being built
against a band that is silent 97.4% of the time; replaying the off-air
corpus is how it gets something to draw on demand.

Paced at real time, in sound-card-sized blocks, on purpose. Faster than
real time and the backlog outruns CorrelationVISDetector's rolling window:
the header is scrolled out of the buffer before the detector looks at it
(measured in tests/integration/test_sdr_roundtrip.py -- a 65,536-sample
backlog decodes nothing). Real time also makes the canvas paint at the
speed an operator will actually see.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from math import gcd
from pathlib import Path

import numpy as np

from sstv_core.audio.gain import apply_input_gain
from sstv_core.audio.ring_buffer import AudioRingBuffer
from sstv_core.audio.stream_manager import AudioLevels

logger = logging.getLogger(__name__)

#: The engine rate. Recordings are resampled to it on load.
ENGINE_RATE = 48_000

#: Samples per push -- a typical sound-card callback.
BLOCK_SAMPLES = 1024

CLIP_THRESHOLD = 0.99


class FileSource:
    """Feeds a recording into a ring buffer at the rate it was recorded.

    Loads and resamples in the constructor, so an unreadable file fails
    the request that named it rather than a session that has already
    started.

    Raises:
        OSError / RuntimeError: from soundfile, if the file can't be read.
        ValueError: if it holds no audio.

    """

    def __init__(self, path: str | Path) -> None:
        import soundfile as sf
        from scipy.signal import resample_poly

        audio, rate = sf.read(str(path), dtype="float32", always_2d=True)
        mono = audio.mean(axis=1)
        if not len(mono):
            raise ValueError(f"{path} holds no audio.")
        if rate != ENGINE_RATE:
            # The reduced ratio. An integer ratio (48000 // 11025 = 4) would
            # label a 44.1 kHz stream 48 kHz -- a 9% rate error that slants
            # every picture.
            divisor = gcd(ENGINE_RATE, int(rate))
            mono = resample_poly(mono, ENGINE_RATE // divisor, int(rate) // divisor)
        self._audio = np.asarray(mono, dtype=np.float32)
        self._buffer: AudioRingBuffer | None = None
        self._levels = AudioLevels()
        self._input_gain: float | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def sample_rate(self) -> int:
        return ENGINE_RATE

    @property
    def duration_sec(self) -> float:
        return len(self._audio) / ENGINE_RATE

    def start_input(
        self,
        device_index: int | None = None,
        callback: Callable | None = None,
        buffer_size: int = AudioRingBuffer.DEFAULT_MAX_SAMPLES,
    ) -> None:
        """Start replaying from the beginning.

        `device_index` and `callback` are accepted and ignored, matching
        AudioStreamManager.start_input so the duck type is drop-in.
        """
        self.stop_input()
        self._buffer = AudioRingBuffer(max_samples=buffer_size, sample_rate=ENGINE_RATE)
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._feed, name="file-source", daemon=True
        )
        self._thread.start()

    def _feed(self) -> None:
        buffer = self._buffer
        if buffer is None:
            return
        started = time.monotonic()
        position = 0
        while position < len(self._audio) and not self._stop.is_set():
            block = self._audio[position : position + BLOCK_SAMPLES]
            block = apply_input_gain(block, self._input_gain)
            self._levels = self._calculate_levels(block)
            buffer.add(block)
            position += len(block)
            # Against the start, not the last push, so a late wakeup
            # doesn't accumulate into a slow replay.
            due = started + position / ENGINE_RATE
            self._stop.wait(max(0.0, due - time.monotonic()))
        # Silence after the end, not a frozen last reading.
        self._levels = AudioLevels()

    @staticmethod
    def _calculate_levels(samples: np.ndarray) -> AudioLevels:
        rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
        peak = float(np.max(np.abs(samples)))
        return AudioLevels(rms=rms, peak=peak, is_clipping=peak >= CLIP_THRESHOLD)

    def stop_input(self) -> None:
        """Stop the replay. Never raises: RXManager calls it from a finally."""
        self._stop.set()
        thread = self._thread
        self._thread = None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)

    def get_input_buffer(self) -> AudioRingBuffer | None:
        return self._buffer

    def get_input_levels(self) -> AudioLevels:
        return self._levels

    @property
    def input_gain(self) -> float | None:
        return self._input_gain

    def set_input_gain(self, gain: float | None) -> None:
        """Change the operator gain mid-replay (#56), as a live source does."""
        self._input_gain = gain
