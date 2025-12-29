"""Sync pulse detector for SSTV scanline synchronization.

Uses Goertzel filtering to detect 1200 Hz sync pulses and measure inter-pulse timing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SyncPulseResult:
    """Result of sync pulse detection."""
    position_samples: int
    duration_ms: float
    confidence: float

    def to_dict(self) -> dict:
        return {
            "position_samples": self.position_samples,
            "duration_ms": self.duration_ms,
            "confidence": self.confidence,
        }


@dataclass
class ModeTimingEstimate:
    """Estimated mode based on sync pulse timing."""
    mode_name: str
    line_duration_ms: float
    confidence: float
    sync_duration_ms: float

    def to_dict(self) -> dict:
        return {
            "mode_name": self.mode_name,
            "line_duration_ms": self.line_duration_ms,
            "confidence": self.confidence,
            "sync_duration_ms": self.sync_duration_ms,
        }


class GoertzelFilter:
    """Goertzel filter for efficient single-frequency detection."""

    def __init__(self, target_freq: float, sample_rate: int, block_size: int) -> None:
        self._target_freq = target_freq
        self._sample_rate = sample_rate
        self._block_size = block_size
        k = int(0.5 + (block_size * target_freq) / sample_rate)
        omega = (2.0 * np.pi * k) / block_size
        self._coeff = 2.0 * np.cos(omega)

    def magnitude(self, samples: np.ndarray) -> float:
        s0 = s1 = s2 = 0.0
        for sample in samples:
            s0 = sample + self._coeff * s1 - s2
            s2 = s1
            s1 = s0
        power = s1 * s1 + s2 * s2 - self._coeff * s1 * s2
        return np.sqrt(power) / len(samples)


class SyncPulseDetector:
    """Detects SSTV sync pulses (1200 Hz) in audio stream.

    Sync pulse characteristics vary by mode:
    - Scottie S1/S2: 9ms sync pulse, ~428ms line time
    - Martin M1/M2: 4.862ms sync, ~446ms line time
    - Robot 36/72: 9ms sync
    """

    SYNC_FREQ = 1200.0
    MIN_SYNC_DURATION_MS = 3.0
    MAX_SYNC_DURATION_MS = 15.0
    DETECTION_THRESHOLD = 0.6

    # Mode timing database (line_duration_ms, sync_duration_ms)
    MODE_TIMINGS = {
        "ScottieS1": (428.22, 9.0),
        "ScottieS2": (277.69, 9.0),
        "ScottieDX": (1050.0, 9.0),
        "MartinM1": (446.446, 4.862),
        "MartinM2": (226.798, 4.862),
        "Robot36": (150.0, 9.0),
        "Robot72": (300.0, 9.0),
    }

    def __init__(self, sample_rate: int = 48000) -> None:
        self._sample_rate = sample_rate
        # Use small block for precise timing (1ms)
        self._block_size = int(sample_rate / 1000)
        self._filter = GoertzelFilter(self.SYNC_FREQ, sample_rate, self._block_size)

        self._in_sync = False
        self._sync_start = 0
        self._last_sync_end = 0
        self._sync_pulses: list[SyncPulseResult] = []
        self._inter_pulse_times: list[float] = []

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def reset(self) -> None:
        """Reset detector state."""
        self._in_sync = False
        self._sync_start = 0
        self._last_sync_end = 0
        self._sync_pulses = []
        self._inter_pulse_times = []

    def process_samples(self, samples: np.ndarray, position: int = 0) -> list[SyncPulseResult]:
        """Process audio samples detecting sync pulses.

        Args:
            samples: Audio samples to process
            position: Position of first sample in overall stream

        Returns:
            List of detected sync pulses
        """
        detected = []
        offset = 0

        while offset + self._block_size <= len(samples):
            block = samples[offset:offset + self._block_size]
            mag = self._filter.magnitude(block)

            current_pos = position + offset
            is_sync = mag > self.DETECTION_THRESHOLD

            if is_sync and not self._in_sync:
                # Start of sync pulse
                self._in_sync = True
                self._sync_start = current_pos

            elif not is_sync and self._in_sync:
                # End of sync pulse
                self._in_sync = False
                duration_samples = current_pos - self._sync_start
                duration_ms = duration_samples * 1000.0 / self._sample_rate

                if self.MIN_SYNC_DURATION_MS <= duration_ms <= self.MAX_SYNC_DURATION_MS:
                    pulse = SyncPulseResult(
                        position_samples=self._sync_start,
                        duration_ms=duration_ms,
                        confidence=mag,
                    )
                    detected.append(pulse)
                    self._sync_pulses.append(pulse)

                    # Calculate inter-pulse time
                    if self._last_sync_end > 0:
                        inter_time_ms = (self._sync_start - self._last_sync_end) * 1000.0 / self._sample_rate
                        self._inter_pulse_times.append(inter_time_ms)

                    self._last_sync_end = current_pos

            offset += self._block_size

        return detected

    def estimate_mode_from_timing(self) -> Optional[ModeTimingEstimate]:
        """Estimate SSTV mode from detected sync pulse timing.

        Returns:
            ModeTimingEstimate if enough pulses detected, None otherwise
        """
        if len(self._inter_pulse_times) < 3:
            return None

        # Calculate median inter-pulse time (more robust than mean)
        median_time = np.median(self._inter_pulse_times)

        # Calculate median sync duration
        sync_durations = [p.duration_ms for p in self._sync_pulses]
        median_sync = np.median(sync_durations)

        # Find best matching mode
        best_mode = None
        best_confidence = 0.0

        for mode_name, (line_time, sync_time) in self.MODE_TIMINGS.items():
            # Calculate how close the timing matches
            time_diff = abs(median_time - line_time) / line_time
            sync_diff = abs(median_sync - sync_time) / sync_time

            # Combined confidence (lower diff = higher confidence)
            confidence = max(0.0, 1.0 - time_diff - sync_diff * 0.5)

            if confidence > best_confidence:
                best_confidence = confidence
                best_mode = mode_name

        if best_mode and best_confidence > 0.5:
            logger.info("Mode estimate: %s (confidence: %.1f%%)", best_mode, best_confidence * 100)
            return ModeTimingEstimate(
                mode_name=best_mode,
                line_duration_ms=median_time,
                confidence=best_confidence,
                sync_duration_ms=median_sync,
            )

        logger.warning("Can't confidently estimate mode from timing (best: %s at %.1f%%)",
                      best_mode, best_confidence * 100)
        return None

    def get_sync_positions(self) -> list[int]:
        """Get all detected sync pulse positions."""
        return [p.position_samples for p in self._sync_pulses]

    def get_last_sync(self) -> Optional[SyncPulseResult]:
        """Get the most recently detected sync pulse."""
        return self._sync_pulses[-1] if self._sync_pulses else None

    def detect_in_buffer(self, audio_buffer: np.ndarray) -> list[SyncPulseResult]:
        """Process entire audio buffer and return all sync pulses.

        Args:
            audio_buffer: Complete audio buffer to analyze

        Returns:
            List of all detected sync pulses
        """
        self.reset()
        return self.process_samples(audio_buffer, 0)
