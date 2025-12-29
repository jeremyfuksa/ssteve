"""Scottie S1 SSTV mode encoder.

Scottie S1 specifications:
- Resolution: 320x256 pixels
- Sync pulse: 9ms at 1200 Hz
- Color sequence: Green, Blue, Red
- Scanline time per color: 138.24ms
- Frequency mapping: 1500 Hz = black, 2300 Hz = white
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterator, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ScottieS1EncoderConfig:
    width: int = 320
    height: int = 256
    sync_duration_ms: float = 9.0
    separator_duration_ms: float = 1.5
    color_scan_duration_ms: float = 138.24
    black_freq: float = 1500.0
    white_freq: float = 2300.0
    sync_freq: float = 1200.0
    sample_rate: int = 48000

    @property
    def samples_per_color_line(self) -> int:
        return int(self.sample_rate * self.color_scan_duration_ms / 1000)

    @property
    def samples_per_sync(self) -> int:
        return int(self.sample_rate * self.sync_duration_ms / 1000)

    @property
    def samples_per_separator(self) -> int:
        return int(self.sample_rate * self.separator_duration_ms / 1000)


@dataclass
class EncoderProgress:
    lines_encoded: int
    total_lines: int
    percent_complete: float
    estimated_remaining_sec: float

    def to_dict(self) -> dict:
        return {
            "lines_encoded": self.lines_encoded,
            "total_lines": self.total_lines,
            "percent_complete": self.percent_complete,
            "estimated_remaining_sec": self.estimated_remaining_sec,
        }


class ScottieS1Encoder:
    """Encodes RGB images to Scottie S1 SSTV audio."""

    def __init__(self, config: Optional[ScottieS1EncoderConfig] = None):
        self._config = config or ScottieS1EncoderConfig()
        self._phase = 0.0
        self._lines_encoded = 0

    @property
    def config(self) -> ScottieS1EncoderConfig:
        return self._config

    def _generate_tone(self, freq: float, num_samples: int) -> np.ndarray:
        t = (np.arange(num_samples) + self._phase) / self._config.sample_rate
        samples = np.sin(2 * np.pi * freq * t).astype(np.float32) * 0.8
        self._phase = (self._phase + num_samples) % self._config.sample_rate
        return samples

    def _luma_to_freq(self, luma: int) -> float:
        normalized = luma / 255.0
        return self._config.black_freq + normalized * (self._config.white_freq - self._config.black_freq)

    def _encode_color_line(self, pixels: np.ndarray) -> np.ndarray:
        cfg = self._config
        samples_per_pixel = cfg.samples_per_color_line / len(pixels)
        audio = []
        for i, pixel in enumerate(pixels):
            freq = self._luma_to_freq(pixel)
            start_sample = int(i * samples_per_pixel)
            end_sample = int((i + 1) * samples_per_pixel)
            num_samples = end_sample - start_sample
            audio.append(self._generate_tone(freq, num_samples))
        return np.concatenate(audio)

    def encode_scanline(self, rgb_row: np.ndarray, line_number: int) -> np.ndarray:
        """Encode a single RGB scanline to audio.

        Scottie line structure: sep + green + sep + blue + sync + red
        """
        cfg = self._config
        audio_parts = []

        # Extract color channels
        red = rgb_row[:, 0]
        green = rgb_row[:, 1]
        blue = rgb_row[:, 2]

        # Separator before green
        audio_parts.append(self._generate_tone(cfg.black_freq, cfg.samples_per_separator))

        # Green channel
        audio_parts.append(self._encode_color_line(green))

        # Separator before blue
        audio_parts.append(self._generate_tone(cfg.black_freq, cfg.samples_per_separator))

        # Blue channel
        audio_parts.append(self._encode_color_line(blue))

        # Sync pulse (also acts as separator)
        audio_parts.append(self._generate_tone(cfg.sync_freq, cfg.samples_per_sync))

        # Red channel
        audio_parts.append(self._encode_color_line(red))

        self._lines_encoded = line_number + 1
        return np.concatenate(audio_parts)

    def encode_image(self, image: np.ndarray) -> np.ndarray:
        """Encode complete RGB image to audio.

        Args:
            image: RGB image array (height, width, 3)

        Returns:
            Audio samples for complete image
        """
        if image.shape != (self._config.height, self._config.width, 3):
            logger.warning("Image size mismatch: expected (%d, %d, 3), got %s",
                          self._config.height, self._config.width, image.shape)

        self._phase = 0.0
        self._lines_encoded = 0
        audio_parts = []

        for line_num in range(min(image.shape[0], self._config.height)):
            rgb_row = image[line_num]
            audio_parts.append(self.encode_scanline(rgb_row, line_num))

        result = np.concatenate(audio_parts)
        logger.info("Encoded %d scanlines, %d audio samples (%.1f seconds)",
                   self._lines_encoded, len(result), len(result) / self._config.sample_rate)
        return result

    def encode_stream(self, image: np.ndarray) -> Iterator[np.ndarray]:
        """Encode image yielding audio per scanline for streaming."""
        self._phase = 0.0
        self._lines_encoded = 0

        for line_num in range(min(image.shape[0], self._config.height)):
            rgb_row = image[line_num]
            yield self.encode_scanline(rgb_row, line_num)

    def get_progress(self) -> EncoderProgress:
        cfg = self._config
        percent = (self._lines_encoded / cfg.height) * 100
        remaining_lines = cfg.height - self._lines_encoded
        line_duration_sec = (cfg.samples_per_color_line * 3 + cfg.samples_per_sync +
                            cfg.samples_per_separator * 3) / cfg.sample_rate
        return EncoderProgress(
            lines_encoded=self._lines_encoded,
            total_lines=cfg.height,
            percent_complete=percent,
            estimated_remaining_sec=remaining_lines * line_duration_sec,
        )

    def get_total_duration_sec(self) -> float:
        cfg = self._config
        line_samples = (cfg.samples_per_color_line * 3 + cfg.samples_per_sync +
                       cfg.samples_per_separator * 3)
        return (cfg.height * line_samples) / cfg.sample_rate
