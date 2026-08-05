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
    apply_dithering: bool = True  # Add small noise to prevent quantization artifacts


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

        # Apply dithering to prevent quantization artifacts
        if self._config.apply_dithering:
            samples = samples + np.random.normal(0, 1e-6, samples.shape)

        if self._config.use_zero_phase:
            # Use filtfilt for zero-phase filtering
            # This applies filter forward and backward, removing phase distortion
            # Note: We maintain state zi for real-time streaming
            filtered, self._zi = signal.lfilter_zi(self._b, self._a, samples, zi=self._zi)
            # Apply reverse filter for zero-phase
            filtered_reversed, zi_rev = signal.lfilter_zi(
                self._b, self._a, filtered[::-1], zi=self._zi
            )
            filtered = filtered_reversed[::-1]
            # Reset zi for next call
            self._zi = zi_rev
        else:
            # Standard forward-only filtering
            filtered, self._zi = signal.lfilter_zi(self._b, self._a, samples, zi=self._zi)

        # Remove dithering noise (subtracts mean of added dither)
        if self._config.apply_dithering:
            filtered = filtered - np.mean(filtered - samples)

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
        """Return the standard SSTV bandpass (1200-2300 Hz).

        Suitable for most SSTV reception conditions with normal noise levels.
        """
        return BandpassConfig(
            low_freq=1200.0,
            high_freq=2300.0,
            filter_order=4,
        )

    @staticmethod
    def aggressive_noise_reduction() -> BandpassConfig:
        """Aggressive noise reduction (1300-2200 Hz).

        Narrower passband for extremely noisy environments
        (contest stations, urban locations).
        """
        return BandpassConfig(
            low_freq=1300.0,
            high_freq=2200.0,
            filter_order=6,  # Higher order = steeper rolloff
        )

    @staticmethod
    def weak_signal() -> BandpassConfig:
        """Wide bandpass for weak signal detection (1100-2400 Hz).

        Wider passband preserves more signal energy when signal is
        very weak but may admit more noise.
        """
        return BandpassConfig(
            low_freq=1100.0,
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
        """
        return BandpassConfig(
            low_freq=1500.0,  # Higher low cutoff to reject wind
            high_freq=2300.0,
            filter_order=4,
        )
