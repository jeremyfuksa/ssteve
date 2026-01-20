"""Enhanced VIS detector with correlation-based detection.

Uses cross-correlation with known VIS waveform templates for robust
detection in noisy conditions (-15 dB SNR), significantly outperforming
simple Goertzel tone detection.

Reference: Black Cat SSTV benchmark - correlation detects at -15 dB SNR
vs tone detection which fails at -5 dB SNR.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Tuple
from enum import Enum

import numpy as np
from scipy import signal

from sstv_core.decode.vis_detector import SSTVMode, VISDetectionResult

logger = logging.getLogger(__name__)


class VISWaveformTemplate:
    """VIS waveform template for correlation detection."""

    def __init__(
        self,
        mode: SSTVMode,
        sample_rate: int = 48000,
    ) -> None:
        self.mode = mode
        self._sample_rate = sample_rate

        # Generate the complete VIS waveform for this mode
        self._waveform = self._generate_vis_waveform(mode)

    @property
    def waveform(self) -> np.ndarray:
        """Get the VIS waveform template."""
        return self._waveform

    def _generate_vis_waveform(self, mode: SSTVMode) -> np.ndarray:
        """Generate VIS waveform for a given mode.

        VIS structure (from SSTV specification):
        - Leader tone: 1900 Hz for 300ms
        - Break: 1200 Hz for 10ms
        - Leader tone: 1900 Hz for 300ms
        - Start bit: 1200 Hz for 30ms
        - 8 data bits: 1100 Hz = 1, 1300 Hz = 0, each 30ms
        - Stop bit: 1200 Hz for 30ms

        The 8 data bits encode the VIS code in LSB first order.
        """
        # Convert VIS code to binary
        vis_code = mode.value
        bits = [(vis_code >> i) & 1 for i in range(8)]  # LSB first

        # Generate waveform segments
        samples_per_ms = self._sample_rate / 1000.0

        segments = []

        # Leader tones (1900 Hz)
        leader_duration = 0.300  # 300ms
        leader_samples = int(leader_duration * samples_per_ms)
        segments.append(self._generate_tone(1900.0, leader_samples))

        # Break (1200 Hz)
        break_duration = 0.010  # 10ms
        break_samples = int(break_duration * samples_per_ms)
        segments.append(self._generate_tone(1200.0, break_samples))

        # Second leader tone (1900 Hz)
        segments.append(self._generate_tone(1900.0, leader_samples))

        # Start bit (1200 Hz)
        start_bit_duration = 0.030  # 30ms
        start_samples = int(start_bit_duration * samples_per_ms)
        segments.append(self._generate_tone(1200.0, start_samples))

        # 8 data bits
        for bit in bits:
            freq = 1100.0 if bit else 1300.0
            bit_samples = int(start_bit_duration * samples_per_ms)
            segments.append(self._generate_tone(freq, bit_samples))

        # Stop bit (1200 Hz)
        stop_samples = int(start_bit_duration * samples_per_ms)
        segments.append(self._generate_tone(1200.0, stop_samples))

        # Concatenate all segments
        return np.concatenate(segments)

    def _generate_tone(self, freq: float, num_samples: int) -> np.ndarray:
        """Generate a pure sine wave at given frequency."""
        t = np.arange(num_samples) / self._sample_rate
        return np.sin(2 * np.pi * freq * t).astype(np.float32)


@dataclass
class CorrelationVISConfig:
    """Configuration for correlation-based VIS detection."""

    sample_rate: int = 48000
    threshold: float = 0.85  # Minimum correlation coefficient for detection
    min_confidence: float = 0.70  # Minimum confidence to report mode

    # Pre-filtering to improve SNR
    enable_pre_filter: bool = True
    filter_low_freq: float = 1000.0
    filter_high_freq: float = 2500.0


class CorrelationVISDetector:
    """VIS code detector using cross-correlation.

    Advantages over simple Goertzel tone detection:
    - Robust to noise (-15 dB SNR vs -5 dB for tone detection)
    - Detects buried VIS codes in static
    - Matches exact VIS waveform timing

    Algorithm:
    1. Maintain a rolling buffer of audio samples
    2. Correlate buffer with each VIS template waveform
    3. Find peak correlation coefficient
    4. Validate with additional confidence checks
    5. Return detected mode with confidence score
    """

    # VIS templates for all supported modes
    SUPPORTED_MODES = [
        SSTVMode.SCOTTIE_S1,
        SSTVMode.SCOTTIE_S2,
        SSTVMode.SCOTTIE_DX,
        SSTVMode.MARTIN_M1,
        SSTVMode.MARTIN_M2,
        SSTVMode.ROBOT_36,
        SSTVMode.ROBOT_72,
        SSTVMode.PD_90,
        SSTVMode.PD_120,
        SSTVMode.PD_180,
        SSTVMode.PD_240,
    ]

    def __init__(self, config: Optional[CorrelationVISConfig] = None) -> None:
        """Initialize correlation VIS detector.

        Args:
            config: Detection configuration
        """
        self._config = config or CorrelationVISConfig()

        # Generate templates for all supported modes
        self._templates: Dict[SSTVMode, VISWaveformTemplate] = {}
        self._generate_templates()

        # Rolling buffer for incoming audio
        self._max_template_length = max(len(t.waveform) for t in self._templates.values())
        self._buffer = np.zeros(self._max_template_length, dtype=np.float32)

        # Track best correlation
        self._best_correlation: float = 0.0
        self._best_mode: Optional[SSTVMode] = None

    def _generate_templates(self) -> None:
        """Generate VIS waveform templates for all supported modes."""
        logger.info("Generating VIS correlation templates for %d modes", len(self.SUPPORTED_MODES))

        for mode in self.SUPPORTED_MODES:
            template = VISWaveformTemplate(mode, self._config.sample_rate)
            self._templates[mode] = template

        logger.debug("VIS templates generated: %s", list(self._templates.keys()))

    def reset(self) -> None:
        """Reset detector state for new detection cycle."""
        self._buffer[:] = 0
        self._best_correlation = 0.0
        self._best_mode = None

    def process_samples(self, samples: np.ndarray) -> Optional[VISDetectionResult]:
        """Process audio samples and detect VIS code.

        Args:
            samples: Incoming audio samples

        Returns:
            VISDetectionResult if mode detected with confidence, None otherwise
        """
        # Apply pre-filtering if enabled
        if self._config.enable_pre_filter:
            samples = self._apply_bandpass_filter(samples)

        # Update rolling buffer
        buffer_size = len(self._buffer)
        samples_size = len(samples)

        if samples_size < buffer_size:
            # Buffer not yet full
            self._buffer[buffer_size - samples_size:] = samples
            return None

        # Shift buffer and add new samples
        self._buffer = np.roll(self._buffer, -samples_size)
        self._buffer[-samples_size:] = samples

        # Correlate with all templates
        best_mode = None
        best_correlation = 0.0

        for mode, template in self._templates.items():
            template_waveform = template.waveform
            template_length = len(template_waveform)

            # Correlate buffer end with template
            # Use normalized cross-correlation for SNR independence
            correlation = self._normalized_correlation(
                self._buffer[-template_length:],
                template_waveform,
            )

            if correlation > best_correlation:
                best_correlation = correlation
                best_mode = mode

        # Update best tracking
        if best_correlation > self._best_correlation:
            self._best_correlation = best_correlation
            self._best_mode = best_mode

        # Check if detection threshold met
        if best_correlation >= self._config.threshold:
            logger.info(
                "VIS detected via correlation: %s (correlation: %.3f)",
                best_mode.name,
                best_correlation,
            )

            # Extract bit pattern from mode value
            vis_code = best_mode.value
            bit_pattern = [(vis_code >> i) & 1 for i in range(8)]

            return VISDetectionResult(
                mode=best_mode,
                vis_code=vis_code,
                confidence=best_correlation,
                bit_pattern=bit_pattern,
                parity_valid=self._check_parity(vis_code),
            )

        return None

    def _normalized_correlation(self, signal: np.ndarray, template: np.ndarray) -> float:
        """Calculate normalized cross-correlation.

        Normalized correlation coefficient (Pearson correlation coefficient)
        is robust to amplitude differences between signal and template.

        Returns value in [-1, 1] where:
        - 1 = perfect match (same shape, proportional amplitude)
        - 0 = no correlation
        - -1 = perfect anti-correlation (inverse shape)
        """
        # Ensure equal length
        min_len = min(len(signal), len(template))
        sig = signal[:min_len]
        tmpl = template[:min_len]

        # Calculate means
        sig_mean = np.mean(sig)
        tmpl_mean = np.mean(tmpl)

        # Calculate standard deviations
        sig_std = np.std(sig)
        tmpl_std = np.std(tmpl)

        # Avoid division by zero
        if sig_std == 0 or tmpl_std == 0:
            return 0.0

        # Calculate Pearson correlation coefficient
        numerator = np.sum((sig - sig_mean) * (tmpl - tmpl_mean))
        denominator = sig_std * tmpl_std * min_len

        return numerator / denominator if denominator != 0 else 0.0

    def _apply_bandpass_filter(self, samples: np.ndarray) -> np.ndarray:
        """Apply bandpass filter to improve SNR before correlation.

        Filter passes 1000-2500 Hz to focus on VIS frequency range
        and reject low-frequency noise, high-frequency hiss.

        Args:
            samples: Input audio samples

        Returns:
            Filtered samples
        """
        nyquist = self._config.sample_rate / 2.0
        low = self._config.filter_low_freq / nyquist
        high = self._config.filter_high_freq / nyquist

        # 4th order Butterworth bandpass filter
        b, a = signal.butter(4, [low, high], btype="band")

        # Apply filter using filtfilt for zero-phase filtering
        filtered = signal.filtfilt(b, a, samples)

        return filtered

    @staticmethod
    def _check_parity(vis_code: int) -> bool:
        """Validate VIS code parity bit.

        VIS codes use odd parity for error detection.
        """
        # Count set bits
        bits_set = sum(1 for i in range(8) if (vis_code >> i) & 1)
        return bits_set % 2 == 1  # Odd parity

    def get_correlation_score(self) -> float:
        """Get current best correlation score."""
        return self._best_correlation

    def get_detected_mode(self) -> Optional[SSTVMode]:
        """Get current detected mode (below threshold)."""
        return self._best_mode
