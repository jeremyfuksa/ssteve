"""Decode regression suite over real off-air transmissions.

The reference corpus this repo shipped with is clean recorded audio -- MMSSTV
files, curated ARISS passes. It cannot tell you whether the decoders work on
20m at 2am, which is the only question that matters for a receiver.

These eleven snippets are cut from a 10.5-hour SpyServer capture of 14.230 MHz
(2026-08-16). They are real signals with real QSB, QRM, and adjacent-channel
splatter, so they are the corpus that catches the failures the clean files
cannot. `manifest.json` records where each came from, so any snippet can be
traced back to its second in the original capture.

The floors below are set from measured behaviour (see the docstring on
`test_decodes_enough_scanlines`), deliberately loose enough that ordinary
resampling noise does not fail the suite and tight enough that a real
regression does.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
import soundfile as sf

from sstv_core.decode.correlation_vis_detector import (
    CorrelationVISConfig,
    CorrelationVISDetector,
)
from sstv_core.decode.martin_decoder import (
    MartinM1Config,
    MartinM1Decoder,
    MartinM2Config,
)
from sstv_core.decode.scottie_decoder import (
    ScottieS1Config,
    ScottieS1Decoder,
    ScottieS2Config,
)
from sstv_core.decode.sync_detector import SyncPulseDetector

CORPUS = Path(__file__).resolve().parents[1] / "reference" / "audio" / "offair"
MANIFEST = CORPUS / "manifest.json"

#: decoder class, config class, and nominal line time per mode.
DECODERS = {
    "SCOTTIE_S1": (ScottieS1Decoder, ScottieS1Config, 428.22),
    "SCOTTIE_S2": (ScottieS1Decoder, ScottieS2Config, 277.692),
    "MARTIN_M1": (MartinM1Decoder, MartinM1Config, 446.446),
    "MARTIN_M2": (MartinM1Decoder, MartinM2Config, 226.798),
}


def _entries() -> list[dict]:
    if not MANIFEST.exists():
        return []
    return list(json.loads(MANIFEST.read_text()))


ENTRIES = _entries()
IDS = [e["file"] for e in ENTRIES]

pytestmark = pytest.mark.skipif(not ENTRIES, reason="off-air corpus not present")


def _load(entry: dict) -> tuple[np.ndarray, int]:
    audio, rate = sf.read(CORPUS / entry["file"], dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    return audio, rate


def _decode(entry: dict) -> tuple[int, np.ndarray | None]:
    audio, rate = _load(entry)
    decoder_cls, config_cls, line_ms = DECODERS[entry["mode"]]
    config = config_cls(sample_rate=rate)

    detector = SyncPulseDetector(sample_rate=rate)
    detector.detect_in_buffer(audio)
    positions = detector.get_sync_positions(line_duration_ms=line_ms)
    if not positions:
        return 0, None

    decoder = decoder_cls(config)
    lines = sum(1 for _ in decoder.decode_stream(iter([audio]), positions))
    return lines, decoder.get_image()


def test_corpus_is_present_and_described() -> None:
    """Every manifest entry names a file that exists, in a mode we decode."""
    assert ENTRIES, "manifest is empty"
    for entry in ENTRIES:
        assert (CORPUS / entry["file"]).exists(), entry["file"]
        assert entry["mode"] in DECODERS, entry["mode"]


@pytest.mark.parametrize("entry", ENTRIES, ids=IDS)
def test_vis_header_identifies_the_mode(entry: dict) -> None:
    """The VIS header reads back the mode the manifest recorded.

    Off-air VIS is the weakest link in the chain -- it is 300ms of tone at
    the very start of a transmission, before AGC has settled.
    """
    audio, rate = _load(entry)
    detector = CorrelationVISDetector(CorrelationVISConfig(sample_rate=rate))

    chunk = 4096
    detected = None
    for offset in range(0, len(audio) - chunk, chunk):
        result = detector.process_samples(audio[offset : offset + chunk])
        if result is not None and result.mode is not None:
            detected = result
            break

    assert detected is not None, f"no VIS in {entry['file']}"
    assert detected.mode.name == entry["mode"]
    # Measured 0.873-0.978. The floor sits just under the weakest, which is
    # cap1_023873s: its header decodes a full 256-line picture but reads back
    # at 0.873 here and misidentifies as ROBOT_36 if the snippet is cut a
    # couple of seconds earlier. Worth keeping precisely because it is the
    # marginal case -- see its note in manifest.json.
    assert detected.confidence > 0.85


@pytest.mark.parametrize("entry", ENTRIES, ids=IDS)
def test_decodes_enough_scanlines(entry: dict) -> None:
    """Each transmission yields most of a frame.

    Measured 168-243 lines of a 256-line frame; the shortfall is real signal
    loss, not a decoder fault -- these are HF signals that fade mid-picture.
    150 sits below every measurement while still failing a decoder that
    stops early.
    """
    lines, image = _decode(entry)

    assert lines >= 150, f"{entry['file']} decoded only {lines} lines"
    assert image is not None


@pytest.mark.parametrize("entry", ENTRIES, ids=IDS)
def test_decoded_image_carries_picture_not_black(entry: dict) -> None:
    """The frame holds an actual picture.

    A decoder that runs to completion while writing nothing still returns an
    array of the right shape, and line count alone would not notice. Measured
    61-86% of pixels above black.
    """
    _, image = _decode(entry)

    assert image is not None
    lit = float((image.reshape(-1, 3).max(axis=1) > 10).mean())
    assert lit > 0.40, f"{entry['file']} is {lit:.0%} lit -- mostly blank"


def test_every_mode_in_the_capture_has_a_decoder() -> None:
    """No mode in the corpus is one we cannot decode.

    Martin M2 was in this position until 2026-08-17: two real transmissions
    in the capture that the CLI skipped with "no decoder for this mode".
    """
    missing = {e["mode"] for e in ENTRIES} - set(DECODERS)
    assert not missing, f"corpus holds undecodable modes: {sorted(missing)}"


#: Chunk sizes a live caller can plausibly deliver. 1024 is the live audio
#: path's default (`audio/stream_manager.py`); 4096 is what the CLI feeds;
#: 9600 and 24000 are what a 48 kHz card produces on 200 ms and 500 ms
#: callbacks. VIS detection must not depend on which of these it gets.
VIS_CHUNK_SIZES = [1024, 2048, 4096, 4800, 8192, 9600, 11025, 16384, 24000]


def _detect_vis(audio: np.ndarray, rate: int, chunk: int):
    """Run VIS detection feeding `audio` in fixed-size chunks."""
    detector = CorrelationVISDetector(CorrelationVISConfig(sample_rate=rate))
    for offset in range(0, len(audio), chunk):
        result = detector.process_samples(audio[offset : offset + chunk])
        if result is not None and result.mode is not None:
            return result
    return None


@pytest.mark.parametrize("chunk", VIS_CHUNK_SIZES)
@pytest.mark.parametrize("entry", ENTRIES, ids=IDS)
def test_vis_detection_does_not_depend_on_chunk_size(entry: dict, chunk: int) -> None:
    """VIS reads back the same mode however the caller buffers the audio.

    A live caller picks its own block size -- a 48 kHz card on 200 ms
    callbacks delivers 9600 samples, and nothing in the API constrains it.
    Measured 2026-08-18 before the fix: chunk 9600 and 24000 missed all
    twelve transmissions outright, because `process_samples` only evaluated
    on chunk boundaries and a large chunk stepped straight past the window
    where the header was still inside the rolling buffer.

    This is the regression gate for that defect: the detector's answer is a
    property of the audio, not of the caller's buffering.
    """
    audio, rate = _load(entry)

    detected = _detect_vis(audio, rate, chunk)

    assert detected is not None, f"no VIS in {entry['file']} at chunk={chunk}"
    assert detected.mode.name == entry["mode"], (
        f"{entry['file']} at chunk={chunk}: read {detected.mode.name}, "
        f"expected {entry['mode']}"
    )


@pytest.mark.parametrize("chunk", [1024, 4096, 9600, 16384, 24000])
@pytest.mark.parametrize("entry", ENTRIES, ids=IDS)
def test_vis_reports_the_strongest_match_not_the_first_lucky_one(
    entry: dict, chunk: int
) -> None:
    """The reported mode is the header's best match, not whichever step got lucky.

    Neighbouring VIS codes score within MIN_MODE_MARGIN of each other on a
    real off-air header, so a per-step decision reports whichever alignment
    happened to separate the top two -- and that depends on where the
    caller's chunk boundaries fall. Measured 2026-08-18 on cap1_023873s at
    chunk 16384, the correct mode never cleared both gates on the same step:
    it peaked at 0.855 while ROBOT_36 held 0.856, then won the margin two
    steps later at 0.810, below the 0.85 threshold.

    Accumulating across steps and committing to the strongest *reportable*
    match makes the answer a property of the header. Tracking the strongest
    raw correlation instead does not: a peak whose top two templates sit a
    hair apart never clears the margin, and latching it blocks every later
    step that separates them cleanly.
    """
    audio, rate = _load(entry)

    detected = _detect_vis(audio, rate, chunk)

    assert detected is not None, f"no VIS in {entry['file']} at chunk={chunk}"
    assert detected.mode.name == entry["mode"], (
        f"{entry['file']} at chunk={chunk}: read {detected.mode.name}, "
        f"expected {entry['mode']}"
    )
    assert detected.confidence >= 0.85, (
        f"{entry['file']} at chunk={chunk}: reported {detected.confidence:.3f}, "
        f"a decayed tail value rather than the header's peak"
    )


#: Decoded renders from a known-good run: main at 4203053 plus the #87 VIS
#: fixes, verified byte-identical to 4203053's own output. These are the
#: pictures a human looked at and accepted -- callsigns legible, artwork
#: recognisable -- so they are the thing a regression has to preserve.
#:
#: Refresh deliberately with `scripts/refresh_offair_renders.py` when a change
#: genuinely improves these decodes, and look at the new renders before you
#: commit them. Never refresh to make a red suite go green.
RENDERS = Path(__file__).resolve().parents[1] / "reference" / "images" / "offair_decoded"


@pytest.mark.parametrize("entry", ENTRIES, ids=IDS)
def test_decode_matches_the_accepted_render(entry: dict) -> None:
    """Each transmission decodes to the exact picture we accepted.

    Statistical floors cannot do this job. Measured on a decoder with a 9%
    Martin M1 timing error -- which visibly destroys the picture, smearing
    the subject away and banding the right edge -- adjacent-scanline
    correlation moved 0.7638 to 0.7614 and lit stayed at 65%. Uniform random
    noise scores 96% lit. Every texture statistic tried passed a decoder that
    a human could see was broken.

    Decoding a fixed file is deterministic, so the honest gate is the render
    itself: same audio in, same pixels out. That same broken decoder changed
    67-82% of pixels in every Martin file and left the two Martin M2 files
    untouched, which is exactly the blast radius of the injected bug.
    """
    reference = RENDERS / entry["file"].replace(".wav", ".png")
    assert reference.exists(), f"no accepted render for {entry['file']}"

    _, image = _decode(entry)
    assert image is not None

    expected = np.array(Image.open(reference).convert("RGB"), dtype=np.int16)
    actual = np.asarray(image, dtype=np.int16)

    assert actual.shape == expected.shape, (
        f"{entry['file']}: decoded {actual.shape}, accepted {expected.shape}"
    )

    changed = float((np.abs(actual - expected).max(axis=2) > 0).mean())
    assert changed == 0.0, (
        f"{entry['file']}: {changed:.1%} of pixels differ from the accepted "
        f"render. If this change improves the decode, look at the new picture "
        f"and refresh the renders deliberately."
    )
