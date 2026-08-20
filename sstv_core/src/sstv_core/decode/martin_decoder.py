"""Martin M1 SSTV mode decoder.

Martin M1 specifications:
- Resolution: 320x256 pixels
- VIS code: 44
- Sync pulse: 4.862ms at 1200 Hz
- Color sequence: Green, Blue, Red
- Scanline time per color: 146.43ms
- Total line time: ~446.45ms
- Frequency mapping: 1500 Hz = black, 2300 Hz = white
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np

from sstv_core.decode.demodulator import (
    channel_window as _window,
)
from sstv_core.decode.demodulator import (
    demodulate_channel,
    instantaneous_frequency,
)

logger = logging.getLogger(__name__)


@dataclass
class MartinM1Config:
    """Martin M1 mode configuration."""

    width: int = 320
    height: int = 256
    sync_duration_ms: float = 4.862
    separator_duration_ms: float = 0.572
    color_scan_duration_ms: float = 146.43
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

    @property
    def total_line_samples(self) -> int:
        """Samples in one scanline: sync + 4 separators + 3 colour scans.

        Four separators, not three: one follows the sync pulse and one follows
        each colour channel. Sums to the specified 446.446ms at the defaults.
        Derived rather than hardcoded so the parts cannot drift from the total.
        """
        line_ms = (
            self.sync_duration_ms
            + 4 * self.separator_duration_ms
            + 3 * self.color_scan_duration_ms
        )
        return int(self.sample_rate * line_ms / 1000)


@dataclass
class MartinM2Config(MartinM1Config):
    """Martin M2 mode configuration.

    M1 with half the colour scan, which is the whole difference between them:
    ~58s per frame against M1's ~114s. As with `ScottieS2Config`, subclassing
    leaves the line arithmetic in one place -- 73.216ms here yields the
    published 226.798ms line time without that total being written down
    anywhere it could drift from its parts.
    """

    color_scan_duration_ms: float = 73.216


@dataclass
class ScanlineData:
    """Decoded scanline data."""

    line_number: int
    green: np.ndarray
    blue: np.ndarray
    red: np.ndarray
    sync_confidence: float = 0.0
    decode_quality: float = 0.0

    def to_rgb_row(self) -> np.ndarray:
        """Convert to RGB row array (height=1, width=320, channels=3)."""
        rgb = np.zeros((self.green.shape[0], 3), dtype=np.uint8)
        rgb[:, 0] = self.red
        rgb[:, 1] = self.green
        rgb[:, 2] = self.blue
        return rgb

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


class MartinM1Decoder:
    """Decodes Martin M1 SSTV images from audio.

    Martin M1 line structure (after sync):
    1. Sync pulse (4.862ms at 1200Hz)
    2. Separator (0.572ms at 1500Hz)
    3. Green scan (146.43ms)
    4. Separator (0.572ms at 1500Hz)
    5. Blue scan (146.43ms)
    6. Separator (0.572ms at 1500Hz)
    7. Red scan (146.43ms)
    """

    def __init__(self, config: MartinM1Config | None = None) -> None:
        self._config = config or MartinM1Config()
        self._image_buffer: np.ndarray | None = None
        self._current_line = 0
        self._lines_decoded = 0
        self._quality_sum = 0.0
        self._decode_start_time = 0.0

    @property
    def line_start_offset(self) -> int:
        """Samples from a detected sync pulse to the start of its line.

        Zero: Martin's `decode_scanline` receives the sync pulse at the head
        of the buffer and skips it itself. Stated explicitly rather than left
        to a default so the convention is visible where it is decided --
        Scottie takes the opposite one, and a caller assuming either for all
        modes shifts the image (#101).
        """
        return 0

    @property
    def config(self) -> MartinM1Config:
        return self._config

    @property
    def width(self) -> int:
        return self._config.width

    @property
    def height(self) -> int:
        return self._config.height

    def reset(self) -> None:
        """Reset decoder state for new image."""
        self._image_buffer = np.zeros(
            (self._config.height, self._config.width, 3),
            dtype=np.uint8
        )
        self._current_line = 0
        self._lines_decoded = 0
        self._quality_sum = 0.0

    def _freq_to_luma(self, freq: float) -> int:
        """Convert frequency to luminance value (0-255)."""
        # Linear interpolation: 1500Hz -> 0, 2300Hz -> 255
        normalized = (freq - self._config.black_freq) / (
            self._config.white_freq - self._config.black_freq
        )
        return int(max(0, min(255, normalized * 255)))

    def _samples_to_freq(self, samples: np.ndarray) -> np.ndarray:
        """Estimate instantaneous frequency from samples.

        Hilbert transform and phase derivative; see `demodulator` for why the
        previous zero-crossing estimator could not work.
        """
        return instantaneous_frequency(samples, self._config.sample_rate)

    def _decode_color_channel(self, samples: np.ndarray) -> np.ndarray:
        """Decode a single color channel from audio samples.

        Args:
            samples: Audio samples for one color channel (~146ms)

        Returns:
            Array of 320 pixel values (0-255)

        """
        return demodulate_channel(
            samples,
            self._config.sample_rate,
            self._config.width,
            self._config.black_freq,
            self._config.white_freq,
        )

    def decode_scanline(self, line_samples: np.ndarray, line_number: int) -> ScanlineData:
        """Decode a single scanline from audio samples.

        Args:
            line_samples: Audio samples for complete scanline
            line_number: Line number (0-255)

        Returns:
            ScanlineData with decoded RGB values

        """
        cfg = self._config
        samples_per_sep = cfg.samples_per_separator
        samples_per_color = cfg.samples_per_color_line

        # Calculate offsets for each color channel
        # Structure: sync + sep + green + sep + blue + sep + red
        offset = cfg.samples_per_sync + samples_per_sep
        green_start = offset
        green_end = green_start + samples_per_color

        offset = green_end + samples_per_sep
        blue_start = offset
        blue_end = blue_start + samples_per_color

        offset = blue_end + samples_per_sep
        red_start = offset
        red_end = red_start + samples_per_color

        # Take whatever of each window is present; see channel_window for why
        # an all-or-nothing guard silently destroyed channels on short lines.
        green_samples = _window(line_samples, green_start, green_end)
        blue_samples = _window(line_samples, blue_start, blue_end)
        red_samples = _window(line_samples, red_start, red_end)

        green = self._decode_color_channel(green_samples)
        blue = self._decode_color_channel(blue_samples)
        red = self._decode_color_channel(red_samples)

        # Calculate decode quality (based on signal variance)
        signal_power = np.var(line_samples)
        decode_quality = min(1.0, signal_power * 10) if signal_power > 0 else 0.0

        scanline = ScanlineData(
            line_number=line_number,
            green=green,
            blue=blue,
            red=red,
            sync_confidence=0.9,  # Would be set by sync detector
            decode_quality=decode_quality,
        )

        # Update image buffer
        if self._image_buffer is not None and 0 <= line_number < self._config.height:
            self._image_buffer[line_number] = scanline.to_rgb_row()
            self._lines_decoded += 1
            self._quality_sum += decode_quality

        return scanline

    def decode_stream(
        self, audio_iterator: Iterator[np.ndarray], sync_positions: list[int]
    ) -> Iterator[ScanlineData]:
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

            # Calculate line boundaries (include sync pulse in line)
            line_start = sync_pos
            line_end = (
                sync_positions[i + 1]
                if i + 1 < len(sync_positions)
                else line_start + self._config.total_line_samples
            )

            if line_end <= len(audio_buffer):
                line_samples = audio_buffer[line_start:line_end]
                scanline = self.decode_scanline(line_samples, i)
                yield scanline

    @property
    def image_buffer(self) -> np.ndarray | None:
        """Rows decoded so far, for the progressive canvas (#55).

        The live buffer, not a copy: a caller reads the slice it needs
        and the decoder keeps writing. Undecoded rows are still zero.
        """
        return self._image_buffer

    def get_image(self) -> np.ndarray | None:
        """Get the decoded image array.

        Returns:
            RGB image as numpy array (height, width, 3) or None if not decoded

        """
        return self._image_buffer.copy() if self._image_buffer is not None else None

    def get_progress(self) -> DecodeProgress:
        """Get current decode progress."""
        percent = (
            (self._lines_decoded / self._config.height) * 100 if self._config.height > 0 else 0
        )
        avg_quality = self._quality_sum / self._lines_decoded if self._lines_decoded > 0 else 0

        # Estimate remaining time
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
