"""Auto-RSV: measured decode metrics -> RSV signal report.

Implements docs/features/AUTO_RSV_SPECIFICATION.md. RSV (Readability,
Signal, Video) is SSTV's signal report; the point of computing it from
measurements is honest reports instead of rubber-stamp 599s.

Every number in a report must trace to a measurement; when a metric was
not measured, the calculator degrades confidence rather than inventing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class DecodeMetrics:
    """Raw measurements collected during an SSTV decode."""

    # Signal level measurements
    peak_amplitude: float = 0.0        # 0.0-1.0 normalized audio level
    noise_floor: float = 0.0           # 0.0-1.0, measured before VIS
    snr_db: float = 0.0                # 20*log10(peak/noise)

    # VIS detection quality
    vis_confidence: float = 0.0        # 0.0-1.0
    vis_parity_valid: bool = True

    # Sync/timing quality
    sync_pulse_jitter_ms: float = 0.0  # stddev of sync spacing
    afc_correction_hz: float = 0.0     # applied frequency offset
    slant_correction_applied: bool = False

    # Scanline decode quality
    scanline_confidences: list[float] = field(default_factory=list)

    # Overall composite (legacy field)
    rx_quality_score: float = 0.0

    @property
    def mean_scanline_quality(self) -> float:
        if not self.scanline_confidences:
            return 0.0
        return float(sum(self.scanline_confidences) / len(self.scanline_confidences))

    def to_json(self) -> str:
        return json.dumps(
            {
                "peak_amplitude": round(self.peak_amplitude, 4),
                "noise_floor": round(self.noise_floor, 6),
                "snr_db": round(self.snr_db, 1),
                "vis_confidence": round(self.vis_confidence, 3),
                "vis_parity_valid": self.vis_parity_valid,
                "sync_pulse_jitter_ms": round(self.sync_pulse_jitter_ms, 3),
                "afc_correction_hz": round(self.afc_correction_hz, 1),
                "slant_correction_applied": self.slant_correction_applied,
                "mean_scanline_quality": round(self.mean_scanline_quality, 3),
                "scanline_count": len(self.scanline_confidences),
                "rx_quality_score": round(self.rx_quality_score, 3),
            }
        )


@dataclass
class RSVReport:
    """SSTV signal report (Readability, Signal, Video)."""

    readability: int   # 1-5
    signal: int        # 1-9
    video: int         # 1-5
    snr_db: float
    signal_description: str
    confidence: float  # 0.0-1.0

    def to_string(self) -> str:
        return f"{self.readability}{self.signal}{self.video}"

    def to_dict(self) -> dict:
        return {
            "rsv": self.to_string(),
            "readability": self.readability,
            "signal": self.signal,
            "video": self.video,
            "snr_db": round(self.snr_db, 1),
            "description": self.signal_description,
            "confidence": round(self.confidence, 2),
        }


class RSVCalculator:
    """Converts decode metrics to an RSV report, per the spec tables."""

    def calculate(self, metrics: DecodeMetrics) -> RSVReport:
        readability = self._calculate_readability(metrics)
        signal = self._calculate_signal_strength(metrics)
        video = self._calculate_video_quality(metrics)
        return RSVReport(
            readability=readability,
            signal=signal,
            video=video,
            snr_db=metrics.snr_db,
            signal_description=self._generate_description(signal, video),
            confidence=self._calculate_confidence(metrics),
        )

    def _calculate_readability(self, metrics: DecodeMetrics) -> int:
        if not metrics.vis_parity_valid:
            return 4
        if metrics.rx_quality_score < 0.3:
            return 3
        return 5

    def _calculate_signal_strength(self, metrics: DecodeMetrics) -> int:
        """Map SNR in dB to S-units per the spec table."""
        thresholds = [
            (20.0, 9), (17.0, 8), (14.0, 7), (11.0, 6),
            (8.0, 5), (5.0, 4), (2.0, 3), (-1.0, 2),
        ]
        for snr_floor, s_unit in thresholds:
            if metrics.snr_db >= snr_floor:
                return s_unit
        return 1

    def _calculate_video_quality(self, metrics: DecodeMetrics) -> int:
        quality = metrics.mean_scanline_quality

        if metrics.sync_pulse_jitter_ms > 5.0:
            quality *= 0.7
        elif metrics.sync_pulse_jitter_ms > 2.0:
            quality *= 0.85

        if abs(metrics.afc_correction_hz) > 50:
            quality *= 0.8
        elif abs(metrics.afc_correction_hz) > 20:
            quality *= 0.9

        if metrics.slant_correction_applied:
            quality *= 0.9

        if quality >= 0.9:
            return 5
        if quality >= 0.75:
            return 4
        if quality >= 0.55:
            return 3
        if quality >= 0.35:
            return 2
        return 1

    def _generate_description(self, signal: int, video: int) -> str:
        signal_desc = {
            9: "Very strong", 8: "Strong", 7: "Good", 6: "Fair",
            5: "Moderate", 4: "Weak", 3: "Weak", 2: "Very weak", 1: "Barely readable",
        }[signal]
        video_desc = {
            5: "crystal clear image", 4: "clean image",
            3: "some noise in the image", 2: "noisy image", 1: "heavy artifacts",
        }[video]
        return f"{signal_desc} signal, {video_desc}"

    def _calculate_confidence(self, metrics: DecodeMetrics) -> float:
        """Estimate how certain we are of this report.

        Confidence falls when the inputs are thin: no noise-floor sample,
        few scanlines, or shaky VIS. Never fabricate certainty.
        """
        confidence = 1.0
        if metrics.noise_floor <= 0.0:
            confidence *= 0.5  # SNR was not really measured
        if len(metrics.scanline_confidences) < 32:
            confidence *= 0.7
        confidence *= max(0.3, min(1.0, metrics.vis_confidence + 0.3))
        return round(min(1.0, confidence), 3)
