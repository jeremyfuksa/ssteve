"""Encode->decode roundtrip on gradient content.

The 2026-08-07 audit found all three encoders generated phase-discontinuous
audio: ``_generate_tone`` tracked phase as a sample count, so every frequency
change (every pixel boundary in a gradient) produced a near-full-scale click.
Flat test cards decoded fine, which is why a green suite never saw it -- but
real photographs are gradients everywhere, and they decoded as noise.

These tests are the gate against that whole class of lie: gradient content
must survive the full encode -> sync-detect -> decode pipeline, and the raw
waveform itself must be free of discontinuities.
"""

from __future__ import annotations

import numpy as np
import pytest

from sstv_core.decode.martin_decoder import MartinM1Config, MartinM1Decoder
from sstv_core.decode.robot_decoder import Robot36Config, Robot36Decoder
from sstv_core.decode.scottie_decoder import (
    ScottieS1Config,
    ScottieS1Decoder,
    ScottieS2Config,
)
from sstv_core.decode.sync_detector import SyncPulseDetector
from sstv_core.encode.martin_encoder import MartinM1Encoder
from sstv_core.encode.robot_encoder import Robot36Encoder
from sstv_core.encode.scottie_encoder import (
    ScottieS1Encoder,
    ScottieS2Encoder,
    ScottieS2EncoderConfig,
)

MODES = [
    pytest.param(ScottieS1Encoder, ScottieS1Config, ScottieS1Decoder, 0.95, id="ScottieS1"),
    # Scottie S2 shares S1's structure and decoder; only the scan duration
    # differs. It was the dominant mode on 20m in the 2026-08-16 capture (18
    # of 24 transmissions) and had no decoder at all until #96.
    pytest.param(ScottieS2Encoder, ScottieS2Config, ScottieS1Decoder, 0.95, id="ScottieS2"),
    pytest.param(MartinM1Encoder, MartinM1Config, MartinM1Decoder, 0.95, id="MartinM1"),
    # Robot 36 subsamples chroma across line pairs, so color ramps lose a
    # little fidelity even through a perfect channel.
    pytest.param(Robot36Encoder, Robot36Config, Robot36Decoder, 0.90, id="Robot36"),
]


def gradient_card(width: int, height: int) -> np.ndarray:
    """Every pixel differs from its neighbors in every channel.

    R ramps horizontally, G vertically, B diagonally -- worst case for a
    phase-discontinuous encoder, and channel-swap bugs can't hide in it.
    """
    x = np.linspace(0, 255, width)
    y = np.linspace(0, 255, height)
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:, :, 0] = np.tile(x, (height, 1)).astype(np.uint8)
    img[:, :, 1] = np.tile(y[:, None], (1, width)).astype(np.uint8)
    img[:, :, 2] = ((x[None, :] + y[:, None]) / 2).astype(np.uint8)
    return img


@pytest.mark.parametrize("encoder_cls, config_cls, decoder_cls, min_corr", MODES)
def test_gradient_audio_has_no_phase_discontinuities(
    encoder_cls, config_cls, decoder_cls, min_corr
):
    """A pure tone sweep must never jump sample-to-sample.

    At 48 kHz a <=2300 Hz sine at 0.8 amplitude moves at most ~0.24 between
    consecutive samples. Phase discontinuities show up as jumps of 1.0+.
    """
    enc = encoder_cls()
    img = gradient_card(enc.config.width, enc.config.height)
    audio = enc.encode_image(img, include_vis=True)
    max_jump = float(np.max(np.abs(np.diff(audio))))
    assert max_jump < 0.30, (
        f"waveform discontinuity {max_jump:.3f} -- encoder is emitting clicks"
    )


@pytest.mark.parametrize("encoder_cls, config_cls, decoder_cls, min_corr", MODES)
def test_gradient_roundtrip_through_real_pipeline(
    encoder_cls, config_cls, decoder_cls, min_corr
):
    """Gradient card survives encode -> sync detect -> decode."""
    enc = encoder_cls()
    width, height = enc.config.width, enc.config.height
    sample_rate = enc.config.sample_rate
    img = gradient_card(width, height)
    audio = enc.encode_image(img, include_vis=True)

    detector = SyncPulseDetector(sample_rate=sample_rate)
    detector.detect_in_buffer(audio)
    line_ms = 1000.0 * _total_line_samples(config_cls()) / sample_rate
    positions = detector.get_sync_positions(line_duration_ms=line_ms)
    assert positions, "no sync pulses found in clean generated audio"

    decoder = decoder_cls(config_cls(sample_rate=sample_rate))
    for _ in decoder.decode_stream(iter([audio]), positions):
        pass
    decoded = decoder.get_image()
    assert decoded is not None

    # Crop edges: first/last lines and leftmost columns carry sync-timing
    # slop that isn't what this test is about.
    o = img[10:-10, 10:-10].astype(np.float64)
    d = decoded[10:-10, 10:-10].astype(np.float64)
    for ch, name in enumerate("RGB"):
        corr = float(np.corrcoef(o[:, :, ch].ravel(), d[:, :, ch].ravel())[0, 1])
        assert corr >= min_corr, f"{name} channel corr {corr:.3f} < {min_corr}"


def _total_line_samples(config) -> int:
    if hasattr(config, "total_line_samples"):
        return int(config.total_line_samples)
    # Robot36Config exposes per-line duration instead.
    return int(config.sample_rate * config.line_duration_ms / 1000)
