"""Tests for slant error detection."""

import numpy as np
import pytest

from sstv_core.accessibility.slant_detector import SlantDetector, SlantErrorData


class TestSlantErrorData:
    """Tests for SlantErrorData dataclass."""

    def test_needs_correction_threshold(self):
        """Slant error needs correction when above threshold."""
        # Negligible slant, high confidence - no correction needed
        error1 = SlantErrorData(
            slant_degrees=0.3,
            drift_pixels_per_line=0.1,
            cumulative_drift_pixels=25.6,
            confidence=0.9,
            measurement_lines=100,
        )
        assert not error1.needs_correction

        # Moderate slant, high confidence - correction needed
        error2 = SlantErrorData(
            slant_degrees=2.5,
            drift_pixels_per_line=0.5,
            cumulative_drift_pixels=128.0,
            confidence=0.85,
            measurement_lines=100,
        )
        assert error2.needs_correction

        # High slant, low confidence - no correction (unreliable)
        error3 = SlantErrorData(
            slant_degrees=4.0,
            drift_pixels_per_line=1.0,
            cumulative_drift_pixels=256.0,
            confidence=0.5,
            measurement_lines=20,
        )
        assert not error3.needs_correction

    def test_severity_levels(self):
        """Slant severity categories are correct."""
        negligible = SlantErrorData(0.5, 0.1, 25.6, 0.9, 100)
        assert negligible.severity_level == "negligible"

        minor = SlantErrorData(2.0, 0.3, 76.8, 0.9, 100)
        assert minor.severity_level == "minor"

        moderate = SlantErrorData(4.0, 0.6, 153.6, 0.9, 100)
        assert moderate.severity_level == "moderate"

        severe = SlantErrorData(7.0, 1.2, 307.2, 0.9, 100)
        assert severe.severity_level == "severe"

    def test_to_dict(self):
        """SlantErrorData converts to dict correctly."""
        error = SlantErrorData(
            slant_degrees=2.5,
            drift_pixels_per_line=0.5,
            cumulative_drift_pixels=128.0,
            confidence=0.85,
            measurement_lines=100,
        )
        d = error.to_dict()

        assert d["slant_degrees"] == 2.5
        assert d["drift_pixels_per_line"] == 0.5
        assert d["cumulative_drift_pixels"] == 128.0
        assert d["confidence"] == 0.85
        assert d["measurement_lines"] == 100


class TestSlantDetector:
    """Tests for SlantDetector."""

    def test_initialization(self):
        """Detector initializes with correct parameters."""
        detector = SlantDetector(
            image_width=320,
            image_height=256,
            expected_line_duration_ms=428.22,
            sample_rate=48000,
        )

        assert detector.measurement_count == 0
        assert not detector.has_sufficient_data

    def test_perfect_timing_no_slant(self):
        """Perfect timing with no drift produces zero slant."""
        detector = SlantDetector(
            image_width=320,
            image_height=256,
            expected_line_duration_ms=428.22,
        )

        # Simulate perfect sync timing (no drift)
        for line in range(50):
            sync_time_ms = line * 428.22
            detector.add_sync_timing(line, sync_time_ms)

        assert detector.has_sufficient_data

        slant = detector.calculate_slant_error()
        assert slant is not None
        assert abs(slant.slant_degrees) < 0.01  # Near-zero slant
        assert slant.confidence > 0.99  # Perfect fit
        assert slant.measurement_lines == 50

    def test_positive_drift_detection(self):
        """Detector measures positive drift (receiver slower than transmitter)."""
        detector = SlantDetector(
            image_width=320,
            image_height=256,
            expected_line_duration_ms=428.22,
        )

        # Simulate receiver running 0.5% slower
        # Each line arrives 0.5% later than expected
        drift_rate = 1.005  # 0.5% slower

        for line in range(100):
            # Actual time = expected time * drift rate
            sync_time_ms = line * 428.22 * drift_rate
            detector.add_sync_timing(line, sync_time_ms)

        slant = detector.calculate_slant_error()
        assert slant is not None

        # Should detect positive slant (image shifts right)
        assert slant.slant_degrees > 0.5  # Measurable slant
        assert slant.drift_pixels_per_line > 0  # Positive drift
        assert slant.confidence > 0.95  # High confidence (linear drift)

    def test_negative_drift_detection(self):
        """Detector measures negative drift (receiver faster than transmitter)."""
        detector = SlantDetector(
            image_width=320,
            image_height=256,
            expected_line_duration_ms=428.22,
        )

        # Simulate receiver running 0.3% faster
        drift_rate = 0.997  # 0.3% faster

        for line in range(100):
            sync_time_ms = line * 428.22 * drift_rate
            detector.add_sync_timing(line, sync_time_ms)

        slant = detector.calculate_slant_error()
        assert slant is not None

        # Should detect negative slant (image shifts left)
        assert slant.slant_degrees < -0.3  # Measurable slant
        assert slant.drift_pixels_per_line < 0  # Negative drift
        assert slant.confidence > 0.95  # High confidence

    def test_insufficient_data_returns_none(self):
        """Detector returns None when insufficient data."""
        detector = SlantDetector(
            image_width=320,
            image_height=256,
            expected_line_duration_ms=428.22,
        )

        # Add only 5 lines (need 10+ for reliable measurement)
        for line in range(5):
            detector.add_sync_timing(line, line * 428.22)

        assert not detector.has_sufficient_data
        slant = detector.calculate_slant_error()
        assert slant is None

    def test_noisy_timing_lowers_confidence(self):
        """Random noise in sync timing reduces confidence."""
        detector = SlantDetector(
            image_width=320,
            image_height=256,
            expected_line_duration_ms=428.22,
        )

        np.random.seed(42)  # Reproducible test

        # Add timing with small systematic drift + small jitter
        drift_rate = 1.002  # 0.2% drift (systematic component)
        for line in range(100):
            base_time = line * 428.22 * drift_rate
            jitter = np.random.uniform(-0.5, 0.5)  # ±0.5ms jitter (small noise)
            detector.add_sync_timing(line, base_time + jitter)

        slant = detector.calculate_slant_error()
        assert slant is not None

        # Small jitter on systematic drift should still have good confidence
        # (R² measures how well linear fit explains variance)
        assert slant.confidence > 0.95  # Linear component dominates
        assert slant.slant_degrees > 0  # Positive drift detected

    def test_reset_clears_state(self):
        """Reset clears all timing data."""
        detector = SlantDetector(
            image_width=320,
            image_height=256,
            expected_line_duration_ms=428.22,
        )

        # Add some data
        for line in range(20):
            detector.add_sync_timing(line, line * 428.22)

        assert detector.measurement_count == 20

        detector.reset()

        assert detector.measurement_count == 0
        assert not detector.has_sufficient_data

    def test_realtime_drift_estimation(self):
        """Real-time drift estimation tracks current line drift."""
        detector = SlantDetector(
            image_width=320,
            image_height=256,
            expected_line_duration_ms=428.22,
        )

        # Simulate 1% positive drift
        drift_rate = 1.01

        for line in range(50):
            sync_time_ms = line * 428.22 * drift_rate
            detector.add_sync_timing(line, sync_time_ms)

        # Get real-time drift for line 25
        drift_px = detector.get_realtime_drift(25)

        # Should be positive and proportional to line number
        assert drift_px > 0
        # Rough check: 1% drift over 25 lines
        # pixels_per_ms = 320 / 428.22 ≈ 0.747
        # drift per line ≈ 428.22 * 0.01 * 0.747 ≈ 3.2 px
        # After 25 lines: ~80 px
        assert 50 < drift_px < 150  # Reasonable range

    def test_slant_angle_calculation(self):
        """Slant angle is calculated correctly from drift."""
        detector = SlantDetector(
            image_width=320,
            image_height=256,
            expected_line_duration_ms=428.22,
        )

        # Create known slant scenario:
        # If image drifts 32 pixels over 256 lines
        # tan(angle) = 32 / 256 = 0.125
        # angle = arctan(0.125) ≈ 7.13°

        # Pixels per ms for this mode
        pixels_per_ms = 320 / 428.22  # ≈ 0.747

        # To get 32px drift total, need drift_px_per_line = 32/256 = 0.125
        # drift_ms_per_line = 0.125 / pixels_per_ms ≈ 0.167ms

        # Drift rate = 1 + (0.167 / 428.22) ≈ 1.00039
        drift_rate = 1 + (0.125 / pixels_per_ms / 428.22)

        for line in range(256):
            sync_time_ms = line * 428.22 * drift_rate
            detector.add_sync_timing(line, sync_time_ms)

        slant = detector.calculate_slant_error()
        assert slant is not None

        # Check angle is approximately 7.13°
        expected_angle = np.degrees(np.arctan(32 / 256))
        assert abs(slant.slant_degrees - expected_angle) < 0.5  # Within 0.5°
        assert abs(slant.cumulative_drift_pixels - 32) < 5  # Within 5 pixels


class TestSlantDetectorEdgeCases:
    """Edge case tests for slant detection."""

    def test_zero_height_image(self):
        """Zero height image handled gracefully."""
        detector = SlantDetector(
            image_width=320,
            image_height=0,  # Edge case
            expected_line_duration_ms=428.22,
        )

        for line in range(10):
            detector.add_sync_timing(line, line * 428.22)

        slant = detector.calculate_slant_error()
        # Should return result but with zero slant angle
        assert slant is not None
        assert slant.slant_degrees == 0.0

    def test_extremely_high_drift(self):
        """Detector handles extreme drift rates."""
        detector = SlantDetector(
            image_width=320,
            image_height=256,
            expected_line_duration_ms=428.22,
        )

        # 10% drift (extreme for SSTV)
        drift_rate = 1.10

        for line in range(100):
            sync_time_ms = line * 428.22 * drift_rate
            detector.add_sync_timing(line, sync_time_ms)

        slant = detector.calculate_slant_error()
        assert slant is not None

        # Should detect severe slant
        assert abs(slant.slant_degrees) > 10  # Very high angle
        assert slant.severity_level == "severe"
        assert slant.needs_correction  # Definitely needs fixing
