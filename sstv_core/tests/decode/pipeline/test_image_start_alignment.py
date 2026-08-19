"""Decoding must begin at the picture, not at the first stray pulse (#102).

Every decoded image carried a noise band across the top and the picture
began around halfway down -- median first content row 131/256 on the
2026-08-16 capture and 143/256 on 2026-08-17, consistent across two nights,
different stations and both Scottie modes.

`decode_stream` consumes `sync_positions[0..255]`, and those positions
include pulses found before the transmission begins: picture content and
noise from other signals momentarily resemble 1200 Hz. Mapping sync
regularity for one Scottie S2 transmission (71.1 s frame), relative to the
located marker:

    -8s  0.30   +17s  0.33   +47s  1.00   +92s  0.56
    -3s  0.53   +22s  0.94   +52s  1.00   +97s  0.29
    +2s  0.29   +27s  1.00   ...
    +7s  0.35   +32s  0.82

The picture runs +22s to +92s. The decoder consumed -7.9s to +61.1s, so it
filled the top ~108 lines with pre-transmission noise and then ran out of
lines partway through the real picture -- one offset producing both the
noise band and the truncation.

The image start is therefore the beginning of a sustained run of pulses one
line apart. This has to hold on a *stream*, where the decoder cannot look
ahead at pulses it has not received: the tests below drive the real
RXManager at wall-clock-ish rates rather than scanning a finished list,
because an offline-only result would not transfer (the lesson of #99, #100
and #101).
"""

from __future__ import annotations

import asyncio
import threading
import time

import numpy as np
import pytest

from sstv_core.audio.ring_buffer import AudioRingBuffer
from sstv_core.audio.stream_manager import AudioLevels
from sstv_core.decode.rx_manager import RXManager
from sstv_core.encode.scottie_encoder import (
    ScottieS1Encoder,
    ScottieS2Encoder,
    ScottieS2EncoderConfig,
)

SAMPLE_RATE = 48000


def picture_card(width: int, height: int) -> np.ndarray:
    """A card whose very first rows carry unmistakable content.

    Row 0-15 is pure white. If decoding starts late the white band moves up
    and off; if it starts early the band appears lower with noise above it.
    Either way the band's position measures the error directly.
    """
    card = np.full((height, width, 3), 90, np.uint8)
    card[0:16, :] = (255, 255, 255)
    x = np.linspace(0, 255, width)
    card[16:, :, 0] = np.tile(x, (height - 16, 1)).astype(np.uint8)
    card[16:, :, 2] = 200
    return card


class PrefixedSource:
    """Silence, then noise, then the transmission -- what a real band gives.

    The noise section is what produces the stray 1200 Hz detections that
    `sync_positions[0]` lands in. Without it a test starts at the picture by
    accident and proves nothing.
    """

    sample_rate = SAMPLE_RATE

    def __init__(self, audio: np.ndarray, *, noise_sec: float = 12.0,
                 speed: float = 8.0, chunk_ms: float = 100.0) -> None:
        rng = np.random.default_rng(20260817)
        n = int(noise_sec * SAMPLE_RATE)
        # Band-limited noise around the SSTV range, loud enough that the
        # detector finds spurious pulses in it.
        t = np.arange(n) / SAMPLE_RATE
        wobble = 1500 + 700 * np.sin(2 * np.pi * 0.7 * t)
        noise = (
            np.sin(2 * np.pi * np.cumsum(wobble) / SAMPLE_RATE) * 0.5
            + rng.standard_normal(n) * 0.25
        ).astype(np.float32)
        self._audio = np.concatenate(
            [np.zeros(SAMPLE_RATE, np.float32), noise, np.asarray(audio, np.float32)]
        )
        self._picture_start = SAMPLE_RATE + n
        self._speed = speed
        self._chunk = max(1, int(SAMPLE_RATE * chunk_ms / 1000.0))
        self._buffer: AudioRingBuffer | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.fed = 0

    @property
    def picture_start_sec(self) -> float:
        return self._picture_start / SAMPLE_RATE

    def start_input(self, device_index=None, callback=None, buffer_size=None):
        self._buffer = AudioRingBuffer(
            max_samples=len(self._audio) + SAMPLE_RATE, sample_rate=SAMPLE_RATE
        )
        self._stop.clear()
        self._thread = threading.Thread(target=self._feed, daemon=True)
        self._thread.start()

    def _feed(self) -> None:
        assert self._buffer is not None
        origin = time.monotonic()
        while not self._stop.is_set() and self.fed < len(self._audio):
            block = self._audio[self.fed : self.fed + self._chunk]
            if not len(block):
                break
            self._buffer.add(block)
            self.fed += len(block)
            target = origin + (self.fed / SAMPLE_RATE) / self._speed
            delay = target - time.monotonic()
            if delay > 0:
                self._stop.wait(delay)

    def stop_input(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def get_input_buffer(self):
        assert self._buffer is not None
        return self._buffer

    def get_input_levels(self) -> AudioLevels:
        return AudioLevels(rms=0.3, peak=0.9)


async def _decode(audio: np.ndarray, mode: str, tmp_path, *,
                  noise_sec: float = 12.0, hard_limit: float = 120.0) -> np.ndarray:
    """Run one receive and return the decoded image.

    RXManager exposes no in-memory image accessor, so the image is read back
    from the file it saves -- which exercises the whole path the operator
    actually gets.
    """
    source = PrefixedSource(audio, noise_sec=noise_sec)
    rx = RXManager(
        stream_manager=source, sample_rate=SAMPLE_RATE, save_directory=tmp_path
    )
    saved = await asyncio.wait_for(
        rx.receive(mode=mode, timeout_sec=30.0, save_image=True),
        timeout=hard_limit,
    )
    assert saved is not None, "decode produced no image at all"
    cv2 = pytest.importorskip("cv2", reason="opencv not installed")
    image = cv2.imread(str(saved))
    assert image is not None, f"could not read back {saved}"
    return image.astype(np.float64)


def _white_band_row(image: np.ndarray) -> int:
    """Row where the card's white marker band lands.

    The card opens with 16 rows of pure white on a mid-grey/gradient body,
    so the brightest row IS the top of the picture. Measuring the marker
    rather than "where noise stops" keeps the test honest when the decode is
    clean: a uniformly good image has no noise boundary to find, and a
    metric looking for one reports failure on a perfect result.
    """
    luma = image.mean(axis=2)
    brightest = float(luma.mean(axis=1).max())
    floor = float(np.median(luma))
    threshold = floor + (brightest - floor) * 0.6
    rows = np.flatnonzero(luma.mean(axis=1) > threshold)
    return int(rows[0]) if len(rows) else len(luma)


@pytest.mark.integration
@pytest.mark.parametrize(
    "encoder, ident",
    [
        (ScottieS1Encoder(), "ScottieS1"),
        (ScottieS2Encoder(ScottieS2EncoderConfig(sample_rate=SAMPLE_RATE)), "ScottieS2"),
    ],
)
async def test_picture_starts_at_the_top_of_the_frame(encoder, ident, tmp_path):
    """The regression gate for #102, driven through the live path.

    Twelve seconds of band-like noise precede the transmission, which is
    what puts stray pulses in front of the real ones. The decoded image must
    still open on the picture.
    """
    card = picture_card(encoder.config.width, encoder.config.height)
    audio = encoder.encode_image(card, include_vis=True)

    image = await _decode(audio, ident, tmp_path)

    first = _white_band_row(image)
    assert first < 24, (
        f"{ident}: the card's white top band decoded at row {first} of "
        f"{encoder.config.height}; rows above it are pre-transmission "
        "noise (#102)"
    )


@pytest.mark.integration
async def test_noise_before_the_signal_does_not_move_the_start(tmp_path):
    """More leading noise must not push the picture further down.

    This is the shape of #102 stated as an invariant: the amount of junk
    before a transmission is a property of the band, and it must not change
    where the image begins.
    """
    encoder = ScottieS2Encoder(ScottieS2EncoderConfig(sample_rate=SAMPLE_RATE))
    card = picture_card(encoder.config.width, encoder.config.height)
    audio = encoder.encode_image(card, include_vis=True)

    rows = []
    for noise_sec in (4.0, 16.0):
        image = await _decode(audio, "ScottieS2", tmp_path, noise_sec=noise_sec)
        rows.append(_white_band_row(image))

    assert abs(rows[0] - rows[1]) < 16, (
        f"the picture's top band landed at row {rows[0]} with 4s of leading "
        f"noise and {rows[1]} with 16s -- the start is tracking the noise, "
        "not the signal (#102)"
    )
