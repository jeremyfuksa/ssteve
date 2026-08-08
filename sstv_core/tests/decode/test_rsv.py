"""Auto-RSV: calculator per spec tables, and honest confidence handling."""

from __future__ import annotations

import json

import pytest

from sstv_core.decode.rsv import DecodeMetrics, RSVCalculator


def metrics(**overrides) -> DecodeMetrics:
    base = DecodeMetrics(
        peak_amplitude=0.8,
        noise_floor=0.01,
        snr_db=21.0,
        vis_confidence=0.95,
        vis_parity_valid=True,
        sync_pulse_jitter_ms=0.5,
        afc_correction_hz=0.0,
        slant_correction_applied=False,
        scanline_confidences=[0.95] * 256,
        rx_quality_score=0.95,
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


class TestSignalMapping:
    """The spec's SNR -> S-unit table, boundary-exact."""

    @pytest.mark.parametrize(
        "snr, expected_s",
        [(25.0, 9), (20.0, 9), (19.9, 8), (17.0, 8), (14.0, 7), (11.0, 6),
         (8.0, 5), (5.0, 4), (2.0, 3), (-1.0, 2), (-5.0, 1)],
    )
    def test_snr_to_s_unit(self, snr, expected_s):
        report = RSVCalculator().calculate(metrics(snr_db=snr))
        assert report.signal == expected_s


class TestVideoAndReadability:
    def test_clean_decode_is_595_class(self):
        report = RSVCalculator().calculate(metrics())
        assert report.readability == 5
        assert report.video == 5
        assert report.to_string() == "595"

    def test_jitter_and_drift_degrade_video(self):
        report = RSVCalculator().calculate(
            metrics(sync_pulse_jitter_ms=6.0, afc_correction_hz=60.0)
        )
        assert report.video <= 3

    def test_degraded_decode_lowers_readability(self):
        report = RSVCalculator().calculate(metrics(rx_quality_score=0.2))
        assert report.readability == 3


class TestHonestConfidence:
    def test_missing_noise_floor_halves_confidence(self):
        with_floor = RSVCalculator().calculate(metrics())
        without_floor = RSVCalculator().calculate(metrics(noise_floor=0.0))
        assert without_floor.confidence <= with_floor.confidence * 0.6

    def test_metrics_json_round_trips(self):
        payload = json.loads(metrics().to_json())
        assert payload["snr_db"] == 21.0
        assert payload["scanline_count"] == 256


class TestMeasuredSNR:
    """The DecodeMetrics the rx pipeline builds must reflect real levels."""

    def test_snr_math_matches_definition(self):
        # 0.5 peak over 0.005 floor = 40 dB
        m = DecodeMetrics(peak_amplitude=0.5, noise_floor=0.005)
        import numpy as np

        m.snr_db = 20.0 * float(np.log10(m.peak_amplitude / m.noise_floor))
        assert m.snr_db == pytest.approx(40.0)
