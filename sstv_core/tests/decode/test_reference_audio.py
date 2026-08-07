"""Decode tests against third-party reference recordings.

These files are not in the repository. They are other people's recordings
under their own licences; `scripts/fetch_reference_audio.py` downloads them
into a gitignored cache on demand:

    uv run python scripts/fetch_reference_audio.py

Every test here skips when the cache is absent, so a clean checkout, CI, and
offline work are unaffected. Run the fetcher when you want real-signal
coverage for Martin M1 and Robot 36, neither of which has a recording in
`tests/reference/audio/`.

These complement `test_roundtrip.py` rather than replacing it. Round trips
prove the pipeline is internally correct and standards-conforming against
clean signal we generated. These prove it decodes audio produced by *other
people's encoders*, which is the only check that catches an assumption
SSTeVe's encoder and decoder happen to share.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from sstv_core.decode.martin_decoder import MartinM1Config, MartinM1Decoder
from sstv_core.decode.robot_decoder import Robot36Config, Robot36Decoder
from sstv_core.decode.sync_detector import SyncPulseDetector

CACHE = Path(__file__).parent.parent / "reference" / "audio" / "_cache"

SPEC_LINE_MS = {"MartinM1": 446.446, "Robot36": 150.0}

FETCH_HINT = (
    "reference audio cache is empty; run "
    "`uv run python scripts/fetch_reference_audio.py` to enable this test"
)


def load_audio(path: Path) -> tuple[np.ndarray, int]:
    """Load any format soundfile handles, as mono float32."""
    soundfile = pytest.importorskip("soundfile", reason="soundfile not installed")
    data, rate = soundfile.read(str(path), dtype="float32", always_2d=True)
    return data.mean(axis=1), int(rate)


def require(filename: str) -> Path:
    path = CACHE / filename
    if not path.exists():
        pytest.skip(FETCH_HINT)
    return path


class TestMartinM1Reference:
    """Wikimedia 'SSTV sunset': third-party Martin M1 with a paired decode.

    The only licence-clean Martin M1 file found with ground truth. Lossy Ogg
    Vorbis at ~23 kbps, so this is a happy-path check rather than a
    signal-quality benchmark.
    """

    AUDIO = "wikimedia_martin_m1_sunset.ogg"
    EXPECTED = "wikimedia_martin_m1_sunset_expected.png"

    def test_sync_pulses_match_martin_m1_timing(self):
        """Line spacing in a third-party transmission must match the spec.

        This is the check that catches a shared encoder/decoder assumption:
        the audio came from QSSTV, so agreement here means SSTeVe agrees with
        another implementation, not merely with itself.
        """
        audio, rate = load_audio(require(self.AUDIO))

        detector = SyncPulseDetector(sample_rate=rate)
        detector.detect_in_buffer(audio)
        positions = detector.get_sync_positions(
            line_duration_ms=SPEC_LINE_MS["MartinM1"]
        )

        assert len(positions) >= 100, (
            f"found only {len(positions)} line starts in a 256-line image"
        )

        intervals = np.diff(np.array(positions, dtype=np.float64))
        median_ms = float(np.median(intervals)) * 1000.0 / rate

        assert abs(median_ms - SPEC_LINE_MS["MartinM1"]) < 10.0, (
            f"line spacing {median_ms:.2f}ms, Martin M1 spec is "
            f"{SPEC_LINE_MS['MartinM1']}ms"
        )

    def test_decodes_to_an_image_with_real_content(self):
        """The decode must produce a picture, not a flat field.

        Deliberately weak: this file is a low-bitrate lossy encode and the
        decoder still has known line-tearing artefacts, so asserting a
        similarity score against the reference PNG would encode today's
        quality as a requirement. What must hold is that real image structure
        comes out -- the failure mode this catches is the flat-grey output
        that zero-crossing demodulation produced for years.
        """
        audio, rate = load_audio(require(self.AUDIO))

        config = MartinM1Config(sample_rate=rate)
        detector = SyncPulseDetector(sample_rate=rate)
        detector.detect_in_buffer(audio)
        positions = detector.get_sync_positions(
            line_duration_ms=SPEC_LINE_MS["MartinM1"]
        )
        assert positions, "no sync pulses found"

        decoder = MartinM1Decoder(config)
        lines = sum(1 for _ in decoder.decode_stream(iter([audio]), positions))
        assert lines >= 100, f"decoded only {lines} lines"

        image = decoder.get_image()
        assert image is not None

        assert len(np.unique(image)) > 50, (
            f"only {len(np.unique(image))} distinct values -- decoder is "
            "producing a flat field, not a picture"
        )
        assert float(np.std(image)) > 20.0, (
            f"pixel standard deviation {np.std(image):.1f} is too low for a photograph"
        )

    def test_reference_image_is_the_expected_geometry(self):
        """Guards the fixture itself: a wrong download invalidates the tests."""
        cv2 = pytest.importorskip("cv2", reason="opencv not installed")
        image = cv2.imread(str(require(self.EXPECTED)))
        assert image is not None, "expected image failed to load"
        assert image.shape[:2] == (256, 320), (
            f"expected a 320x256 Martin M1 frame, got {image.shape[1]}x{image.shape[0]}"
        )


class TestRobot36Reference:
    """Wikimedia French Wikipedia logo: CC0, lossless FLAC.

    The cleanest fixture available. No published expected image, so this
    covers sync timing and decode geometry rather than pixel accuracy.
    """

    AUDIO = "wikimedia_robot36_fr_logo.flac"

    def test_sync_pulses_match_robot36_timing(self):
        """Robot 36 line spacing from a third-party encoder.

        Robot 36's timing was wrong in SSTeVe by 29% -- chroma duration was a
        copy of the luminance duration -- in both the encoder and the decoder,
        so they agreed with each other and with nothing else. Only audio from
        another implementation can catch that class of error.
        """
        audio, rate = load_audio(require(self.AUDIO))

        detector = SyncPulseDetector(sample_rate=rate)
        detector.detect_in_buffer(audio)
        positions = detector.get_sync_positions(
            line_duration_ms=SPEC_LINE_MS["Robot36"]
        )

        assert len(positions) >= 100, (
            f"found only {len(positions)} line starts in a 240-line image"
        )

        intervals = np.diff(np.array(positions, dtype=np.float64))
        median_ms = float(np.median(intervals)) * 1000.0 / rate

        assert abs(median_ms - SPEC_LINE_MS["Robot36"]) < 5.0, (
            f"line spacing {median_ms:.2f}ms, Robot 36 spec is "
            f"{SPEC_LINE_MS['Robot36']}ms"
        )

    def test_decodes_to_an_image_with_real_content(self):
        """A logo has flat regions, so this asserts structure exists at all."""
        audio, rate = load_audio(require(self.AUDIO))

        config = Robot36Config(sample_rate=rate)
        detector = SyncPulseDetector(sample_rate=rate)
        detector.detect_in_buffer(audio)
        positions = detector.get_sync_positions(
            line_duration_ms=SPEC_LINE_MS["Robot36"]
        )
        assert positions, "no sync pulses found"

        decoder = Robot36Decoder(config)
        lines = sum(1 for _ in decoder.decode_stream(iter([audio]), positions))
        assert lines >= 80, f"decoded only {lines} lines"

        image = decoder.get_image()
        assert image is not None
        assert len(np.unique(image)) > 20, (
            f"only {len(np.unique(image))} distinct values -- flat output"
        )
