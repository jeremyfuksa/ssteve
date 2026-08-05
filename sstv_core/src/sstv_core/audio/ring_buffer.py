"""Thread-safe ring buffer for audio samples."""

from __future__ import annotations

import threading
from collections import deque

import numpy as np


class AudioRingBuffer:
    """Thread-safe ring buffer for audio samples.

    Uses collections.deque for efficient FIFO operations.
    Thread-safe for single-producer, single-consumer scenarios.

    Attributes:
        max_samples: Maximum number of samples to store (default: 480000 = 10s @ 48kHz)
        sample_rate: Sample rate in Hz (default: 48000)

    """

    DEFAULT_MAX_SAMPLES = 480000  # 10 seconds at 48kHz

    def __init__(
        self,
        max_samples: int = DEFAULT_MAX_SAMPLES,
        sample_rate: int = 48000,
    ) -> None:
        """Initialize the ring buffer.

        Args:
            max_samples: Maximum number of samples to store.
            sample_rate: Sample rate in Hz.

        """
        self._lock = threading.RLock()
        self._buffer: deque[float] = deque(maxlen=max_samples)
        self._max_samples = max_samples
        self._sample_rate = sample_rate
        self._total_samples_added = 0

    @property
    def max_samples(self) -> int:
        return self._max_samples

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def max_duration_sec(self) -> float:
        return self._max_samples / self._sample_rate

    def __len__(self) -> int:
        with self._lock:
            return len(self._buffer)

    def add(self, samples: np.ndarray) -> None:
        """Add samples to the buffer.

        If the buffer is full, oldest samples are automatically discarded.

        Args:
            samples: NumPy array of audio samples (mono).

        """
        # Flatten in case of multi-channel input
        flat_samples = np.asarray(samples).flatten()

        with self._lock:
            self._buffer.extend(flat_samples)
            self._total_samples_added += len(flat_samples)

    def get(self, num_samples: int | None = None) -> np.ndarray:
        """Get samples from the buffer without removing them.

        Args:
            num_samples: Number of samples to get. If None, get all.

        Returns:
            NumPy array of samples.

        """
        with self._lock:
            if num_samples is None or num_samples >= len(self._buffer):
                return np.array(list(self._buffer), dtype=np.float32)
            # Get most recent samples
            start_idx = len(self._buffer) - num_samples
            return np.array(list(self._buffer)[start_idx:], dtype=np.float32)

    def pop(self, num_samples: int) -> np.ndarray:
        """Get and remove samples from the buffer (FIFO).

        Args:
            num_samples: Number of samples to pop.

        Returns:
            NumPy array of samples.

        """
        with self._lock:
            actual_count = min(num_samples, len(self._buffer))
            samples = []
            for _ in range(actual_count):
                samples.append(self._buffer.popleft())
            return np.array(samples, dtype=np.float32)

    def clear(self) -> None:
        """Clear all samples from the buffer."""
        with self._lock:
            self._buffer.clear()

    def is_full(self) -> bool:
        """Check if the buffer is full."""
        with self._lock:
            return len(self._buffer) >= self._max_samples

    def is_empty(self) -> bool:
        """Check if the buffer is empty."""
        with self._lock:
            return len(self._buffer) == 0

    def get_duration_sec(self) -> float:
        """Get the duration of buffered audio in seconds."""
        with self._lock:
            return len(self._buffer) / self._sample_rate

    def get_total_samples_added(self) -> int:
        """Get total number of samples added since creation/clear."""
        with self._lock:
            return self._total_samples_added

    def to_numpy(self) -> np.ndarray:
        """Convert entire buffer to a numpy array."""
        return self.get()
