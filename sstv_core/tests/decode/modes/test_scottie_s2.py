"""Scottie S2 decode: timing, VIS, and round trip.

Scottie S2 was the dominant mode on 20m in the 2026-08-16 capture -- 18 of 24
located transmissions -- and had no decoder at all (#96). VIS detection,
sync timing, transmit duration and the mode enum all already knew about S2;
only the decode/encode configs were missing.

S2 shares S1's line structure exactly (sep + green + sep + blue + sync + red)
and differs only in the colour scan duration, so it reuses `ScottieS1Decoder`
rather than introducing a parallel class. These tests pin the properties that
reuse could silently get wrong: the scan duration, the resulting line time,
and the VIS code -- which is the one value that is not derived from config.

As in `test_roundtrip.py`, published figures are duplicated here on purpose. A
test that imports the constant it is checking cannot catch that constant being
wrong, which is how Robot 36 shipped a 29% timing error agreeing with itself.
"""

from __future__ import annotations

import numpy as np

from sstv_core.decode.scottie_decoder import (
    ScottieS1Config,
    ScottieS1Decoder,
    ScottieS2Config,
)
from sstv_core.decode.sync_detector import SyncPulseDetector
from sstv_core.encode.scottie_encoder import ScottieS2Encoder, ScottieS2EncoderConfig
from sstv_core.encode.vis_generator import SSTVMode

# Published Scottie S2 figures.
SPEC_COLOR_SCAN_MS = 88.064
SPEC_LINE_MS = 277.692
SPEC_VIS_CODE = 56

RATE = 48000


class TestScottieS2Timing:
    """The scan duration and the line time it produces must match the spec."""

    def test_color_scan_duration_matches_spec(self):
        assert abs(ScottieS2Config().color_scan_duration_ms - SPEC_COLOR_SCAN_MS) < 0.01

    def test_total_line_time_matches_spec(self):
        """Line time is derived from the parts, so this catches a bad part.

        3 separators + 3 colour scans + 1 sync must sum to the published
        277.692 ms. If any component is wrong the sum drifts and every
        decoded image slants.
        """
        cfg = ScottieS2Config(sample_rate=RATE)
        line_ms = 1000.0 * cfg.total_line_samples / RATE
        assert abs(line_ms - SPEC_LINE_MS) < 0.1, (
            f"line time {line_ms:.3f}ms, spec is {SPEC_LINE_MS}ms"
        )

    def test_s2_is_faster_than_s1(self):
        """Guards against S2 being a copy-paste of S1 that was never edited."""
        s1 = ScottieS1Config(sample_rate=RATE)
        s2 = ScottieS2Config(sample_rate=RATE)
        assert s2.total_line_samples < s1.total_line_samples

    def test_geometry_matches_s1(self):
        """S2 differs from S1 in timing only, not in image size."""
        assert ScottieS2Config().width == ScottieS1Config().width
        assert ScottieS2Config().height == ScottieS1Config().height

    def test_encoder_and_decoder_configs_agree(self):
        """Encode and decode must derive the same line length.

        The two configs are separate dataclasses; nothing but a test stops
        them drifting apart, and a drift here tears every decoded image.
        """
        enc = ScottieS2EncoderConfig(sample_rate=RATE)
        dec = ScottieS2Config(sample_rate=RATE)
        assert enc.samples_per_color_line == dec.samples_per_color_line
        assert enc.samples_per_sync == dec.samples_per_sync


class TestScottieS2VIS:
    """The VIS code is the one value not derived from config."""

    def test_encoder_emits_s2_vis_code(self):
        """S1's encoder hardcoded SSTVMode.SCOTTIE_S1; S2 must not inherit it.

        A wrong VIS code means a conforming receiver decodes our S2
        transmission with S1 geometry and gets a slanted, garbage picture.
        """
        assert SSTVMode.SCOTTIE_S2.value == SPEC_VIS_CODE
        assert ScottieS2Encoder().vis_mode is SSTVMode.SCOTTIE_S2

    def test_s1_encoder_still_emits_s1_vis_code(self):
        """Parameterising the VIS code must not have changed S1's."""
        from sstv_core.encode.scottie_encoder import ScottieS1Encoder

        assert ScottieS1Encoder().vis_mode is SSTVMode.SCOTTIE_S1


class TestScottieS2RoundTrip:
    """Encode a known image, decode it, compare."""

    @staticmethod
    def _pattern(width: int, height: int) -> np.ndarray:
        x = np.linspace(0, 255, width)
        y = np.linspace(0, 255, height)
        img = np.zeros((height, width, 3), dtype=np.uint8)
        img[:, :, 0] = np.tile(x, (height, 1)).astype(np.uint8)
        img[:, :, 1] = np.tile(y[:, None], (1, width)).astype(np.uint8)
        img[:, :, 2] = ((x[None, :] + y[:, None]) / 2).astype(np.uint8)
        return img

    def test_transmission_duration_matches_spec(self):
        """~71 seconds, the figure the transmit route already advertises."""
        enc = ScottieS2Encoder(ScottieS2EncoderConfig(sample_rate=RATE))
        img = self._pattern(enc.config.width, enc.config.height)
        audio = enc.encode_image(img, include_vis=False)
        duration = len(audio) / RATE
        expected = SPEC_LINE_MS * ScottieS2Config().height / 1000.0
        assert abs(duration - expected) < 0.5, (
            f"encoded {duration:.2f}s, spec implies {expected:.2f}s"
        )

    def test_sync_spacing_matches_spec(self):
        enc = ScottieS2Encoder(ScottieS2EncoderConfig(sample_rate=RATE))
        img = self._pattern(enc.config.width, enc.config.height)
        audio = enc.encode_image(img, include_vis=True)

        detector = SyncPulseDetector(sample_rate=RATE)
        detector.detect_in_buffer(audio)
        positions = detector.get_sync_positions(line_duration_ms=SPEC_LINE_MS)
        assert len(positions) >= 100, f"only {len(positions)} line starts found"

        intervals = np.diff(np.array(positions, dtype=np.float64))
        median_ms = float(np.median(intervals)) * 1000.0 / RATE
        assert abs(median_ms - SPEC_LINE_MS) < 5.0, (
            f"line spacing {median_ms:.2f}ms, spec is {SPEC_LINE_MS}ms"
        )

    def test_gradient_survives_round_trip(self):
        """The S1 decoder, given an S2 config, must reproduce the image."""
        enc = ScottieS2Encoder(ScottieS2EncoderConfig(sample_rate=RATE))
        width, height = enc.config.width, enc.config.height
        img = self._pattern(width, height)
        audio = enc.encode_image(img, include_vis=True)

        cfg = ScottieS2Config(sample_rate=RATE)
        detector = SyncPulseDetector(sample_rate=RATE)
        detector.detect_in_buffer(audio)
        line_ms = 1000.0 * cfg.total_line_samples / RATE
        positions = detector.get_sync_positions(line_duration_ms=line_ms)
        assert positions, "no sync pulses in clean generated audio"

        decoder = ScottieS1Decoder(cfg)
        for _ in decoder.decode_stream(iter([audio]), positions):
            pass
        decoded = decoder.get_image()
        assert decoded is not None

        o = img[10:-10, 10:-10].astype(np.float64)
        d = decoded[10:-10, 10:-10].astype(np.float64)
        for ch, name in enumerate("RGB"):
            corr = float(np.corrcoef(o[:, :, ch].ravel(), d[:, :, ch].ravel())[0, 1])
            assert corr >= 0.95, f"{name} channel corr {corr:.3f} < 0.95"

    def test_decoding_s2_with_s1_config_fails(self):
        """The negative control: geometry must actually matter.

        If an S2 transmission decoded acceptably with S1 timing, these tests
        would prove nothing about the config being used.
        """
        enc = ScottieS2Encoder(ScottieS2EncoderConfig(sample_rate=RATE))
        img = self._pattern(enc.config.width, enc.config.height)
        audio = enc.encode_image(img, include_vis=True)

        wrong = ScottieS1Config(sample_rate=RATE)
        detector = SyncPulseDetector(sample_rate=RATE)
        detector.detect_in_buffer(audio)
        positions = detector.get_sync_positions(
            line_duration_ms=1000.0 * wrong.total_line_samples / RATE
        )

        decoder = ScottieS1Decoder(wrong)
        for _ in decoder.decode_stream(iter([audio]), positions):
            pass
        decoded = decoder.get_image()
        assert decoded is not None

        o = img[10:-10, 10:-10].astype(np.float64)
        d = decoded[10:-10, 10:-10].astype(np.float64)
        corrs = [
            float(np.corrcoef(o[:, :, ch].ravel(), d[:, :, ch].ravel())[0, 1])
            for ch in range(3)
        ]
        assert min(corrs) < 0.9, (
            f"S2 audio decoded at {min(corrs):.3f} with S1 timing -- the "
            "round-trip test is not actually exercising S2 geometry"
        )
