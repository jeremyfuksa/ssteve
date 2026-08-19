"""Carrier detection for the recording calibration ladder.

The thing under test is the presence decision, not a level: a raw
amplitude cannot tell a carrier from noise. Measured against the live
Airspy on 2026-08-19, WWV 5 MHz and a silent 20m read mean|IQ| 0.01210
and 0.01036 -- indistinguishable -- while their carrier SNR was 13.1 dB
and 1.3 dB. Every test here therefore feeds a synthetic signal whose
answer is known by construction.
"""

from __future__ import annotations

import numpy as np
import pytest

from sstv_core.sdr.calibration import CARRIER_SNR_DB, carrier_snr_db

RATE = 48_000


def _noise(seconds: float, amplitude: float, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(seconds * RATE)
    return amplitude * (rng.standard_normal(n) + 1j * rng.standard_normal(n))


def _carrier(seconds: float, amplitude: float, offset_hz: float = 0.0) -> np.ndarray:
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    return amplitude * np.exp(2j * np.pi * offset_hz * t)


class TestCarrierSNR:
    def test_pure_noise_has_no_carrier(self) -> None:
        assert carrier_snr_db(_noise(3.0, 0.05), RATE) < CARRIER_SNR_DB

    def test_carrier_in_noise_is_detected(self) -> None:
        signal = _carrier(3.0, 0.05) + _noise(3.0, 0.01)
        assert carrier_snr_db(signal, RATE) > CARRIER_SNR_DB

    def test_a_weak_carrier_still_beats_a_loud_noise_floor(self) -> None:
        """The case a level threshold gets wrong.

        The noise-only array is louder in amplitude than the one carrying
        the carrier, so any mean|IQ| rule ranks them backwards.
        """
        quiet_carrier = _carrier(3.0, 0.010) + _noise(3.0, 0.004, seed=1)
        loud_noise = _noise(3.0, 0.030, seed=2)

        assert np.abs(loud_noise).mean() > np.abs(quiet_carrier).mean()
        assert carrier_snr_db(quiet_carrier, RATE) > carrier_snr_db(loud_noise, RATE)

    def test_carrier_slightly_off_centre_is_still_found(self) -> None:
        """AFC drift and SpyServer's own offset put WWV a few Hz off."""
        signal = _carrier(3.0, 0.05, offset_hz=40.0) + _noise(3.0, 0.01)
        assert carrier_snr_db(signal, RATE) > CARRIER_SNR_DB

    def test_carrier_far_off_centre_is_not_counted(self) -> None:
        """A signal 2 kHz away is a different station, not our carrier."""
        signal = _carrier(3.0, 0.05, offset_hz=2_000.0) + _noise(3.0, 0.01)
        assert carrier_snr_db(signal, RATE) < CARRIER_SNR_DB

    def test_stronger_carrier_reads_higher(self) -> None:
        weak = _carrier(3.0, 0.02) + _noise(3.0, 0.01, seed=3)
        strong = _carrier(3.0, 0.20) + _noise(3.0, 0.01, seed=3)
        assert carrier_snr_db(strong, RATE) > carrier_snr_db(weak, RATE) + 10.0

    def test_too_short_to_judge_returns_nan(self) -> None:
        """Better to say 'I could not measure' than to guess from 100 samples."""
        assert np.isnan(carrier_snr_db(_noise(0.001, 0.05), RATE))

    def test_empty_input_returns_nan(self) -> None:
        assert np.isnan(carrier_snr_db(np.array([], dtype=complex), RATE))

    @pytest.mark.parametrize("seconds", [1.0, 2.0, 3.0, 5.0])
    def test_verdict_is_stable_from_one_second(self, seconds: float) -> None:
        """Why the ladder dwells 5s and not 60s.

        Measured on live WWV, four of five frequencies settled within 1 dB
        by 3 seconds. A synthetic carrier should not need longer.
        """
        signal = _carrier(seconds, 0.05) + _noise(seconds, 0.01)
        assert carrier_snr_db(signal, RATE) > CARRIER_SNR_DB
