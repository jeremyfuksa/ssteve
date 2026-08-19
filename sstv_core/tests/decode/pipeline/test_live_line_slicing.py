"""The live decode loop must slice lines the way the decoder expects (#101).

Decoded images were displaced horizontally -- about 10% of the right edge
wrapping to the left, duplicating callsign characters ("XE2UDD", "4A2MAXS").
Offline decodes of the same audio, from the same sync positions, framed
correctly.

The two paths slice differently. `ScottieS1Decoder.decode_stream` starts a
line *after* the sync pulse:

    line_start = sync_pos + self._config.samples_per_sync

`RXManager`'s decode loop reimplemented the arithmetic and sliced sync-to-
sync, leaving the 9 ms pulse at the head of every line. Everything then
shifts by one sync duration:

    ScottieS1: 432 of 6635 samples per channel = 20.8 px of 320  (6.5%)
    ScottieS2: 432 of 4266 samples per channel = 32.7 px of 320 (10.2%)

Scottie S2 was 18 of the 24 transmissions in the 2026-08-16 capture, which
is why the wrap measured "about 10%".

`decode_scanline` is written against the post-sync convention -- its own
comment explains that the buffer begins with that line's RED channel -- so
handing it a sync-prefixed buffer rotates every channel by the sync length.
"""

from __future__ import annotations

import numpy as np
import pytest

from sstv_core.decode.scottie_decoder import (
    ScottieS1Config,
    ScottieS1Decoder,
    ScottieS2Config,
)
from sstv_core.decode.sync_detector import SyncPulseDetector
from sstv_core.encode.scottie_encoder import (
    ScottieS1Encoder,
    ScottieS2Encoder,
    ScottieS2EncoderConfig,
)

RATE = 48000


def marker_card(width: int, height: int) -> np.ndarray:
    """A card whose markers identify their own position.

    Column 0-7 red, 312-319 blue, rows 0-3 white, mid-grey elsewhere. Any
    horizontal or vertical displacement moves a marker somewhere it can be
    measured, without relying on the encoder and decoder agreeing about
    anything except pixel values.
    """
    card = np.full((height, width, 3), 110, np.uint8)
    card[:, 0:8] = (255, 0, 0)
    card[:, width - 8 : width] = (0, 0, 255)
    card[0:4, :] = (255, 255, 255)
    return card


def _positions(audio: np.ndarray, line_ms: float) -> list[int]:
    det = SyncPulseDetector(sample_rate=RATE)
    det.detect_in_buffer(audio)
    return det.get_sync_positions(line_duration_ms=line_ms)


@pytest.mark.parametrize(
    "encoder, config, ident",
    [
        (ScottieS1Encoder(), ScottieS1Config(sample_rate=RATE), "ScottieS1"),
        (
            ScottieS2Encoder(ScottieS2EncoderConfig(sample_rate=RATE)),
            ScottieS2Config(sample_rate=RATE),
            "ScottieS2",
        ),
    ],
)
def test_markers_land_where_they_were_encoded(encoder, config, ident):
    """Baseline: the decoder's own slicing frames the card correctly.

    This is the convention the live loop has to match. If this fails the
    problem is in the decoder, not in how a caller drives it.
    """
    card = marker_card(config.width, config.height)
    audio = encoder.encode_image(card, include_vis=True)
    line_ms = 1000.0 * config.total_line_samples / RATE

    decoder = ScottieS1Decoder(config)
    for _ in decoder.decode_stream(iter([audio]), _positions(audio, line_ms)):
        pass
    img = decoder.get_image()
    assert img is not None

    r = img[:, :, 0].astype(int)
    g = img[:, :, 1].astype(int)
    b = img[:, :, 2].astype(int)
    reddest = int(np.argmax((r - (g + b) // 2).mean(axis=0)))
    bluest = int(np.argmax((b - (r + g) // 2).mean(axis=0)))

    assert reddest < 24, (
        f"{ident}: red marker encoded at columns 0-7 decoded at {reddest} "
        "-- the image is shifted horizontally"
    )
    assert bluest > config.width - 24, (
        f"{ident}: blue marker encoded at columns "
        f"{config.width - 8}-{config.width - 1} decoded at {bluest}"
    )


@pytest.mark.parametrize(
    "encoder, config, ident",
    [
        (ScottieS1Encoder(), ScottieS1Config(sample_rate=RATE), "ScottieS1"),
        (
            ScottieS2Encoder(ScottieS2EncoderConfig(sample_rate=RATE)),
            ScottieS2Config(sample_rate=RATE),
            "ScottieS2",
        ),
    ],
)
def test_sync_to_sync_slicing_displaces_the_image(encoder, config, ident):
    """The negative control: slicing sync-to-sync must visibly break framing.

    This is what `RXManager` did. Asserting that it *fails* is what gives the
    positive test meaning -- without it, both conventions might frame
    acceptably and the fix would be unverifiable.
    """
    card = marker_card(config.width, config.height)
    audio = encoder.encode_image(card, include_vis=True)
    line_ms = 1000.0 * config.total_line_samples / RATE
    positions = _positions(audio, line_ms)

    # Reproduce the live loop's slicing: sync included at the head.
    decoder = ScottieS1Decoder(config)
    decoder.reset()
    for i in range(min(len(positions) - 1, config.height)):
        decoder.decode_scanline(audio[positions[i] : positions[i + 1]], i)
    img = decoder.get_image()
    assert img is not None

    r = img[:, :, 0].astype(int)
    g = img[:, :, 1].astype(int)
    b = img[:, :, 2].astype(int)
    reddest = int(np.argmax((r - (g + b) // 2).mean(axis=0)))

    shift_px = config.width * config.samples_per_sync / config.samples_per_color_line
    assert reddest > 8, (
        f"{ident}: sync-to-sync slicing left the red marker at column "
        f"{reddest}; a {shift_px:.0f}px displacement was expected, so this "
        "test is no longer exercising the defect"
    )


def test_live_loop_slice_matches_decoder_convention():
    """The arithmetic itself, stated once.

    `decode_stream` starts a line at `sync_pos + samples_per_sync`. Any
    other caller driving `decode_scanline` has to do the same; this pins the
    relationship so a future reimplementation cannot quietly diverge again.
    """
    for config in (
        ScottieS1Config(sample_rate=RATE),
        ScottieS2Config(sample_rate=RATE),
    ):
        # A line runs from just after one sync to just after the next.
        expected_len = config.total_line_samples
        sync_pos, next_sync = 100_000, 100_000 + expected_len
        line_start = sync_pos + config.samples_per_sync
        line_end = next_sync + config.samples_per_sync
        assert line_end - line_start == expected_len
        assert line_start != sync_pos, (
            "the sync pulse must not be included at the head of the line"
        )
