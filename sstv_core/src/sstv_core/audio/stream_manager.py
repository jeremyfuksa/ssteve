"""Audio stream management for SSTeVe."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import sounddevice as sd

from sstv_core.audio.ring_buffer import AudioRingBuffer

logger = logging.getLogger(__name__)


@dataclass
class AudioLevels:
    """Audio level metrics."""

    rms: float = 0.0
    peak: float = 0.0
    is_clipping: bool = False


class AudioStreamError(Exception):
    """Raised when audio stream operations fail."""

    pass


class AudioStreamManager:
    """Manages audio input/output streams.

    Provides real-time audio I/O with level metering and clipping detection.

    Attributes:
        sample_rate: Sample rate in Hz (default: 48000)
        block_size: Samples per callback (default: 1024)
        clip_threshold: Threshold for clipping detection (default: 0.99)

    """

    DEFAULT_SAMPLE_RATE = 48000
    DEFAULT_BLOCK_SIZE = 1024
    CLIP_THRESHOLD = 0.99

    def __init__(
        self,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        block_size: int = DEFAULT_BLOCK_SIZE,
    ) -> None:
        """Initialize the stream manager."""
        self._lock = threading.RLock()
        self._sample_rate = sample_rate
        self._block_size = block_size
        self._input_stream: sd.InputStream | None = None
        self._output_stream: sd.OutputStream | None = None
        self._input_buffer: AudioRingBuffer | None = None
        self._output_buffer: AudioRingBuffer | None = None
        self._input_levels = AudioLevels()
        self._output_levels = AudioLevels()
        self._input_callback: Callable | None = None
        self._output_callback: Callable | None = None
        self._input_device_id: str | None = None
        self._output_device_id: str | None = None

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def block_size(self) -> int:
        return self._block_size

    @property
    def is_input_active(self) -> bool:
        return self._input_stream is not None and self._input_stream.active

    @property
    def is_output_active(self) -> bool:
        return self._output_stream is not None and self._output_stream.active

    def _calculate_levels(self, samples: np.ndarray) -> AudioLevels:
        """Calculate audio level metrics."""
        if len(samples) == 0:
            return AudioLevels()
        flat = np.asarray(samples).flatten()
        rms = float(np.sqrt(np.mean(flat ** 2)))
        peak = float(np.max(np.abs(flat)))
        is_clipping = peak >= self.CLIP_THRESHOLD
        return AudioLevels(rms=rms, peak=peak, is_clipping=is_clipping)

    def _input_stream_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: Any,
        status: sd.CallbackFlags,
    ) -> None:
        """Handle input stream callbacks."""
        if status:
            logger.warning("Input stream status: %s", status)

        # Convert to mono if stereo
        if indata.ndim > 1 and indata.shape[1] > 1:
            mono = np.mean(indata, axis=1)
        else:
            mono = indata.flatten()

        # Update levels
        self._input_levels = self._calculate_levels(mono)

        # Add to buffer
        if self._input_buffer is not None:
            self._input_buffer.add(mono)

        # Call user callback
        if self._input_callback is not None:
            try:
                self._input_callback(mono, self._input_levels)
            except Exception as e:
                logger.error("Input callback error: %s", e)

    def _output_stream_callback(
        self,
        outdata: np.ndarray,
        frames: int,
        time_info: Any,
        status: sd.CallbackFlags,
    ) -> None:
        """Handle output stream callbacks."""
        if status:
            logger.warning("Output stream status: %s", status)

        # Get data from buffer
        if self._output_buffer is not None and len(self._output_buffer) > 0:
            samples = self._output_buffer.pop(frames)
            if len(samples) < frames:
                # Pad with zeros (buffer underrun)
                samples = np.pad(samples, (0, frames - len(samples)))
            outdata[:] = samples.reshape(-1, 1)
            self._output_levels = self._calculate_levels(samples)
        elif self._output_callback is not None:
            # Use user callback to generate data
            try:
                data = self._output_callback(frames)
                if data is not None and len(data) > 0:
                    outdata[:] = np.asarray(data).reshape(-1, 1)[:frames]
                    self._output_levels = self._calculate_levels(data)
                else:
                    outdata.fill(0)
                    self._output_levels = AudioLevels()
            except Exception as e:
                logger.error("Output callback error: %s", e)
                outdata.fill(0)
        else:
            outdata.fill(0)
            self._output_levels = AudioLevels()

    def start_input(
        self,
        device_index: int | None = None,
        callback: Callable | None = None,
        buffer_size: int = AudioRingBuffer.DEFAULT_MAX_SAMPLES,
    ) -> None:
        """Start audio input stream.

        Args:
            device_index: Input device index (None for default).
            callback: Function called with (samples, levels) on each block.
            buffer_size: Size of the ring buffer in samples.

        """
        with self._lock:
            if self._input_stream is not None:
                self.stop_input()

            self._input_callback = callback
            self._input_buffer = AudioRingBuffer(
                max_samples=buffer_size,
                sample_rate=self._sample_rate,
            )

            try:
                self._input_stream = sd.InputStream(
                    device=device_index,
                    samplerate=self._sample_rate,
                    blocksize=self._block_size,
                    channels=1,
                    callback=self._input_stream_callback,
                )
                self._input_stream.start()
                logger.info("Started input stream on device %s", device_index)
            except (sd.PortAudioError, ValueError) as e:
                # sounddevice raises ValueError (not PortAudioError) for bad
                # device indexes and unsupported parameters.
                self._input_stream = None
                self._input_buffer = None
                raise AudioStreamError(f"Can't start input stream: {e}") from e

    def stop_input(self) -> None:
        """Stop audio input stream."""
        with self._lock:
            if self._input_stream is not None:
                try:
                    self._input_stream.stop()
                    self._input_stream.close()
                except Exception as e:
                    logger.warning("Error stopping input stream: %s", e)
                finally:
                    self._input_stream = None
                logger.info("Stopped input stream")

    def start_output(
        self,
        device_index: int | None = None,
        callback: Callable | None = None,
        buffer_size: int = AudioRingBuffer.DEFAULT_MAX_SAMPLES,
    ) -> None:
        """Start audio output stream."""
        with self._lock:
            if self._output_stream is not None:
                self.stop_output()

            self._output_callback = callback
            self._output_buffer = AudioRingBuffer(
                max_samples=buffer_size,
                sample_rate=self._sample_rate,
            )

            try:
                self._output_stream = sd.OutputStream(
                    device=device_index,
                    samplerate=self._sample_rate,
                    blocksize=self._block_size,
                    channels=1,
                    callback=self._output_stream_callback,
                )
                self._output_stream.start()
                logger.info("Started output stream on device %s", device_index)
            except (sd.PortAudioError, ValueError) as e:
                # sounddevice raises ValueError (not PortAudioError) for bad
                # device indexes and unsupported parameters.
                self._output_stream = None
                self._output_buffer = None
                raise AudioStreamError(f"Can't start output stream: {e}") from e

    def stop_output(self) -> None:
        """Stop audio output stream."""
        with self._lock:
            if self._output_stream is not None:
                try:
                    self._output_stream.stop()
                    self._output_stream.close()
                except Exception as e:
                    logger.warning("Error stopping output stream: %s", e)
                finally:
                    self._output_stream = None
                logger.info("Stopped output stream")

    def get_input_buffer(self) -> AudioRingBuffer | None:
        """Get the input ring buffer."""
        return self._input_buffer

    def get_output_buffer(self) -> AudioRingBuffer | None:
        """Get the output ring buffer."""
        return self._output_buffer

    def get_input_levels(self) -> AudioLevels:
        """Get current input level metrics."""
        return self._input_levels

    def get_output_levels(self) -> AudioLevels:
        """Get current output level metrics."""
        return self._output_levels

    def write_output(self, samples: np.ndarray) -> None:
        """Write samples to the output buffer."""
        if self._output_buffer is not None:
            self._output_buffer.add(samples)

    def stop_all(self) -> None:
        """Stop all active streams."""
        self.stop_input()
        self.stop_output()
