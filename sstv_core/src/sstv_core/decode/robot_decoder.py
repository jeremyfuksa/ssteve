"""Robot 36 SSTV mode decoder.

Robot 36 specifications:
- Resolution: 320x240 pixels (4:3 aspect ratio)
- VIS code: 8
- Sync pulse: 9ms at 1200 Hz
- Color space: YUV (NOT RGB)
- Scanline format: Sync (9ms) → Y (88ms) → Even/Odd chroma (88ms each)
- Interlaced: Even scanlines carry U (Cb), odd scanlines carry V (Cr)
- Frequency mapping: 1500 Hz = black, 2300 Hz = white
- YUV to RGB conversion: ITU-R BT.601 standard
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterator, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Robot36Config:
    """Robot 36 mode configuration."""
    width: int = 320
    height: int = 240
    sync_duration_ms: float = 9.0
    porch_duration_ms: float = 3.0
    y_scan_duration_ms: float = 88.0
    chroma_scan_duration_ms: float = 88.0
    black_freq: float = 1500.0
    white_freq: float = 2300.0
    sync_freq: float = 1200.0
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

    @property
    def total_line_samples(self) -> int:
        # Sync + porch + Y + chroma + porch
        return int(self.sample_rate * 194.0 / 1000)


@dataclass
class ScanlineData:
    """Decoded scanline data for Robot 36."""
    line_number: int
    y_channel: np.ndarray  # Luminance
    chroma: np.ndarray     # U for even lines, V for odd lines
    sync_confidence: float = 0.0
    decode_quality: float = 0.0

    def to_dict(self) -> dict:
        return {
            "line_number": self.line_number,
            "sync_confidence": self.sync_confidence,
            "decode_quality": self.decode_quality,
        }


@dataclass
class DecodeProgress:
    """Decode progress information."""
    lines_decoded: int
    total_lines: int
    current_line: int
    percent_complete: float
    estimated_remaining_sec: float
    signal_quality: float

    def to_dict(self) -> dict:
        return {
            "lines_decoded": self.lines_decoded,
            "total_lines": self.total_lines,
            "current_line": self.current_line,
            "percent_complete": self.percent_complete,
            "estimated_remaining_sec": self.estimated_remaining_sec,
            "signal_quality": self.signal_quality,
        }


class Robot36Decoder:
    """Decodes Robot 36 SSTV images from audio.

    Robot 36 uses YUV color space with interlaced chroma:
    - Even scanlines (0, 2, 4...): Y + U (Cb)
    - Odd scanlines (1, 3, 5...): Y + V (Cr)

    Line structure: Sync (9ms) → Porch (3ms) → Y (88ms) → Chroma (88ms) → Porch (3ms)
    """

    def __init__(self, config: Optional[Robot36Config] = None) -> None:
        self._config = config or Robot36Config()
        self._y_buffer: Optional[np.ndarray] = None
        self._u_buffer: Optional[np.ndarray] = None
        self._v_buffer: Optional[np.ndarray] = None
        self._image_buffer: Optional[np.ndarray] = None
        self._current_line = 0
        self._lines_decoded = 0
        self._quality_sum = 0.0

    @property
    def config(self) -> Robot36Config:
        return self._config

    @property
    def width(self) -> int:
        return self._config.width

    @property
    def height(self) -> int:
        return self._config.height

    def reset(self) -> None:
        """Reset decoder state for new image."""
        cfg = self._config
        self._y_buffer = np.zeros((cfg.height, cfg.width), dtype=np.uint8)
        self._u_buffer = np.zeros((cfg.height, cfg.width), dtype=np.uint8)
        self._v_buffer = np.zeros((cfg.height, cfg.width), dtype=np.uint8)
        self._image_buffer = np.zeros((cfg.height, cfg.width, 3), dtype=np.uint8)
        self._current_line = 0
        self._lines_decoded = 0
        self._quality_sum = 0.0

    def _freq_to_luma(self, freq: float) -> int:
        """Convert frequency to luminance value (0-255)."""
        normalized = (freq - self._config.black_freq) / (self._config.white_freq - self._config.black_freq)
        return int(max(0, min(255, normalized * 255)))

    def _samples_to_freq(self, samples: np.ndarray) -> np.ndarray:
        """Estimate instantaneous frequency from samples using zero-crossing."""
        crossings = np.where(np.diff(np.signbit(samples)))[0]

        if len(crossings) < 2:
            return np.full(len(samples), (self._config.black_freq + self._config.white_freq) / 2)

        freqs = np.zeros(len(samples))
        for i in range(len(crossings) - 1):
            period_samples = (crossings[i + 1] - crossings[i]) * 2
            freq = self._config.sample_rate / period_samples if period_samples > 0 else 0
            freqs[crossings[i]:crossings[i + 1]] = freq

        # Fill edges
        if crossings[0] > 0:
            freqs[:crossings[0]] = freqs[crossings[0]]
        if crossings[-1] < len(samples) - 1:
            freqs[crossings[-1]:] = freqs[crossings[-1] - 1] if crossings[-1] > 0 else 1900

        return freqs

    def _decode_channel(self, samples: np.ndarray, target_len: int = 320) -> np.ndarray:
        """Decode a single channel from audio samples.

        Args:
            samples: Audio samples for one channel
            target_len: Number of pixels to decode (default 320)

        Returns:
            Array of pixel values (0-255)
        """
        indices = np.linspace(0, len(samples) - 1, target_len).astype(int)
        freqs = self._samples_to_freq(samples)
        pixel_freqs = freqs[indices]
        pixels = np.array([self._freq_to_luma(f) for f in pixel_freqs], dtype=np.uint8)
        return pixels

    def _yuv_to_rgb(self, y: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
        """Convert YUV to RGB using ITU-R BT.601 standard.

        Args:
            y: Luminance (0-255)
            u: Blue chroma difference (0-255)
            v: Red chroma difference (0-255)

        Returns:
            RGB array (height, width, 3)
        """
        # Convert to float and normalize to -0.5 to 0.5 range for U/V
        y_norm = y.astype(np.float32)
        u_norm = (u.astype(np.float32) - 128.0)
        v_norm = (v.astype(np.float32) - 128.0)

        # ITU-R BT.601 conversion matrix
        r = y_norm + 1.402 * v_norm
        g = y_norm - 0.344136 * u_norm - 0.714136 * v_norm
        b = y_norm + 1.772 * u_norm

        # Clip to valid range
        r = np.clip(r, 0, 255).astype(np.uint8)
        g = np.clip(g, 0, 255).astype(np.uint8)
        b = np.clip(b, 0, 255).astype(np.uint8)

        # Stack into RGB image
        rgb = np.stack([r, g, b], axis=-1)
        return rgb

    def decode_scanline(self, line_samples: np.ndarray, line_number: int) -> ScanlineData:
        """Decode a single scanline from audio samples.

        Args:
            line_samples: Audio samples for complete scanline
            line_number: Line number (0-239)

        Returns:
            ScanlineData with decoded Y and chroma values
        """
        cfg = self._config

        # Calculate offsets for Y and chroma channels
        # Structure: sync + porch + Y + chroma + porch
        offset = cfg.samples_per_sync + cfg.samples_per_porch
        y_start = offset
        y_end = y_start + cfg.samples_per_y_scan

        chroma_start = y_end
        chroma_end = chroma_start + cfg.samples_per_chroma_scan

        # Extract and decode channels
        y_samples = line_samples[y_start:y_end] if y_end <= len(line_samples) else np.zeros(cfg.samples_per_y_scan)
        chroma_samples = line_samples[chroma_start:chroma_end] if chroma_end <= len(line_samples) else np.zeros(cfg.samples_per_chroma_scan)

        y_channel = self._decode_channel(y_samples, cfg.width)
        chroma = self._decode_channel(chroma_samples, cfg.width)

        # Calculate decode quality
        signal_power = np.var(line_samples)
        decode_quality = min(1.0, signal_power * 10) if signal_power > 0 else 0.0

        scanline = ScanlineData(
            line_number=line_number,
            y_channel=y_channel,
            chroma=chroma,
            sync_confidence=0.9,
            decode_quality=decode_quality,
        )

        # Update buffers
        if self._y_buffer is not None and 0 <= line_number < cfg.height:
            self._y_buffer[line_number] = y_channel

            # Even lines carry U (Cb), odd lines carry V (Cr)
            if line_number % 2 == 0:
                if self._u_buffer is not None:
                    self._u_buffer[line_number] = chroma
                    # Interpolate U for odd line below
                    if line_number + 1 < cfg.height:
                        self._u_buffer[line_number + 1] = chroma
            else:
                if self._v_buffer is not None:
                    self._v_buffer[line_number] = chroma
                    # Interpolate V for even line above
                    if line_number > 0:
                        self._v_buffer[line_number - 1] = chroma

            self._lines_decoded += 1
            self._quality_sum += decode_quality

        return scanline

    def decode_stream(self, audio_iterator: Iterator[np.ndarray], sync_positions: list[int]) -> Iterator[ScanlineData]:
        """Decode SSTV image from audio stream with known sync positions.

        Args:
            audio_iterator: Iterator yielding audio sample chunks
            sync_positions: List of sync pulse positions in samples

        Yields:
            ScanlineData for each decoded line
        """
        self.reset()

        # Accumulate audio
        audio_buffer = np.array([], dtype=np.float32)
        for chunk in audio_iterator:
            audio_buffer = np.concatenate([audio_buffer, chunk])

        # Decode each line from sync pulses
        for i, sync_pos in enumerate(sync_positions):
            if i >= self._config.height:
                break

            line_start = sync_pos
            line_end = sync_positions[i + 1] if i + 1 < len(sync_positions) else line_start + self._config.total_line_samples

            if line_end <= len(audio_buffer):
                line_samples = audio_buffer[line_start:line_end]
                scanline = self.decode_scanline(line_samples, i)
                yield scanline

        # Convert YUV to RGB
        if self._y_buffer is not None and self._u_buffer is not None and self._v_buffer is not None:
            self._image_buffer = self._yuv_to_rgb(self._y_buffer, self._u_buffer, self._v_buffer)

    def get_image(self) -> Optional[np.ndarray]:
        """Get the decoded image array.

        Returns:
            RGB image as numpy array (height, width, 3) or None if not decoded
        """
        return self._image_buffer.copy() if self._image_buffer is not None else None

    def get_progress(self) -> DecodeProgress:
        """Get current decode progress."""
        percent = (self._lines_decoded / self._config.height) * 100 if self._config.height > 0 else 0
        avg_quality = self._quality_sum / self._lines_decoded if self._lines_decoded > 0 else 0

        remaining_lines = self._config.height - self._lines_decoded
        line_time_sec = self._config.total_line_samples / self._config.sample_rate
        estimated_remaining = remaining_lines * line_time_sec

        return DecodeProgress(
            lines_decoded=self._lines_decoded,
            total_lines=self._config.height,
            current_line=self._current_line,
            percent_complete=percent,
            estimated_remaining_sec=estimated_remaining,
            signal_quality=avg_quality,
        )
