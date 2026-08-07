"""Sync pulse detector for SSTV scanline synchronization.

Uses Goertzel filtering to detect 1200 Hz sync pulses and measure inter-pulse timing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import ClassVar

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
        return float(np.sqrt(power) / len(samples))


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

    # Detection is a RATIO of 1200 Hz response to the block's own broadband
    # energy, not an absolute magnitude. An absolute threshold is a
    # recording-level test rather than a sync-pulse test: measured across the
    # reference corpus, per-file median magnitude spans 0.0148-0.0471 purely
    # because the recordings were made at different levels, and no single
    # constant separates sync from noise on all of them. The ratio asks "is
    # this block mostly 1200 Hz?", which is unchanged when the input is
    # scaled -- necessary because SSTeVe takes audio from USB interfaces,
    # virtual cables, line-out, and (soon) SDR demodulation at wildly
    # different levels.
    #
    # A pure 1200 Hz tone gives a ratio near 0.65; broadband noise sits well
    # below 0.2. See scripts/sync_threshold_study.py.
    SYNC_RATIO_THRESHOLD = 0.40

    # Blocks quieter than this carry no usable signal; testing their spectral
    # shape produces noise-driven ratios. Guards the silence between
    # transmissions.
    MIN_BLOCK_ENERGY = 0.005

    # Fraction of the expected line interval a pulse must clear to be treated
    # as a genuine line start. Picture content can momentarily resemble
    # 1200 Hz -- a dark region sits near 1500 Hz and noise does the rest --
    # producing spurious pulses mid-line that split scanlines and tear the
    # image. Measured on the reference corpus, real line starts cluster within
    # a few percent of the mode's line time while spurious ones scatter well
    # below it, so 0.8 separates them with margin.
    LINE_SPACING_TOLERANCE = 0.8

    # Retained for callers that reference it; no longer used for detection.
    DETECTION_THRESHOLD = 0.6

    # Mode timing database (line_duration_ms, sync_duration_ms)
    MODE_TIMINGS: ClassVar[dict[str, tuple[float, float]]] = {
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

            # Ratio of 1200 Hz content to the block's total energy. Both terms
            # scale linearly with input level, so the ratio does not.
            energy = float(np.sqrt(np.mean(block.astype(np.float64) ** 2)))
            ratio = mag / energy if energy > self.MIN_BLOCK_ENERGY else 0.0

            current_pos = position + offset
            is_sync = ratio > self.SYNC_RATIO_THRESHOLD

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
                        # The ratio at the pulse's trailing edge: how purely
                        # 1200 Hz this block was, on a 0-1 scale that means
                        # the same thing at any input level.
                        confidence=min(1.0, ratio),
                    )
                    detected.append(pulse)
                    self._sync_pulses.append(pulse)

                    # Calculate inter-pulse time
                    if self._last_sync_end > 0:
                        inter_time_ms = (
                            (self._sync_start - self._last_sync_end) * 1000.0 / self._sample_rate
                        )
                        self._inter_pulse_times.append(inter_time_ms)

                    self._last_sync_end = current_pos

            offset += self._block_size

        return detected

    def estimate_mode_from_timing(self) -> ModeTimingEstimate | None:
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

    def get_sync_positions(self, line_duration_ms: float | None = None) -> list[int]:
        """Get detected sync pulse positions, one per scanline.

        Args:
            line_duration_ms: Expected line time for the mode being decoded.
                When given, pulses closer together than
                `LINE_SPACING_TOLERANCE` of it are dropped as spurious. When
                omitted, the spacing is inferred from the pulses themselves.

        Returns:
            Sample positions of accepted line-start pulses.

        Notes:
            Raw detections include picture content that momentarily looked like
        1200 Hz. Left in, those split scanlines: the decoder treats each as a
        line start and the image tears. Filtering here rather than in
        `process_samples` is deliberate -- the mode, and therefore the real
        line time, is not known while blocks are streaming past.

        """
        positions = [p.position_samples for p in self._sync_pulses]
        if len(positions) < 3:
            return positions

        if line_duration_ms is not None:
            expected = line_duration_ms * self._sample_rate / 1000.0
        else:
            # Infer it: real line starts are the dominant interval, and taking
            # the largest cluster is more robust than the median when spurious
            # detections outnumber genuine ones.
            intervals = np.diff(np.array(positions, dtype=np.float64))
            if len(intervals) == 0:
                return positions
            hist, edges = np.histogram(intervals, bins=48)
            peak = int(np.argmax(hist))
            expected = float((edges[peak] + edges[peak + 1]) / 2.0)

        if expected <= 0:
            return positions

        minimum_gap = expected * self.LINE_SPACING_TOLERANCE

        kept = [positions[0]]
        for pos in positions[1:]:
            if pos - kept[-1] >= minimum_gap:
                kept.append(pos)

        return kept

    def get_last_sync(self) -> SyncPulseResult | None:
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
