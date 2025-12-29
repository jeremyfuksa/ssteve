"""Slant error detection for SSTV image correction.

Detects horizontal slant (timing drift) in SSTV images by analyzing sync pulse timing
and provides correction data for real-time feedback via stereo sonification.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SlantErrorData:
    """Slant error measurement data."""

    slant_degrees: float  # Degrees of horizontal slant
    drift_pixels_per_line: float  # Horizontal drift in pixels per scanline
    cumulative_drift_pixels: float  # Total drift over entire image
    confidence: float  # Confidence in measurement (0.0-1.0)
    measurement_lines: int  # Number of lines used for calculation

    def to_dict(self) -> dict:
        return {
            "slant_degrees": self.slant_degrees,
            "drift_pixels_per_line": self.drift_pixels_per_line,
            "cumulative_drift_pixels": self.cumulative_drift_pixels,
            "confidence": self.confidence,
            "measurement_lines": self.measurement_lines,
        }

    @property
    def needs_correction(self) -> bool:
        """Whether slant error is significant enough to warrant correction."""
        return abs(self.slant_degrees) > 0.5 and self.confidence > 0.7

    @property
    def severity_level(self) -> str:
        """Categorize slant severity for user feedback."""
        abs_slant = abs(self.slant_degrees)
        if abs_slant < 1.0:
            return "negligible"
        elif abs_slant < 3.0:
            return "minor"
        elif abs_slant < 5.0:
            return "moderate"
        else:
            return "severe"


class SlantDetector:
    """Detects horizontal slant error from sync pulse timing.

    Slant occurs when the transmitter and receiver audio sample rates differ,
    causing the received image to drift horizontally over time. This detector
    measures the drift by tracking sync pulse timing and calculates the
    cumulative slant angle.

    Example:
        detector = SlantDetector(image_width=320, image_height=256)

        # Feed sync pulse times from decoder
        for line_num, sync_time_ms in enumerate(sync_times):
            detector.add_sync_timing(line_num, sync_time_ms)

        # Get slant measurement
        slant = detector.calculate_slant_error()
        if slant and slant.needs_correction:
            print(f"Slant: {slant.slant_degrees:.2f}°")
    """

    def __init__(
        self,
        image_width: int,
        image_height: int,
        expected_line_duration_ms: float,
        sample_rate: int = 48000,
    ) -> None:
        """Initialize slant detector.

        Args:
            image_width: Image width in pixels
            image_height: Image height in pixels (scanlines)
            expected_line_duration_ms: Expected time per scanline (mode-specific)
            sample_rate: Audio sample rate
        """
        self._image_width = image_width
        self._image_height = image_height
        self._expected_line_duration_ms = expected_line_duration_ms
        self._sample_rate = sample_rate

        # Timing data for each scanline
        self._sync_times: list[tuple[int, float]] = []  # (line_number, time_ms)
        self._expected_times: list[float] = []

    def reset(self) -> None:
        """Reset detector state for new image."""
        self._sync_times.clear()
        self._expected_times.clear()

    def add_sync_timing(self, line_number: int, sync_time_ms: float) -> None:
        """Add sync pulse timing measurement.

        Args:
            line_number: Scanline number (0-based)
            sync_time_ms: Time when sync pulse was detected (milliseconds)
        """
        self._sync_times.append((line_number, sync_time_ms))

        # Calculate expected sync time based on line number
        expected_time = line_number * self._expected_line_duration_ms
        self._expected_times.append(expected_time)

    def calculate_slant_error(self) -> Optional[SlantErrorData]:
        """Calculate slant error from accumulated sync timing data.

        Returns:
            SlantErrorData if enough measurements available, None otherwise
        """
        if len(self._sync_times) < 10:
            # Need at least 10 lines for reliable measurement
            logger.debug("Insufficient sync timing data for slant calculation")
            return None

        # Extract line numbers and actual sync times
        line_numbers = np.array([ln for ln, _ in self._sync_times])
        actual_times = np.array([t for _, t in self._sync_times])

        # Calculate time drift from expected
        # Use first sync as reference (t=0)
        reference_time = actual_times[0]
        actual_times = actual_times - reference_time
        expected_times = line_numbers * self._expected_line_duration_ms

        time_drift = actual_times - expected_times  # Positive = late, negative = early

        # Linear regression to find drift rate (ms per line)
        # drift = slope * line_number + intercept
        coeffs = np.polyfit(line_numbers, time_drift, 1)
        drift_rate_ms_per_line = coeffs[0]

        # Calculate confidence based on R² (goodness of fit)
        predicted_drift = np.polyval(coeffs, line_numbers)
        ss_res = np.sum((time_drift - predicted_drift) ** 2)
        ss_tot = np.sum((time_drift - np.mean(time_drift)) ** 2)

        # Special case: if both ss_res and ss_tot are near zero, we have perfect fit
        if ss_tot < 1e-10 and ss_res < 1e-10:
            r_squared = 1.0  # Perfect fit (no variance in residuals or data)
        elif ss_tot > 0:
            r_squared = 1 - (ss_res / ss_tot)
        else:
            r_squared = 0.0

        confidence = max(0.0, min(1.0, r_squared))

        # Convert drift rate to pixels per line
        # drift_rate_ms_per_line represents how much time we gain/lose per line
        # Positive drift = receiver running slower than transmitter
        # This causes the image to shift right (late arrival)

        # Calculate pixels per ms for this mode
        pixels_per_ms = self._image_width / self._expected_line_duration_ms

        # Drift in pixels per line
        drift_pixels_per_line = drift_rate_ms_per_line * pixels_per_ms

        # Calculate cumulative drift over entire image
        cumulative_drift_pixels = drift_pixels_per_line * self._image_height

        # Calculate slant angle in degrees
        # tan(angle) = horizontal_drift / vertical_distance
        # For small angles: angle_radians ≈ tan(angle) = drift_pixels / height_pixels
        if self._image_height > 0:
            slant_radians = np.arctan(cumulative_drift_pixels / self._image_height)
            slant_degrees = np.degrees(slant_radians)
        else:
            slant_degrees = 0.0

        logger.info(
            "Slant detected: %.2f° (%.1f px/line, %.1f total px drift over %d lines, confidence %.1f%%)",
            slant_degrees,
            drift_pixels_per_line,
            cumulative_drift_pixels,
            len(self._sync_times),
            confidence * 100,
        )

        return SlantErrorData(
            slant_degrees=slant_degrees,
            drift_pixels_per_line=drift_pixels_per_line,
            cumulative_drift_pixels=cumulative_drift_pixels,
            confidence=confidence,
            measurement_lines=len(self._sync_times),
        )

    def get_realtime_drift(self, current_line: int) -> float:
        """Get estimated horizontal drift for current scanline.

        Useful for real-time correction during decode.

        Args:
            current_line: Current scanline number

        Returns:
            Estimated horizontal drift in pixels (positive = shift right)
        """
        if len(self._sync_times) < 5:
            return 0.0

        # Quick calculation using last few lines
        recent_data = self._sync_times[-min(20, len(self._sync_times)):]

        line_numbers = np.array([ln for ln, _ in recent_data])
        actual_times = np.array([t for _, t in recent_data])

        # Relative to first of recent samples
        actual_times = actual_times - actual_times[0]
        expected_times = (line_numbers - line_numbers[0]) * self._expected_line_duration_ms

        time_drift = actual_times - expected_times

        # Simple linear fit
        if len(line_numbers) > 1:
            drift_rate = np.polyfit(line_numbers, time_drift, 1)[0]
            pixels_per_ms = self._image_width / self._expected_line_duration_ms
            drift_pixels_per_line = drift_rate * pixels_per_ms

            # Calculate drift for current line
            return drift_pixels_per_line * current_line

        return 0.0

    @property
    def has_sufficient_data(self) -> bool:
        """Whether detector has enough data for reliable measurement."""
        return len(self._sync_times) >= 10

    @property
    def measurement_count(self) -> int:
        """Number of sync timing measurements collected."""
        return len(self._sync_times)
