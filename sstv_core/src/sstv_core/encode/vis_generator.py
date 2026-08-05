"""VIS (Vertical Interval Signaling) code generator for SSTV transmission."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

import numpy as np

logger = logging.getLogger(__name__)


class SSTVMode(Enum):
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


@dataclass
class VISConfig:
    leader_freq: float = 1900.0
    sync_freq: float = 1200.0
    bit_1_freq: float = 1100.0
    bit_0_freq: float = 1300.0
    leader_duration_ms: float = 300.0
    break_duration_ms: float = 10.0
    bit_duration_ms: float = 30.0
    sample_rate: int = 48000


class VISGenerator:
    """Generates VIS code audio for SSTV transmission."""

    def __init__(self, config: VISConfig | None = None, sample_rate: int = 48000):
        self._config = config or VISConfig(sample_rate=sample_rate)
        self._sample_rate = sample_rate

    def _generate_tone(self, freq: float, duration_ms: float) -> np.ndarray:
        num_samples = int(self._sample_rate * duration_ms / 1000)
        t = np.arange(num_samples) / self._sample_rate
        return (np.sin(2 * np.pi * freq * t) * 0.8).astype(np.float32)

    def _encode_vis_bits(self, vis_code: int) -> list:
        bits = []
        for i in range(7):
            bits.append((vis_code >> i) & 1)
        parity = sum(bits) % 2
        bits.append(parity)
        return bits

    def generate(self, mode: SSTVMode) -> np.ndarray:
        """Generate complete VIS code audio sequence."""
        cfg = self._config
        audio_parts = []

        # Leader tone (300ms)
        audio_parts.append(self._generate_tone(cfg.leader_freq, cfg.leader_duration_ms))

        # Break (10ms)
        audio_parts.append(self._generate_tone(cfg.sync_freq, cfg.break_duration_ms))

        # Second leader (300ms)
        audio_parts.append(self._generate_tone(cfg.leader_freq, cfg.leader_duration_ms))

        # VIS start bit (30ms at sync freq)
        audio_parts.append(self._generate_tone(cfg.sync_freq, cfg.bit_duration_ms))

        # 8 data bits (LSB first)
        bits = self._encode_vis_bits(mode.value)
        for bit in bits:
            freq = cfg.bit_1_freq if bit == 1 else cfg.bit_0_freq
            audio_parts.append(self._generate_tone(freq, cfg.bit_duration_ms))

        # Stop bit (30ms at sync freq)
        audio_parts.append(self._generate_tone(cfg.sync_freq, cfg.bit_duration_ms))

        result = np.concatenate(audio_parts)
        logger.info(
            "Generated VIS code for %s (code=%d), %d samples", mode.name, mode.value, len(result)
        )
        return result

    def get_duration_ms(self) -> float:
        cfg = self._config
        return (cfg.leader_duration_ms * 2 + cfg.break_duration_ms + cfg.bit_duration_ms * 10)

    def get_duration_samples(self) -> int:
        return int(self._sample_rate * self.get_duration_ms() / 1000)
