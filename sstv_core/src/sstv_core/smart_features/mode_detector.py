"""Smart Mode Detection - Detect SSTV mode from sync timing when VIS fails.

This module implements sophisticated mode detection based on sync pulse timing analysis.
When VIS code detection fails or returns low confidence, this algorithm can suggest
the most likely mode based on measured scanline intervals.
"""

from dataclasses import dataclass

import numpy as np

from ..decode.sync_detector import SyncPulseDetector

# Full line period in ms -- the time between consecutive sync pulse starts,
# which is what this module actually measures. Until 2026-08-07 this table
# held per-COLOR-CHANNEL scan durations instead (ScottieS1 138.24 instead of
# 428.22...), so a textbook Scottie S1 measured ~428 ms, matched nothing
# within the confidence window, and detection returned None for every mode
# except Robot36/72, whose entries happened to be real line periods. The
# seven non-PD entries come from the decode-side sync detector's table (the
# correct one that already existed and was bypassed); PD periods are
# 20 ms sync + 2.08 ms porch + 4 color components.
MODE_TIMINGS = {
    mode: line_ms
    for mode, (line_ms, _sync_ms) in SyncPulseDetector.MODE_TIMINGS.items()
}
MODE_TIMINGS.update(
    {
        "PD90": 703.04,   # 20 + 2.08 + 4 x 170.240
        "PD120": 508.48,  # 20 + 2.08 + 4 x 121.600
        "PD180": 754.24,  # 20 + 2.08 + 4 x 183.040
        "PD240": 1000.0,  # 20 + 2.08 + 4 x 244.480
    }
)


@dataclass
class ModeDetectionResult:
    """Result of mode detection analysis."""

    mode: str
    confidence: float
    measured_intervals: list[float]
    expected_interval: float
    num_samples: int

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "confidence": self.confidence,
            "measured_intervals": self.measured_intervals[:10],  # First 10 for debugging
            "expected_interval": self.expected_interval,
            "num_samples": self.num_samples,
        }


def remove_outliers(data: list[float], z_threshold: float = 2.0) -> list[float]:
    """Remove statistical outliers from data using z-score method.

    Args:
        data: List of numeric values
        z_threshold: Z-score threshold for outlier detection (default 2.0)

    Returns:
        List with outliers removed

    """
    if len(data) < 3:
        return data

    data_array = np.array(data)
    mean = np.mean(data_array)
    std = np.std(data_array)

    if std == 0:
        return data

    # Calculate z-scores
    z_scores = np.abs((data_array - mean) / std)

    # Filter out outliers
    filtered = data_array[z_scores < z_threshold]

    return [float(v) for v in filtered]


def calculate_mode_confidence(measured_interval: float, expected_interval: float) -> float:
    """Calculate confidence score for a mode match.

    Confidence calculation:
    - 1.0 at perfect match (0% error)
    - Linear decay to 0.0 at 10% error
    - 0.0 for errors > 10%

    Args:
        measured_interval: Measured scanline interval (ms)
        expected_interval: Expected interval for mode (ms)

    Returns:
        Confidence score 0.0-1.0

    """
    deviation = abs(measured_interval - expected_interval)
    percent_error = (deviation / expected_interval) * 100

    # Confidence: 1.0 at perfect match, 0.0 at >10% error
    if percent_error < 10:
        confidence = 1.0 - (percent_error / 10)
    else:
        confidence = 0.0

    return confidence


def _measure_intervals(
    audio_stream: np.ndarray,
    sample_rate: int,
    duration_sec: float,
    min_samples: int,
) -> tuple[float, list[float]] | None:
    """Measure the median sync-to-sync interval in ms.

    Shared by primary detection and candidate ranking so candidates exist
    even when the primary confidence gate rejects the best match --
    previously get_top_mode_candidates called the gated function first and
    returned [] exactly when fallback options were needed.
    """
    max_samples = int(duration_sec * sample_rate)
    if len(audio_stream) > max_samples:
        audio_stream = audio_stream[:max_samples]

    sync_detector = SyncPulseDetector(sample_rate=sample_rate)
    sync_pulses = sync_detector.detect_in_buffer(audio_stream)
    if len(sync_pulses) < min_samples:
        return None

    intervals = []
    for i in range(len(sync_pulses) - 1):
        interval_samples = (
            sync_pulses[i + 1].position_samples - sync_pulses[i].position_samples
        )
        intervals.append(interval_samples * 1000.0 / sample_rate)

    if len(intervals) < min_samples - 1:
        return None

    filtered_intervals = remove_outliers(intervals, z_threshold=2.0)
    if len(filtered_intervals) < 5:
        return None

    return float(np.median(filtered_intervals)), filtered_intervals


def detect_mode_from_sync_timing(
    audio_stream: np.ndarray,
    sample_rate: int = 48000,
    duration_sec: float = 10.0,
    min_samples: int = 10
) -> ModeDetectionResult | None:
    """Detect SSTV mode from sync pulse timing when VIS fails.

    Algorithm:
    1. Detect 1200 Hz sync pulses (Goertzel filter)
    2. Measure inter-pulse intervals (scanline duration)
    3. Remove outliers (QRM, noise spikes) using z-score
    4. Compare against known mode timings
    5. Calculate confidence based on timing consistency

    Args:
        audio_stream: Audio samples to analyze
        sample_rate: Sample rate in Hz (default 48000)
        duration_sec: Duration to analyze in seconds (default 10.0)
        min_samples: Minimum number of scanlines needed (default 10)

    Returns:
        ModeDetectionResult or None if detection failed

    """
    measurement = _measure_intervals(
        audio_stream, sample_rate, duration_sec, min_samples
    )
    if measurement is None:
        return None
    median_interval, filtered_intervals = measurement

    # Step 5: Score each mode based on deviation
    mode_scores = {}
    for mode_name, expected_interval in MODE_TIMINGS.items():
        confidence = calculate_mode_confidence(median_interval, expected_interval)
        mode_scores[mode_name] = confidence

    # Step 6: Return best match if confidence >= threshold
    best_mode = max(mode_scores, key=mode_scores.__getitem__)
    best_confidence = mode_scores[best_mode]

    if best_confidence < 0.70:
        # Confidence too low for reliable detection
        return None

    return ModeDetectionResult(
        mode=best_mode,
        confidence=best_confidence,
        measured_intervals=filtered_intervals[:10],  # First 10 for debugging
        expected_interval=MODE_TIMINGS[best_mode],
        num_samples=len(filtered_intervals),
    )


def get_top_mode_candidates(
    audio_stream: np.ndarray,
    sample_rate: int = 48000,
    duration_sec: float = 10.0,
    top_n: int = 3
) -> list[tuple[str, float]]:
    """Get top N mode candidates sorted by confidence.

    Useful for providing fallback options when primary detection has low confidence.

    Args:
        audio_stream: Audio samples to analyze
        sample_rate: Sample rate in Hz
        duration_sec: Duration to analyze in seconds
        top_n: Number of top candidates to return

    Returns:
        List of (mode_name, confidence) tuples sorted by confidence (descending)

    """
    measurement = _measure_intervals(
        audio_stream, sample_rate, duration_sec, min_samples=10
    )
    if measurement is None:
        return []
    median_interval, _ = measurement

    mode_scores = []

    for mode_name, expected_interval in MODE_TIMINGS.items():
        confidence = calculate_mode_confidence(median_interval, expected_interval)
        if confidence > 0.0:
            mode_scores.append((mode_name, confidence))

    # Sort by confidence (descending) and return top N
    mode_scores.sort(key=lambda x: x[1], reverse=True)
    return mode_scores[:top_n]


def get_confidence_level(confidence: float) -> str:
    """Get human-readable confidence level description.

    Args:
        confidence: Confidence score 0.0-1.0

    Returns:
        Confidence level: "high", "medium", or "low"

    """
    if confidence >= 0.85:
        return "high"
    elif confidence >= 0.70:
        return "medium"
    else:
        return "low"


def get_suggestion_message(mode: str, confidence: float) -> str:
    """Generate user-friendly suggestion message in SSTeVe voice.

    Args:
        mode: Detected mode name
        confidence: Confidence score 0.0-1.0

    Returns:
        Suggestion message for UI display

    """
    level = get_confidence_level(confidence)
    confidence_pct = int(confidence * 100)

    if level == "high":
        return f"This looks like {mode} to me. Should we go with that?"
    elif level == "medium":
        return (
            f"Not sure, but this looks like {mode} to me (about {confidence_pct}% sure). "
            "Want to try it?"
        )
    else:
        return "Having trouble reading this signal. You'll need to choose the mode manually."
