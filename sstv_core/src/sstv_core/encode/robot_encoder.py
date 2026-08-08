"""Robot 36 SSTV mode encoder.

Robot 36 specifications:
- Resolution: 320x240 pixels (4:3 aspect ratio)
- VIS code: 8
- Sync pulse: 9ms at 1200 Hz
- Color space: YUV (NOT RGB)
- Scanline format: Sync (9ms) → Porch (3ms) → Y (88ms) → Chroma (88ms) → Porch (3ms)
- Interlaced: Even scanlines encode U (Cb), odd scanlines encode V (Cr)
- Frequency mapping: 1500 Hz = black, 2300 Hz = white
- RGB to YUV conversion: ITU-R BT.601 standard
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np

# The encode-side SSTVMode. A separate enum of the same name lives in
# decode/vis_detector.py; their VIS values agree for all 12 shared modes,
# but VISGenerator is typed against this one.
from sstv_core.encode.vis_generator import SSTVMode, VISGenerator

logger = logging.getLogger(__name__)


@dataclass
class Robot36EncoderConfig:
    width: int = 320
    height: int = 240
    sync_duration_ms: float = 9.0
    porch_duration_ms: float = 3.0
    y_scan_duration_ms: float = 88.0
    # Robot 36 subsamples colour: full-rate luminance, half-width chroma
    # alternating R-Y and B-Y between lines. 88.0 here (a copy of the Y
    # duration) made an encoded line 194ms against the specified 150ms, so
    # SSTeVe transmitted audio no standards-compliant decoder could read.
    # The matching decoder bug was fixed in 3314571.
    chroma_scan_duration_ms: float = 44.0
    black_freq: float = 1500.0
    white_freq: float = 2300.0
    sync_freq: float = 1200.0
    porch_freq: float = 1500.0
    sample_rate: int = 48000

    @property
    def samples_per_y_scan(self) -> int:
        return int(self.sample_rate * self.y_scan_duration_ms / 1000)

    @property
    def samples_per_chroma_scan(self) -> int:
        return int(self.sample_rate * self.chroma_scan_duration_ms / 1000)

    @property
    def samples_per_sync(self) -> int:
        return int(self.sample_rate * self.sync_duration_ms / 1000)

    @property
    def samples_per_porch(self) -> int:
        return int(self.sample_rate * self.porch_duration_ms / 1000)


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


class Robot36Encoder:
    """Encodes RGB images to Robot 36 SSTV audio."""

    def __init__(self, config: Robot36EncoderConfig | None = None):
        self._config = config or Robot36EncoderConfig()
        self._phase = 0.0
        self._lines_encoded = 0

    @property
    def config(self) -> Robot36EncoderConfig:
        return self._config

    def _generate_tone(self, freq: float, num_samples: int) -> np.ndarray:
        """Generate a pure tone at the specified frequency."""
        t = (np.arange(num_samples) + self._phase) / self._config.sample_rate
        samples = np.sin(2 * np.pi * freq * t).astype(np.float32) * 0.8
        self._phase = (self._phase + num_samples) % self._config.sample_rate
        return samples

    def _luma_to_freq(self, luma: int) -> float:
        """Convert luminance value (0-255) to frequency (1500-2300 Hz)."""
        normalized = luma / 255.0
        return self._config.black_freq + normalized * (
            self._config.white_freq - self._config.black_freq
        )

    def _rgb_to_yuv(self, rgb_image: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Convert RGB image to YUV using ITU-R BT.601 standard.

        Args:
            rgb_image: RGB image array (height, width, 3)

        Returns:
            Tuple of (Y, U, V) arrays, each (height, width)

        """
        r = rgb_image[:, :, 0].astype(np.float32)
        g = rgb_image[:, :, 1].astype(np.float32)
        b = rgb_image[:, :, 2].astype(np.float32)

        # ITU-R BT.601 conversion
        y = 0.299 * r + 0.587 * g + 0.114 * b
        u = -0.168736 * r - 0.331264 * g + 0.5 * b + 128.0
        v = 0.5 * r - 0.418688 * g - 0.081312 * b + 128.0

        # Clip to valid range
        y = np.clip(y, 0, 255).astype(np.uint8)
        u = np.clip(u, 0, 255).astype(np.uint8)
        v = np.clip(v, 0, 255).astype(np.uint8)

        return y, u, v

    def _encode_channel(self, pixels: np.ndarray, num_samples: int) -> np.ndarray:
        """Encode a channel line to audio samples.

        Args:
            pixels: Array of pixel values (0-255)
            num_samples: Total number of samples to generate

        Returns:
            Audio samples for the channel

        """
        samples_per_pixel = num_samples / len(pixels)
        audio = []

        for i, pixel in enumerate(pixels):
            freq = self._luma_to_freq(pixel)
            start_sample = int(i * samples_per_pixel)
            end_sample = int((i + 1) * samples_per_pixel)
            samples = end_sample - start_sample
            audio.append(self._generate_tone(freq, samples))

        return np.concatenate(audio)

    def encode_scanline(
        self, y_row: np.ndarray, chroma_row: np.ndarray, line_number: int
    ) -> np.ndarray:
        """Encode a single scanline to audio.

        Robot 36 line structure: sync + porch + Y + porch + porch + chroma

        Args:
            y_row: Y (luminance) channel values (320 pixels)
            chroma_row: U or V channel values (320 pixels)
            line_number: Line number (0-239)

        Returns:
            Audio samples for the scanline

        """
        cfg = self._config
        audio_parts = []

        # Sync pulse
        audio_parts.append(self._generate_tone(cfg.sync_freq, cfg.samples_per_sync))

        # Front porch
        audio_parts.append(self._generate_tone(cfg.porch_freq, cfg.samples_per_porch))

        # Y channel
        audio_parts.append(self._encode_channel(y_row, cfg.samples_per_y_scan))

        # Separation and chroma porches, between luminance and colour.
        audio_parts.append(self._generate_tone(cfg.porch_freq, cfg.samples_per_porch))
        audio_parts.append(self._generate_tone(cfg.porch_freq, cfg.samples_per_porch))

        # Chroma channel (U for even lines, V for odd lines)
        audio_parts.append(self._encode_channel(chroma_row, cfg.samples_per_chroma_scan))

        self._lines_encoded = line_number + 1
        return np.concatenate(audio_parts)

    def encode_image(
        self, image: np.ndarray, *, include_vis: bool = True
    ) -> np.ndarray:
        """Encode complete RGB image to audio.

        Args:
            image: RGB image array (height, width, 3)
            include_vis: Prepend the VIS header announcing this mode.
                On by default -- without it no receiver can auto-detect
                what is being sent. Pass False only when the caller
                assembles its own preamble.

        Returns:
            Audio samples for complete image

        """
        if image.shape != (self._config.height, self._config.width, 3):
            logger.warning("Image size mismatch: expected (%d, %d, 3), got %s",
                          self._config.height, self._config.width, image.shape)

        # Convert RGB to YUV
        y, u, v = self._rgb_to_yuv(image)

        self._phase = 0.0
        self._lines_encoded = 0
        audio_parts = []

        # Encode each line
        for line_num in range(min(image.shape[0], self._config.height)):
            y_row = y[line_num]

            # Even lines use U (Cb), odd lines use V (Cr)
            if line_num % 2 == 0:
                chroma_row = u[line_num]
            else:
                chroma_row = v[line_num]

            audio_parts.append(self.encode_scanline(y_row, chroma_row, line_num))

        if include_vis:
            # A VIS header is how a transmission announces its own mode.
            # Without one no receiver can auto-detect what we are sending,
            # and until 2026-08-07 no SSTeVe encoder emitted it.
            header = VISGenerator(sample_rate=self._config.sample_rate).generate(
                SSTVMode.ROBOT_36
            )
            audio_parts.insert(0, header.astype(audio_parts[0].dtype))

        result = np.concatenate(audio_parts)
        logger.info("Encoded %d scanlines, %d audio samples (%.1f seconds)",
                   self._lines_encoded, len(result), len(result) / self._config.sample_rate)
        return result

    def encode_stream(self, image: np.ndarray) -> Iterator[np.ndarray]:
        """Encode image yielding audio per scanline for streaming."""
        # Convert RGB to YUV
        y, u, v = self._rgb_to_yuv(image)

        self._phase = 0.0
        self._lines_encoded = 0

        for line_num in range(min(image.shape[0], self._config.height)):
            y_row = y[line_num]

            # Even lines use U (Cb), odd lines use V (Cr)
            if line_num % 2 == 0:
                chroma_row = u[line_num]
            else:
                chroma_row = v[line_num]

            yield self.encode_scanline(y_row, chroma_row, line_num)

    def get_progress(self) -> EncoderProgress:
        """Get encoding progress."""
        cfg = self._config
        percent = (self._lines_encoded / cfg.height) * 100
        remaining_lines = cfg.height - self._lines_encoded
        line_duration_sec = (cfg.samples_per_sync + cfg.samples_per_porch * 2 +
                            cfg.samples_per_y_scan + cfg.samples_per_chroma_scan) / cfg.sample_rate
        return EncoderProgress(
            lines_encoded=self._lines_encoded,
            total_lines=cfg.height,
            percent_complete=percent,
            estimated_remaining_sec=remaining_lines * line_duration_sec,
        )

    def get_total_duration_sec(self) -> float:
        """Calculate total transmission duration."""
        cfg = self._config
        line_samples = (cfg.samples_per_sync + cfg.samples_per_porch * 2 +
                       cfg.samples_per_y_scan + cfg.samples_per_chroma_scan)
        return (cfg.height * line_samples) / cfg.sample_rate
