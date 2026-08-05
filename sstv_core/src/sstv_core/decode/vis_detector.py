"""VIS (Vertical Interval Signaling) code detector for SSTeVe.

Uses Goertzel filtering for efficient single-frequency detection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

import numpy as np

logger = logging.getLogger(__name__)


class SSTVMode(Enum):
    """Supported SSTV modes with VIS codes."""

    SCOTTIE_S1 = 60
    SCOTTIE_S2 = 56
    SCOTTIE_DX = 76
    MARTIN_M1 = 44
    MARTIN_M2 = 40
    ROBOT_36 = 8
    ROBOT_72 = 12
    PD_90 = 99
    PD_120 = 95
    PD_160 = 98
    PD_180 = 96
    PD_240 = 97
    WRAASE_SC2_180 = 55

    @classmethod
    def from_vis_code(cls, code: int) -> SSTVMode | None:
        """Get mode from VIS code."""
        for mode in cls:
            if mode.value == code:
                return mode
        return None


@dataclass
class VISDetectionResult:
    """Result of VIS code detection."""

    mode: SSTVMode | None
    vis_code: int
    confidence: float
    bit_pattern: list[int]
    parity_valid: bool

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.name if self.mode else None,
            "vis_code": self.vis_code,
            "confidence": self.confidence,
            "bit_pattern": self.bit_pattern,
            "parity_valid": self.parity_valid,
        }


class GoertzelFilter:
    """Goertzel filter for efficient single-frequency detection."""

    def __init__(self, target_freq: float, sample_rate: int, block_size: int) -> None:
        self._target_freq = target_freq
        self._sample_rate = sample_rate
        self._block_size = block_size

        # Pre-compute Goertzel coefficient
        k = int(0.5 + (block_size * target_freq) / sample_rate)
        omega = (2.0 * np.pi * k) / block_size
        self._coeff = 2.0 * np.cos(omega)

    def magnitude(self, samples: np.ndarray) -> float:
        """Calculate magnitude at target frequency."""
        s0 = s1 = s2 = 0.0
        for sample in samples:
            s0 = sample + self._coeff * s1 - s2
            s2 = s1
            s1 = s0
        power = s1 * s1 + s2 * s2 - self._coeff * s1 * s2
        return float(np.sqrt(power) / len(samples))


class VISDetector:
    """Detects VIS codes from audio stream.

    VIS code structure:
    - Leader tone: 1900 Hz for 300ms
    - Break: 1200 Hz for 10ms
    - Leader tone: 1900 Hz for 300ms
    - VIS start bit: 1200 Hz for 30ms
    - 8 data bits (LSB first): 1100 Hz = 1, 1300 Hz = 0, each 30ms
    - Stop bit: 1200 Hz for 30ms
    """

    LEADER_FREQ = 1900.0
    SYNC_FREQ = 1200.0
    VIS_BIT_1_FREQ = 1100.0
    VIS_BIT_0_FREQ = 1300.0

    LEADER_DURATION_MS = 300
    BREAK_DURATION_MS = 10
    BIT_DURATION_MS = 30

    DETECTION_THRESHOLD = 0.7

    def __init__(self, sample_rate: int = 48000) -> None:
        self._sample_rate = sample_rate
        self._bit_samples = int(sample_rate * self.BIT_DURATION_MS / 1000)

        # Create Goertzel filters for each frequency
        self._filter_leader = GoertzelFilter(self.LEADER_FREQ, sample_rate, self._bit_samples)
        self._filter_sync = GoertzelFilter(self.SYNC_FREQ, sample_rate, self._bit_samples)
        self._filter_bit1 = GoertzelFilter(self.VIS_BIT_1_FREQ, sample_rate, self._bit_samples)
        self._filter_bit0 = GoertzelFilter(self.VIS_BIT_0_FREQ, sample_rate, self._bit_samples)

        self._state = "searching"
        self._leader_count = 0
        self._bits: list[int] = []
        self._confidence_sum = 0.0
        self._bit_count = 0

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def reset(self) -> None:
        """Reset detector state."""
        self._state = "searching"
        self._leader_count = 0
        self._bits = []
        self._confidence_sum = 0.0
        self._bit_count = 0

    def _detect_frequency(self, samples: np.ndarray) -> tuple[str, float]:
        """Detect which frequency is dominant in samples."""
        mag_leader = self._filter_leader.magnitude(samples)
        mag_sync = self._filter_sync.magnitude(samples)
        mag_bit1 = self._filter_bit1.magnitude(samples)
        mag_bit0 = self._filter_bit0.magnitude(samples)

        magnitudes = {
            "leader": mag_leader,
            "sync": mag_sync,
            "bit1": mag_bit1,
            "bit0": mag_bit0,
        }

        max_freq = max(magnitudes, key=magnitudes.__getitem__)
        max_mag = magnitudes[max_freq]
        total_mag = sum(magnitudes.values())

        confidence = max_mag / total_mag if total_mag > 0 else 0.0
        return max_freq, confidence

    def process_samples(self, samples: np.ndarray) -> VISDetectionResult | None:
        """Process audio samples looking for VIS code.

        Args:
            samples: Audio samples (should be ~30ms worth)

        Returns:
            VISDetectionResult if complete VIS code detected, None otherwise

        """
        freq, confidence = self._detect_frequency(samples)

        if self._state == "searching":
            if freq == "leader" and confidence > self.DETECTION_THRESHOLD:
                self._leader_count += 1
                if self._leader_count >= 10:  # ~300ms of leader
                    self._state = "leader_detected"
                    logger.debug("Leader tone detected")
            else:
                self._leader_count = 0

        elif self._state == "leader_detected":
            if freq == "sync" and confidence > self.DETECTION_THRESHOLD:
                self._state = "break_detected"
                logger.debug("Break detected, waiting for second leader")

        elif self._state == "break_detected":
            if freq == "leader" and confidence > self.DETECTION_THRESHOLD:
                self._leader_count += 1
                if self._leader_count >= 10:
                    self._state = "waiting_start_bit"
                    self._leader_count = 0
                    logger.debug("Second leader detected")

        elif self._state == "waiting_start_bit":
            if freq == "sync" and confidence > self.DETECTION_THRESHOLD:
                self._state = "reading_bits"
                self._bits = []
                self._confidence_sum = 0.0
                self._bit_count = 0
                logger.debug("Start bit detected, reading data bits")

        elif self._state == "reading_bits":
            if freq in ("bit1", "bit0"):
                bit = 1 if freq == "bit1" else 0
                self._bits.append(bit)
                self._confidence_sum += confidence
                self._bit_count += 1

                if len(self._bits) == 8:
                    self._state = "waiting_stop_bit"
                    logger.debug("All data bits read: %s", self._bits)
            else:
                # Unexpected frequency, reset
                logger.warning("Unexpected frequency during bit reading, resetting")
                self.reset()

        elif self._state == "waiting_stop_bit":
            if freq == "sync" and confidence > self.DETECTION_THRESHOLD:
                # Complete VIS code received
                result = self._decode_vis()
                self.reset()
                return result
            else:
                logger.warning("Missing stop bit, resetting")
                self.reset()

        return None

    def _decode_vis(self) -> VISDetectionResult:
        """Decode the collected bits into a VIS code."""
        # Bits are LSB first, with bit 7 being parity
        vis_code = 0
        for i in range(7):
            if self._bits[i]:
                vis_code |= (1 << i)

        # Check parity (even parity)
        parity_bit = self._bits[7]
        calculated_parity = sum(self._bits[:7]) % 2
        parity_valid = parity_bit == calculated_parity

        # Calculate average confidence
        avg_confidence = self._confidence_sum / self._bit_count if self._bit_count > 0 else 0.0

        # Look up mode
        mode = SSTVMode.from_vis_code(vis_code)

        if mode:
            logger.info("Detected VIS code %d (%s) with %.1f%% confidence",
                       vis_code, mode.name, avg_confidence * 100)
        else:
            logger.warning("Unknown VIS code %d with %.1f%% confidence",
                          vis_code, avg_confidence * 100)

        return VISDetectionResult(
            mode=mode,
            vis_code=vis_code,
            confidence=avg_confidence,
            bit_pattern=self._bits.copy(),
            parity_valid=parity_valid,
        )

    def detect_from_buffer(self, audio_buffer: np.ndarray) -> VISDetectionResult | None:
        """Process an entire audio buffer looking for VIS code.

        Args:
            audio_buffer: Audio samples to process

        Returns:
            VISDetectionResult if VIS code found, None otherwise

        """
        self.reset()
        offset = 0

        while offset + self._bit_samples <= len(audio_buffer):
            samples = audio_buffer[offset:offset + self._bit_samples]
            result = self.process_samples(samples)
            if result:
                return result
            offset += self._bit_samples // 2  # 50% overlap for better detection

        return None
