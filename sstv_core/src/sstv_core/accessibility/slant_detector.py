"""Slant error data for accessibility feedback and slant correction.

(The SlantDetector class that lived here -- a sync-timing regression
estimator -- was deleted 2026-08-08: it was orphaned, redundant with the
wired HoughSlantCorrector, and nothing ever fed it sync timings. This
module keeps only the SlantErrorData dataclass both the Hough corrector
and audio guidance consume.)
"""

from dataclasses import dataclass


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
