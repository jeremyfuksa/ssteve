"""Bandpass filter for SSTV signal preprocessing.

Implements a configurable bandpass filter to reject acoustic noise
and pass only the SSTV signal frequency range (1200-2300 Hz).

Purpose:
- Filter out wind noise (low frequency)
- Filter out background conversations/hiss (high frequency)
- Improve SNR for weak SSTV signals
- Enable "Driveway Mode" for acoustic coupling

Reference: "A specific setting to filter out wind noise and background
conversations, focusing only on the 1200Hz-2300Hz SSTV range."
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from scipy import signal

logger = logging.getLogger(__name__)


@dataclass
class BandpassConfig:
    """Configuration for SSTV bandpass filter."""

    # Frequency range (SSTV signal band)
    low_freq: float = 1200.0  # Lower cutoff (suppresses wind, rumble)
    high_freq: float = 2300.0  # Upper cutoff (suppresses hiss, clicks)

    # Filter parameters
    filter_order: int = 4  # 4th order Butterworth (steep rolloff)
    filter_type: str = "bandpass"  # bandpass, lowpass, highpass

    # Audio parameters
    sample_rate: int = 48000

    # Processing options
    use_zero_phase: bool = True  # Use filtfilt for zero-phase (no phase distortion)
    # (A "dithering" option lived here until 2026-08-07. Float samples have
    # no quantization artifacts to dither away, and its removal step
    # actually re-injected the input's DC offset into the bandpassed
    # signal.)


class SSTVBandpassFilter:
    """Bandpass filter optimized for SSTV signal processing.

    Frequency Range Rationale:
    - 1200 Hz: Minimum sync pulse frequency
    - 2300 Hz: Maximum white pixel frequency (Scottie S1)
    - This range covers all SSTV modes (Scottie, Martin, Robot, PD series)

    Filter Design:
    - 4th order Butterworth filter
    - Maximally flat passband (minimal signal distortion)
    - Steep rolloff (good rejection outside passband)

    Application:
    - Applied before DSP pipeline (VIS detection, decoding, encoding)
    - Improves SNR for weak signals
    - Critical for "Driveway Mode" acoustic coupling
    """

    def __init__(self, config: BandpassConfig | None = None) -> None:
        """Initialize SSTV bandpass filter.

        Args:
            config: Filter configuration

        """
        self._config = config or BandpassConfig()

        # Design filter coefficients
        self._b, self._a = self._design_filter()

        # State for zero-phase filtering
        self._zi: np.ndarray | None = None

        logger.info(
            "Bandpass filter initialized: %d-%d Hz, order=%d, sr=%d",
            self._config.low_freq,
            self._config.high_freq,
            self._config.filter_order,
            self._config.sample_rate,
        )

    def _design_filter(self) -> tuple[np.ndarray, np.ndarray]:
        """Design Butterworth bandpass filter coefficients.

        Returns:
            Tuple of (numerator_coeffs, denominator_coeffs)

        """
        nyquist = self._config.sample_rate / 2.0
        low = self._config.low_freq / nyquist
        high = self._config.high_freq / nyquist

        # Design Butterworth filter
        b, a = signal.butter(
            self._config.filter_order,
            [low, high],
            btype=self._config.filter_type,
        )

        return b, a

    def filter(self, samples: np.ndarray) -> np.ndarray:
        """Apply bandpass filter to audio samples.

        Args:
            samples: Input audio samples

        Returns:
            Filtered samples

        """
        if len(samples) == 0:
            return samples

        # filtfilt needs a minimum chunk length for its edge padding; short
        # chunks fall through to the stateful streaming path.
        padlen = 3 * max(len(self._a), len(self._b))
        if self._config.use_zero_phase and len(samples) > padlen:
            # Zero-phase filtering (forward + backward). Block-based by
            # nature; chunk-boundary transients are negligible at SSTV
            # chunk sizes (~100 ms at 48 kHz vs. a ~1 ms filter settle).
            filtered = signal.filtfilt(self._b, self._a, samples)
        else:
            # Stateful forward-only filtering for streaming continuity
            if self._zi is None:
                self._zi = signal.lfilter_zi(self._b, self._a) * samples[0]
            filtered, self._zi = signal.lfilter(self._b, self._a, samples, zi=self._zi)

        return np.asarray(filtered)

    def reset_state(self) -> None:
        """Reset filter state for new processing session."""
        self._zi = None

    def get_frequency_response(
        self, frequencies: np.ndarray
    ) -> np.ndarray:
        """Get frequency response of the filter.

        Useful for debugging and visualization.

        Args:
            frequencies: Array of frequencies to analyze (Hz)

        Returns:
            Magnitude response at each frequency (linear scale)

        """
        _, h = signal.freqz(
            self._b, self._a, worN=2 * np.pi * frequencies / self._config.sample_rate
        )
        return np.asarray(np.abs(h))

    def get_cutoff_frequencies(self) -> tuple[float, float]:
        """Get the filter cutoff frequencies.

        Returns:
            Tuple of (low_cutoff_hz, high_cutoff_hz)

        """
        return (self._config.low_freq, self._config.high_freq)

    def is_in_passband(self, frequency: float) -> bool:
        """Check if a frequency is within the passband.

        Args:
            frequency: Frequency in Hz

        Returns:
            True if frequency is within passband, False otherwise

        """
        return self._config.low_freq <= frequency <= self._config.high_freq


# Preset configurations for common scenarios

class BandpassPresets:
    """Preset bandpass configurations for different scenarios."""

    @staticmethod
    def standard() -> BandpassConfig:
        """Return the standard SSTV bandpass (1000-2400 Hz).

        The lower edge sits below the 1200 Hz sync tone rather than on it.
        This was 1200 Hz until #100, which put sync exactly on the corner
        where a 4th-order Butterworth is already -3 dB: measured on a real
        20m transmission, filtering before sync detection cut raw pulse
        detections from 2945 to 189 and stopped every live decode around
        half the frame.

        Sweeping the lower edge on that recording, counting accepted line
        starts and how many were one clean line apart:

            none    kept=427  clean 82%
            1200    kept=103  clean 54%
            1100    kept=353  clean 76%
            1000    kept=430  clean 87%   <- here
             900    kept=447  clean 78%
             800    kept=458  clean 67%

        1000 Hz scores better than no filter at all, which is the point of
        having one. Below 900 the passband admits enough noise to generate
        spurious pulses, so lower is not simply better.
        """
        return BandpassConfig(
            low_freq=1000.0,
            high_freq=2400.0,
            filter_order=4,
        )

    @staticmethod
    def aggressive_noise_reduction() -> BandpassConfig:
        """Aggressive noise reduction (1100-2200 Hz).

        Narrower passband for extremely noisy environments
        (contest stations, urban locations).

        The lower edge was 1300 Hz until #100, which excluded the 1200 Hz
        sync tone outright -- and with order 6 rather than 4, so the pulse
        the decoder needs most was attenuated hardest exactly when the signal
        could least afford it. 1100 Hz keeps sync inside the passband; the
        noise rejection this preset exists for comes from the steeper rolloff
        and the narrow top end, not from cutting into the sync.
        """
        return BandpassConfig(
            low_freq=1100.0,
            high_freq=2200.0,
            filter_order=6,  # Higher order = steeper rolloff
        )

    @staticmethod
    def weak_signal() -> BandpassConfig:
        """Wide bandpass for weak signal detection (900-2400 Hz).

        Wider passband preserves more signal energy when signal is
        very weak but may admit more noise.

        900 rather than 1100 (see #100): on a weak signal the sync pulse is
        the first thing to disappear, so the preset meant for weak signals
        should give it the most margin, not the least.
        """
        return BandpassConfig(
            low_freq=900.0,
            high_freq=2400.0,
            filter_order=3,  # Lower order = less phase distortion
        )

    @staticmethod
    def driveway_mode() -> BandpassConfig:
        """Optimized for acoustic "Driveway Mode" coupling.

        Phone-to-radio acoustic coupling has specific challenges:
        - Wind noise (low frequency)
        - Traffic/ambient (broad spectrum)
        - Room reflections (comb filtering)

        This preset adds additional low-frequency cutoff to suppress
        wind and room modes.

        Unused today, and not safe to wire into the decode path as it stands:
        the 1500 Hz lower edge excludes the 1200 Hz sync tone entirely, which
        is the failure #100 was. Rejecting wind means cutting where sync
        lives, so this needs a different approach -- a notch or a highpass
        below 1000 Hz -- rather than a passband that starts above it.
        """
        return BandpassConfig(
            low_freq=1500.0,  # Higher low cutoff to reject wind
            high_freq=2300.0,
            filter_order=4,
        )
