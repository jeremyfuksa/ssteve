"""Audio stream transmitter for SSTV.

Handles streaming audio output with progress tracking.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TransmitProgress:
    samples_sent: int
    total_samples: int
    percent_complete: float
    elapsed_sec: float
    remaining_sec: float

    def to_dict(self) -> dict:
        return {
            "samples_sent": self.samples_sent,
            "total_samples": self.total_samples,
            "percent_complete": self.percent_complete,
            "elapsed_sec": self.elapsed_sec,
            "remaining_sec": self.remaining_sec,
        }


class AudioTransmitter:
    """Manages audio output for SSTV transmission."""

    def __init__(self, sample_rate: int = 48000, block_size: int = 1024):
        self._sample_rate = sample_rate
        self._block_size = block_size
        self._samples_sent = 0
        self._total_samples = 0
        self._is_transmitting = False
        self._progress_callback: Callable | None = None

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def is_transmitting(self) -> bool:
        return self._is_transmitting

    def set_progress_callback(self, callback: Callable[[TransmitProgress], None]) -> None:
        self._progress_callback = callback

    def _emit_progress(self, elapsed_sec: float) -> None:
        if self._progress_callback is None:
            return
        percent = (self._samples_sent / self._total_samples * 100) if self._total_samples > 0 else 0
        remaining_samples = self._total_samples - self._samples_sent
        remaining_sec = remaining_samples / self._sample_rate
        progress = TransmitProgress(
            samples_sent=self._samples_sent,
            total_samples=self._total_samples,
            percent_complete=percent,
            elapsed_sec=elapsed_sec,
            remaining_sec=remaining_sec,
        )
        self._progress_callback(progress)

    def stream_to_buffer(self, audio: np.ndarray, output_buffer) -> Iterator[int]:
        """Stream audio to an output buffer in blocks.

        Args:
            audio: Audio samples to transmit
            output_buffer: Ring buffer or similar with add() method

        Yields:
            Number of samples written per block

        """
        self._total_samples = len(audio)
        self._samples_sent = 0
        self._is_transmitting = True

        try:
            offset = 0
            while offset < len(audio):
                block = audio[offset:offset + self._block_size]
                output_buffer.add(block)
                self._samples_sent += len(block)
                offset += len(block)
                yield len(block)
        finally:
            self._is_transmitting = False

    async def stream_async(self, audio: np.ndarray, output_buffer,
                          progress_interval_ms: int = 100) -> None:
        """Stream audio asynchronously with progress updates."""
        self._total_samples = len(audio)
        self._samples_sent = 0
        self._is_transmitting = True

        import time
        start_time = time.time()
        last_progress = start_time

        try:
            offset = 0
            while offset < len(audio):
                block = audio[offset:offset + self._block_size]
                output_buffer.add(block)
                self._samples_sent += len(block)
                offset += len(block)

                current_time = time.time()
                if (current_time - last_progress) * 1000 >= progress_interval_ms:
                    self._emit_progress(current_time - start_time)
                    last_progress = current_time

                # Small delay to allow other tasks
                await asyncio.sleep(0)

            # Final progress update
            self._emit_progress(time.time() - start_time)
            logger.info("Transmission complete: %d samples (%.1f sec)",
                       self._samples_sent, self._samples_sent / self._sample_rate)
        finally:
            self._is_transmitting = False

    def get_audio_blocks(self, audio: np.ndarray) -> Iterator[np.ndarray]:
        """Yield audio in blocks suitable for output callback."""
        self._total_samples = len(audio)
        self._samples_sent = 0

        offset = 0
        while offset < len(audio):
            block = audio[offset:offset + self._block_size]
            # Pad last block if needed
            if len(block) < self._block_size:
                block = np.pad(block, (0, self._block_size - len(block)))
            self._samples_sent += len(block)
            offset += self._block_size
            yield block

    def get_progress(self) -> TransmitProgress:
        elapsed = self._samples_sent / self._sample_rate
        remaining = (self._total_samples - self._samples_sent) / self._sample_rate
        percent = (self._samples_sent / self._total_samples * 100) if self._total_samples > 0 else 0
        return TransmitProgress(
            samples_sent=self._samples_sent,
            total_samples=self._total_samples,
            percent_complete=percent,
            elapsed_sec=elapsed,
            remaining_sec=remaining,
        )
