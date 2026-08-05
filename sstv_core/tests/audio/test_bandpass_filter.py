"""Tests for the SSTV bandpass filter.

Regression coverage for the streaming decode path: filter() previously
called scipy's lfilter_zi (initial-condition helper) where it meant
lfilter, so the first real audio chunk of every decode session raised
TypeError. These tests push real samples through both branches.
"""

import numpy as np
import pytest

from sstv_core.audio.bandpass_filter import (
    BandpassConfig,
    BandpassPresets,
    SSTVBandpassFilter,
)

SAMPLE_RATE = 48000


def tone(freq_hz: float, duration_sec: float = 0.1) -> np.ndarray:
    t = np.arange(int(SAMPLE_RATE * duration_sec)) / SAMPLE_RATE
    return np.sin(2 * np.pi * freq_hz * t)


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x**2)))


class TestFilterRegression:
    def test_standard_preset_filters_streaming_chunks(self):
        """The decode path: repeated 100ms chunks through the standard preset."""
        f = SSTVBandpassFilter(BandpassPresets.standard())
        for _ in range(5):
            chunk = tone(1900.0)
            out = f.filter(chunk)
            assert out.shape == chunk.shape
            assert np.all(np.isfinite(out))

    def test_forward_only_config_maintains_state_across_chunks(self):
        config = BandpassConfig(
            low_freq=1200.0,
            high_freq=2300.0,
            filter_order=4,
            sample_rate=SAMPLE_RATE,
            use_zero_phase=False,
        )
        f = SSTVBandpassFilter(config)
        for _ in range(3):
            out = f.filter(tone(1500.0))
            assert np.all(np.isfinite(out))
        assert f._zi is not None

    def test_short_chunk_does_not_crash_zero_phase(self):
        """Chunks below filtfilt's padlen fall back to streaming filtering."""
        f = SSTVBandpassFilter(BandpassPresets.standard())
        out = f.filter(tone(1900.0)[:10])
        assert out.shape == (10,)
        assert np.all(np.isfinite(out))

    def test_empty_input_passthrough(self):
        f = SSTVBandpassFilter(BandpassPresets.standard())
        out = f.filter(np.array([]))
        assert len(out) == 0


class TestBandBehavior:
    @pytest.mark.parametrize("freq,should_pass", [(1900.0, True), (300.0, False), (6000.0, False)])
    def test_passband_and_stopband(self, freq, should_pass):
        f = SSTVBandpassFilter(BandpassPresets.standard())
        signal_in = tone(freq, duration_sec=0.5)
        ratio = rms(f.filter(signal_in)) / rms(signal_in)
        if should_pass:
            assert ratio > 0.7, f"{freq} Hz should pass (ratio {ratio:.3f})"
        else:
            assert ratio < 0.1, f"{freq} Hz should be attenuated (ratio {ratio:.3f})"


class TestState:
    def test_reset_state_clears_zi(self):
        config = BandpassConfig(
            low_freq=1200.0,
            high_freq=2300.0,
            filter_order=4,
            sample_rate=SAMPLE_RATE,
            use_zero_phase=False,
        )
        f = SSTVBandpassFilter(config)
        f.filter(tone(1500.0))
        assert f._zi is not None
        f.reset_state()
        assert f._zi is None
