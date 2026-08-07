"""FM demodulation for SSTV video: audio frequency to instantaneous frequency.

SSTV encodes brightness as a continuous audio frequency -- 1500 Hz is black,
2300 Hz is white, and every value between is a shade. Recovering the picture
means recovering that frequency accurately at every sample.

The three decoders previously each carried an identical zero-crossing
estimator: count sign changes, derive a period, convert to a frequency. That
cannot work, because the period is quantised to whole samples. In the
1500-2300 Hz video band it yields:

    11025 Hz sample rate -> 1 representable frequency
    22050 Hz sample rate -> 3
    48000 Hz sample rate -> 2

So a decoder built on it can only ever emit one to three distinct grey levels
out of 256, whatever the signal. Measured against the reference corpus, the
decoded images were flat grey.

This module replaces it with the standard approach the old code's own comment
pointed at: build the analytic signal with a Hilbert transform, take the
derivative of its unwrapped phase, and scale to Hz. Frequency is then
continuous and limited by noise rather than by sample quantisation.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import hilbert

# Below this RMS the block is silence or dropout; phase of near-zero samples is
# meaningless and would produce wild frequency excursions.
_MIN_RMS = 1e-6


def instantaneous_frequency(
    samples: np.ndarray,
    sample_rate: int,
    *,
    smooth: int = 0,
) -> np.ndarray:
    """Estimate instantaneous frequency in Hz for every sample.

    Args:
        samples: Real audio samples, one channel.
        sample_rate: Samples per second.
        smooth: If > 1, width of a moving-average applied to the frequency
            track. SSTV pixels are many samples wide, so light smoothing
            trades resolution the picture does not have for noise rejection.

    Returns:
        Array of frequencies in Hz, same length as `samples`.

    """
    n = len(samples)
    if n < 4:
        return np.zeros(n, dtype=np.float64)

    x = samples.astype(np.float64)

    rms = float(np.sqrt(np.mean(x * x)))
    if rms < _MIN_RMS:
        return np.zeros(n, dtype=np.float64)

    # Analytic signal: the real input plus its Hilbert transform as the
    # imaginary part. Its phase advances at the signal's instantaneous
    # frequency.
    analytic = hilbert(x)
    phase = np.unwrap(np.angle(analytic))

    # d(phase)/dt, in Hz. np.gradient uses central differences internally and
    # one-sided differences at the edges, so the result keeps full length
    # without the edge artefacts np.diff would introduce.
    freq = np.gradient(phase) * (sample_rate / (2.0 * np.pi))

    if smooth > 1:
        kernel = np.ones(smooth, dtype=np.float64) / smooth
        freq = np.convolve(freq, kernel, mode="same")

    return np.asarray(freq, dtype=np.float64)


def frequencies_to_luma(
    freqs: np.ndarray,
    black_freq: float,
    white_freq: float,
) -> np.ndarray:
    """Map video-band frequencies to 8-bit luminance.

    Args:
        freqs: Frequencies in Hz.
        black_freq: Frequency representing black (typically 1500 Hz).
        white_freq: Frequency representing white (typically 2300 Hz).

    Returns:
        uint8 array of luminance values, clipped to 0-255.

    """
    span = white_freq - black_freq
    if span == 0:
        return np.zeros(len(freqs), dtype=np.uint8)

    normalized = (freqs - black_freq) / span
    return np.clip(normalized * 255.0, 0.0, 255.0).astype(np.uint8)


def channel_window(
    line_samples: np.ndarray,
    start: int,
    end: int,
    *,
    min_fraction: float = 0.5,
) -> np.ndarray:
    """Slice one channel's samples out of a scanline, tolerating a short line.

    Args:
        line_samples: Audio for the whole scanline.
        start: First sample of this channel.
        end: One past the last sample of this channel.
        min_fraction: Least fraction of the window that must be present for
            the slice to be considered usable.

    Returns:
        The available samples, or an empty array when too little is present.

    Line boundaries come from measured sync spacing, so a scanline is
    routinely a few samples shorter than the nominal geometry -- transmitter
    and receiver clock mismatch alone accounts for it. Decoders previously
    guarded each channel with `if end <= len(line)` and substituted zeros
    otherwise, which turned a three-sample shortfall into a wholly zeroed
    colour channel. In Robot 36 that drove U and V to 0 rather than the
    neutral 128 and cast every decode green.

    Taking the available samples is right because the demodulator resamples
    to the output width anyway: a channel missing its last 0.2% produces a
    pixel row stretched by 0.2%, which is invisible. Returning empty below
    `min_fraction` keeps a genuinely truncated line from inventing detail.

    """
    if start >= len(line_samples):
        return np.zeros(0, dtype=line_samples.dtype)

    available = line_samples[start:min(end, len(line_samples))]
    if len(available) < (end - start) * min_fraction:
        return np.zeros(0, dtype=line_samples.dtype)

    return available


def demodulate_channel(
    samples: np.ndarray,
    sample_rate: int,
    width: int,
    black_freq: float,
    white_freq: float,
) -> np.ndarray:
    """Demodulate one colour channel's audio into a row of pixels.

    Averages the frequency track across each pixel's own span of samples
    rather than point-sampling it. A pixel covers many samples (at 22050 Hz a
    Scottie S1 pixel is roughly 10), and averaging over them rejects noise
    that single-point sampling would carry straight into the picture.

    Args:
        samples: Audio for this colour channel.
        sample_rate: Samples per second.
        width: Output pixel count.
        black_freq: Frequency representing black.
        white_freq: Frequency representing white.

    Returns:
        uint8 array of `width` luminance values.

    """
    if len(samples) == 0:
        # Mid-scale, not zero. For a colour-difference channel zero is fully
        # saturated, so a missing channel would paint a vivid cast across the
        # image; mid-scale is neutral and reads as "no information", which is
        # the truth. For luminance it is mid-grey, which is equally honest.
        return np.full(width, 128, dtype=np.uint8)

    freqs = instantaneous_frequency(samples, sample_rate)

    # Pixel boundaries across the channel's samples.
    edges = np.linspace(0, len(freqs), width + 1)
    starts = edges[:-1].astype(int)
    ends = np.maximum(edges[1:].astype(int), starts + 1)

    pixel_freqs = np.array(
        [float(np.mean(freqs[s:e])) for s, e in zip(starts, ends, strict=True)],
        dtype=np.float64,
    )

    return frequencies_to_luma(pixel_freqs, black_freq, white_freq)
