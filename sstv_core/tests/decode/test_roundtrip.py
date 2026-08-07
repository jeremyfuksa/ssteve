"""Round-trip tests: encode a known image, decode it, compare.

Covers the MVP modes that have no reference recording in
`tests/reference/audio/` -- Martin M1 and Robot 36 -- where the only
alternative was verifying timing against the spec and hoping.

**A round trip alone proves very little.** If encoder and decoder share a
wrong assumption it passes while both are broken, which is exactly the state
Robot 36 was in: both sides used an 88ms chroma scan where the standard says
44ms, so they agreed with each other and with nothing else in the world. Each
test here therefore also asserts the *absolute* properties a conforming
transmission must have -- total duration and line timing against the published
figures -- so agreement between our own two halves is never sufficient.

Signal is generated clean: no noise, no fading, no clock drift. These tests
answer "is the pipeline internally correct and standards-conforming", not
"does it cope with a real signal". Real-signal quality is measured by
`scripts/decode_quality.py` against the reference corpus.
"""

from __future__ import annotations

import numpy as np
import pytest

from sstv_core.decode.martin_decoder import MartinM1Config, MartinM1Decoder
from sstv_core.decode.robot_decoder import Robot36Config, Robot36Decoder
from sstv_core.decode.scottie_decoder import ScottieS1Config, ScottieS1Decoder
from sstv_core.decode.sync_detector import SyncPulseDetector
from sstv_core.encode.martin_encoder import MartinM1Encoder, MartinM1EncoderConfig
from sstv_core.encode.robot_encoder import Robot36Encoder, Robot36EncoderConfig
from sstv_core.encode.scottie_encoder import ScottieS1Encoder, ScottieS1EncoderConfig

# Published line times. Duplicated here deliberately: a test that imports the
# value it is checking cannot catch the value being wrong.
SPEC_LINE_MS = {
    "ScottieS1": 428.22,
    "MartinM1": 446.446,
    "Robot36": 150.0,
}

RATE = 48000


def build_pattern(width: int, height: int) -> np.ndarray:
    """Build a colour test pattern with structure in both axes.

    Vertical colour bars catch channel swaps and horizontal misalignment; a
    brightness ramp down the image catches vertical geometry errors. Flat
    fields would hide both.
    """
    image = np.zeros((height, width, 3), dtype=np.uint8)
    bars = [
        (255, 255, 255), (255, 255, 0), (0, 255, 255), (0, 255, 0),
        (255, 0, 255), (255, 0, 0), (0, 0, 255), (0, 0, 0),
    ]
    bar_width = width // len(bars)
    for i, colour in enumerate(bars):
        start = i * bar_width
        end = start + bar_width if i < len(bars) - 1 else width
        image[:, start:end] = colour

    # Brightness ramp: 40% at the top rising to full at the bottom.
    ramp = np.linspace(0.4, 1.0, height, dtype=np.float32)[:, None, None]
    return np.clip(image * ramp, 0, 255).astype(np.uint8)


class TestRoundTrip:
    """Encode -> decode for each MVP mode."""

    @pytest.mark.parametrize(
        ("mode", "encoder_cls", "encoder_config_cls", "decoder_cls", "decoder_config_cls"),
        [
            ("ScottieS1", ScottieS1Encoder, ScottieS1EncoderConfig,
             ScottieS1Decoder, ScottieS1Config),
            ("MartinM1", MartinM1Encoder, MartinM1EncoderConfig,
             MartinM1Decoder, MartinM1Config),
            ("Robot36", Robot36Encoder, Robot36EncoderConfig,
             Robot36Decoder, Robot36Config),
        ],
    )
    def test_encoded_audio_matches_spec_duration(
        self, mode, encoder_cls, encoder_config_cls, decoder_cls, decoder_config_cls
    ):
        """Encoded audio must run for the duration the standard specifies.

        This is the check a bare round trip cannot make. Robot 36 encoded
        194ms lines against a 150ms spec; encoder and decoder agreed, so only
        an absolute comparison catches it.
        """
        decoder_config = decoder_config_cls(sample_rate=RATE)
        width, height = decoder_config.width, decoder_config.height

        encoder = encoder_cls(encoder_config_cls(sample_rate=RATE))
        audio = encoder.encode_image(build_pattern(width, height))

        per_line_ms = (len(audio) / RATE * 1000.0) / height
        expected = SPEC_LINE_MS[mode]

        # 3% tolerance absorbs the VIS header and any leader tone, which are
        # amortised across every line.
        assert abs(per_line_ms - expected) / expected < 0.03, (
            f"{mode}: encoded {per_line_ms:.2f}ms per line, spec says {expected}ms"
        )

    @pytest.mark.parametrize(
        ("mode", "encoder_cls", "encoder_config_cls", "decoder_cls", "decoder_config_cls"),
        [
            ("ScottieS1", ScottieS1Encoder, ScottieS1EncoderConfig,
             ScottieS1Decoder, ScottieS1Config),
            ("MartinM1", MartinM1Encoder, MartinM1EncoderConfig,
             MartinM1Decoder, MartinM1Config),
            ("Robot36", Robot36Encoder, Robot36EncoderConfig,
             Robot36Decoder, Robot36Config),
        ],
    )
    def test_sync_pulses_land_on_spec_timing(
        self, mode, encoder_cls, encoder_config_cls, decoder_cls, decoder_config_cls
    ):
        """Sync pulses in encoded audio must appear one line time apart.

        Exercises the detector against a signal whose correct answer is known
        exactly, which the reference corpus cannot do.
        """
        decoder_config = decoder_config_cls(sample_rate=RATE)
        width, height = decoder_config.width, decoder_config.height

        encoder = encoder_cls(encoder_config_cls(sample_rate=RATE))
        audio = encoder.encode_image(build_pattern(width, height))

        detector = SyncPulseDetector(sample_rate=RATE)
        detector.detect_in_buffer(audio.astype(np.float32))
        positions = detector.get_sync_positions(
            line_duration_ms=SPEC_LINE_MS[mode]
        )

        assert len(positions) >= height * 0.8, (
            f"{mode}: found {len(positions)} line starts, expected about {height}"
        )

        intervals = np.diff(np.array(positions, dtype=np.float64))
        median_ms = float(np.median(intervals)) * 1000.0 / RATE
        expected = SPEC_LINE_MS[mode]

        assert abs(median_ms - expected) / expected < 0.02, (
            f"{mode}: sync spacing {median_ms:.2f}ms, spec says {expected}ms"
        )

    @pytest.mark.parametrize(
        ("mode", "encoder_cls", "encoder_config_cls", "decoder_cls", "decoder_config_cls"),
        [
            ("ScottieS1", ScottieS1Encoder, ScottieS1EncoderConfig,
             ScottieS1Decoder, ScottieS1Config),
            ("MartinM1", MartinM1Encoder, MartinM1EncoderConfig,
             MartinM1Decoder, MartinM1Config),
        ],
    )
    def test_decodes_back_to_a_recognisable_image(
        self, mode, encoder_cls, encoder_config_cls, decoder_cls, decoder_config_cls
    ):
        """A clean encode must decode back to something close to the original.

        Robot 36 is excluded: it subsamples chroma and interpolates it back,
        so a round trip cannot reproduce the source colours exactly. Its
        geometry is covered by the two tests above.
        """
        decoder_config = decoder_config_cls(sample_rate=RATE)
        width, height = decoder_config.width, decoder_config.height
        original = build_pattern(width, height)

        encoder = encoder_cls(encoder_config_cls(sample_rate=RATE))
        audio = encoder.encode_image(original).astype(np.float32)

        detector = SyncPulseDetector(sample_rate=RATE)
        detector.detect_in_buffer(audio)
        positions = detector.get_sync_positions(line_duration_ms=SPEC_LINE_MS[mode])
        assert positions, f"{mode}: no sync pulses found in encoded audio"

        decoder = decoder_cls(decoder_config)
        lines = sum(1 for _ in decoder.decode_stream(iter([audio]), positions))
        assert lines >= height * 0.8, f"{mode}: decoded only {lines} of {height} lines"

        decoded = decoder.get_image()
        assert decoded is not None

        # Compare the middle band only: the first and last lines depend on
        # where sync detection latched, which is not what this test is about.
        band = slice(height // 4, 3 * height // 4)
        a = decoded[band].astype(np.float64)
        b = original[band].astype(np.float64)

        # Correlation rather than exact equality: demodulation is lossy and
        # the point is that structure survives, not that bytes match.
        correlation = float(
            np.corrcoef(a.ravel(), b.ravel())[0, 1]
        )
        assert correlation > 0.7, (
            f"{mode}: decoded image correlates {correlation:.3f} with the original"
        )

    def test_colour_channels_are_not_swapped(self):
        """Red must come back red.

        A channel-order error decodes to a plausible image in the wrong
        colours, which no geometry check would catch. Scottie's offsets were
        briefly wrong in exactly this way during development and the result
        looked fine until it was compared against a known input.
        """
        config = ScottieS1Config(sample_rate=RATE)
        width, height = config.width, config.height

        # Solid red, so any channel confusion is unambiguous.
        original = np.zeros((height, width, 3), dtype=np.uint8)
        original[:, :, 0] = 220

        encoder = ScottieS1Encoder(ScottieS1EncoderConfig(sample_rate=RATE))
        audio = encoder.encode_image(original).astype(np.float32)

        detector = SyncPulseDetector(sample_rate=RATE)
        detector.detect_in_buffer(audio)
        positions = detector.get_sync_positions(line_duration_ms=SPEC_LINE_MS["ScottieS1"])
        assert positions

        decoder = ScottieS1Decoder(config)
        for _ in decoder.decode_stream(iter([audio]), positions):
            pass
        decoded = decoder.get_image()
        assert decoded is not None

        band = decoded[height // 4:3 * height // 4]
        means = [float(band[:, :, c].mean()) for c in range(3)]

        assert means[0] > means[1] + 40 and means[0] > means[2] + 40, (
            f"red image decoded with channel means R={means[0]:.0f} "
            f"G={means[1]:.0f} B={means[2]:.0f}"
        )
