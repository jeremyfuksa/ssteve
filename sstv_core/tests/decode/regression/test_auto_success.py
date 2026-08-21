"""How often the unattended path produces the right picture, with no help.

The rest of this package asks "did this change break decoding". This file
asks a product question instead: if an operator starts SSTeVe and walks
away, how often do they come back to a correct image?

That is a different measurement, and it needs a different setup. The
regression suite hands `_decode` the mode straight out of `manifest.json`,
which is right for pinning a render but wrong here -- it tells the decoder
the answer. Nothing supplies the mode on the air. So the run below reads the
mode from the VIS header, picks the decoder from *that*, and only consults
the manifest afterwards to mark the attempt right or wrong.

Success is the pinned render, byte for byte. It is tempting to score this
more softly -- "did it finish", "does it look like a picture" -- and every
soft score tried in this repo has been worthless. Measured against a decoder
carrying a 9% Martin M1 timing error that visibly smears the subject away:
adjacent-scanline correlation moved 0.7638 to 0.7614, lit fraction stayed at
65%, and channel correlation *rose* on three of six files. Uniform random
noise scores 96% lit. The picture is the only honest oracle, so an attempt
counts only if it detected the right mode, decoded, and landed on the exact
pixels in `reference/images/offair_decoded/`.

**The rate this reports is an upper bound, not a field number.** Two reasons,
both structural:

  * The corpus is 6 Scottie S2, 5 Martin M1, 3 Martin M2 -- only modes that
    already have decoders. Robot 72 and PD 120 are common on 14.230 and are
    absent here, so real air contains transmissions this corpus cannot
    represent and the unattended path would refuse.
  * These are recorded files at fixed level. Gain is the one setting with no
    correct default (`SpyServerSettings.gain` is None precisely because 0 is
    both legal and deaf on an Airspy HF+), and a WAV cannot exercise an AGC
    that is not there. Nothing below says anything about gain.

Read the number as "of the transmissions we can decode at all, how many need
no human", and keep both caveats attached to it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest
from PIL import Image

from sstv_core.decode.correlation_vis_detector import (
    CorrelationVISConfig,
    CorrelationVISDetector,
)
from sstv_core.decode.sync_detector import SyncPulseDetector

from .test_offair_corpus import (
    DECODERS,
    ENTRIES,
    IDS,
    RENDERS,
    _load,
)

pytestmark = pytest.mark.skipif(not ENTRIES, reason="off-air corpus not present")

#: Chunk size for feeding VIS detection. 4096 is what a live caller would
#: plausibly use, and `test_vis_detection_does_not_depend_on_chunk_size` in
#: the sibling module already proves the answer does not hinge on it -- so
#: this file spends its time on the decode instead of re-sweeping buffering.
CHUNK = 4096


@dataclass
class Attempt:
    """One unattended run, scored."""

    file: str
    expected_mode: str
    detected_mode: str | None
    lines: int
    pixels_match: bool

    @property
    def mode_ok(self) -> bool:
        return self.detected_mode == self.expected_mode

    @property
    def decoded(self) -> bool:
        return self.lines > 0

    @property
    def succeeded(self) -> bool:
        """Right mode, a decode, and the picture we accepted."""
        return self.mode_ok and self.decoded and self.pixels_match

    def why_failed(self) -> str:
        if not self.mode_ok:
            got = self.detected_mode or "nothing"
            return f"read {got}, expected {self.expected_mode}"
        if not self.decoded:
            return "mode detected but no scanlines decoded"
        if not self.pixels_match:
            return "decoded, but not the accepted render"
        return ""


def _run_unattended(entry: dict) -> Attempt:
    """Decode one fixture the way an unattended session would.

    The manifest's mode is deliberately not passed in -- it is only read at
    the end, to score what the VIS header chose.
    """
    audio, rate = _load(entry)

    detector = CorrelationVISDetector(CorrelationVISConfig(sample_rate=rate))
    detected_mode: str | None = None
    for offset in range(0, len(audio), CHUNK):
        result = detector.process_samples(audio[offset : offset + CHUNK])
        if result is not None and result.mode is not None:
            detected_mode = result.mode.name
            break

    attempt = Attempt(
        file=entry["file"],
        expected_mode=entry["mode"],
        detected_mode=detected_mode,
        lines=0,
        pixels_match=False,
    )

    # An undecodable mode is a legitimate unattended outcome, not a crash:
    # rx_manager stops the session with a named reason. Score it as a miss
    # and carry on -- this is exactly the case Robot 72 and PD 120 will hit.
    if detected_mode is None or detected_mode not in DECODERS:
        return attempt

    decoder_cls, config_cls, line_ms = DECODERS[detected_mode]
    config = config_cls(sample_rate=rate)

    sync = SyncPulseDetector(sample_rate=rate)
    sync.detect_in_buffer(audio)
    positions = sync.get_sync_positions(line_duration_ms=line_ms)
    if not positions:
        return attempt

    decoder = decoder_cls(config)
    attempt.lines = sum(1 for _ in decoder.decode_stream(iter([audio]), positions))
    image = decoder.get_image()
    if image is None:
        return attempt

    reference = RENDERS / entry["file"].replace(".wav", ".png")
    if not reference.exists():
        return attempt

    expected = np.array(Image.open(reference).convert("RGB"), dtype=np.int16)
    actual = np.asarray(image, dtype=np.int16)
    if actual.shape != expected.shape:
        return attempt

    attempt.pixels_match = bool((np.abs(actual - expected).max(axis=2) > 0).mean() == 0.0)
    return attempt


@pytest.mark.slow
@pytest.mark.parametrize("entry", ENTRIES, ids=IDS)
def test_unattended_run_produces_the_accepted_picture(entry: dict) -> None:
    """Each transmission decodes correctly with nothing supplied by hand.

    Per-fixture rather than one aggregate assertion so a failure names the
    file that regressed instead of moving a percentage.
    """
    attempt = _run_unattended(entry)
    assert attempt.succeeded, f"{attempt.file}: {attempt.why_failed()}"


@pytest.mark.slow
def test_auto_success_rate_is_total() -> None:
    """Every fixture in the corpus succeeds unattended.

    The rate is 14/14 as of 2026-08-20. This asserts the whole corpus rather
    than a threshold: a fraction invites picking a number that tolerates
    whichever file broke most recently, and with a corpus this small every
    failure is worth looking at directly.

    If a genuine decoder improvement changes the renders, refresh them with
    `scripts/refresh_offair_renders.py`, look at the new pictures, and this
    follows automatically.
    """
    attempts = [_run_unattended(entry) for entry in ENTRIES]
    failed = [a for a in attempts if not a.succeeded]

    detail = "\n".join(f"  {a.file}: {a.why_failed()}" for a in failed)
    assert not failed, (
        f"{len(failed)} of {len(attempts)} transmissions needed a human:\n{detail}"
    )
