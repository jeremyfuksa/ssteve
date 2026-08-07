"""Tests for decode module."""

import pytest
import numpy as np


class TestGoertzelFilter:
    """Tests for Goertzel filter."""

    def test_detects_target_frequency(self):
        from sstv_core.decode.vis_detector import GoertzelFilter
        sample_rate = 48000
        target_freq = 1200.0
        block_size = 1440  # 30ms at 48kHz

        # Generate a pure 1200 Hz tone
        t = np.arange(block_size) / sample_rate
        tone = np.sin(2 * np.pi * target_freq * t)

        filt = GoertzelFilter(target_freq, sample_rate, block_size)
        mag = filt.magnitude(tone)

        # Should have high magnitude for matching frequency
        assert mag > 0.5

    def test_rejects_other_frequency(self):
        from sstv_core.decode.vis_detector import GoertzelFilter
        sample_rate = 48000
        target_freq = 1200.0
        block_size = 1440

        # Generate a 1900 Hz tone (leader frequency)
        t = np.arange(block_size) / sample_rate
        tone = np.sin(2 * np.pi * 1900 * t)

        filt = GoertzelFilter(target_freq, sample_rate, block_size)
        mag = filt.magnitude(tone)

        # Should have low magnitude for non-matching frequency
        assert mag < 0.3


class TestVISDetector:
    """Tests for VIS code detector."""

    def test_vis_detector_creation(self):
        from sstv_core.decode.vis_detector import VISDetector
        detector = VISDetector(sample_rate=48000)
        assert detector.sample_rate == 48000

    def test_vis_detector_reset(self):
        from sstv_core.decode.vis_detector import VISDetector
        detector = VISDetector()
        detector.reset()
        # Should not raise


class TestSSTVMode:
    """Tests for SSTV mode enum."""

    def test_scottie_s1_vis_code(self):
        from sstv_core.decode.vis_detector import SSTVMode
        assert SSTVMode.SCOTTIE_S1.value == 60

    def test_from_vis_code(self):
        from sstv_core.decode.vis_detector import SSTVMode
        mode = SSTVMode.from_vis_code(60)
        assert mode == SSTVMode.SCOTTIE_S1

    def test_unknown_vis_code(self):
        from sstv_core.decode.vis_detector import SSTVMode
        mode = SSTVMode.from_vis_code(999)
        assert mode is None


class TestSyncPulseDetector:
    """Tests for sync pulse detector."""

    def test_detector_creation(self):
        from sstv_core.decode.sync_detector import SyncPulseDetector
        detector = SyncPulseDetector(sample_rate=48000)
        assert detector.sample_rate == 48000

    def test_mode_timing_estimate_requires_pulses(self):
        from sstv_core.decode.sync_detector import SyncPulseDetector
        detector = SyncPulseDetector()
        result = detector.estimate_mode_from_timing()
        assert result is None  # No pulses detected

    def test_detects_a_synthetic_sync_pulse(self):
        """A 9ms 1200 Hz burst must be detected.

        Regression test for a threshold that no signal could ever cross:
        DETECTION_THRESHOLD was 0.6 while GoertzelFilter.magnitude() divides
        by len(samples), capping a pure full-amplitude 1200 Hz tone at ~0.45.
        Every live decode failed with "No scanline sync received", and the
        suite passed because nothing asserted a pulse was ever found.
        """
        import numpy as np

        from sstv_core.decode.sync_detector import SyncPulseDetector

        rate = 22050
        detector = SyncPulseDetector(sample_rate=rate)

        def tone(freq: float, ms: float) -> np.ndarray:
            t = np.arange(int(rate * ms / 1000)) / rate
            return np.sin(2 * np.pi * freq * t).astype(np.float32)

        # 1900 Hz padding either side of a 9ms Scottie sync pulse.
        audio = np.concatenate([tone(1900, 40), tone(1200, 9), tone(1900, 40)])

        pulses = detector.detect_in_buffer(audio)

        assert len(pulses) == 1, f"expected exactly one sync pulse, got {len(pulses)}"
        assert 8.0 <= pulses[0].duration_ms <= 10.0, "9ms pulse should measure ~9ms"
        # Position lands at the start of the pulse: 40ms of 1900 Hz padding.
        assert abs(pulses[0].position_samples - int(rate * 0.040)) < rate * 0.002

    def test_sync_detection_is_level_independent(self):
        """The same pulse must be found at any input level.

        SSTeVe takes audio from USB interfaces, virtual cables, line-out, and
        SDR demodulation, all at wildly different levels. Detection compares
        1200 Hz content against the block's own energy so amplitude cancels.
        """
        import numpy as np

        from sstv_core.decode.sync_detector import SyncPulseDetector

        rate = 22050

        def build(amplitude: float) -> np.ndarray:
            def tone(freq: float, ms: float) -> np.ndarray:
                t = np.arange(int(rate * ms / 1000)) / rate
                return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)

            return np.concatenate([tone(1900, 40), tone(1200, 9), tone(1900, 40)])

        for amplitude in (0.05, 0.5, 0.95):
            detector = SyncPulseDetector(sample_rate=rate)
            pulses = detector.detect_in_buffer(build(amplitude))
            assert len(pulses) == 1, f"amplitude {amplitude}: got {len(pulses)} pulses"

    def test_picture_tones_are_not_mistaken_for_sync(self):
        """Loud 1500-2300 Hz video content must not read as sync.

        A bright image is a loud tone too; detection has to be about spectral
        shape, not loudness.
        """
        import numpy as np

        from sstv_core.decode.sync_detector import SyncPulseDetector

        rate = 22050
        detector = SyncPulseDetector(sample_rate=rate)

        def tone(freq: float, ms: float) -> np.ndarray:
            t = np.arange(int(rate * ms / 1000)) / rate
            return np.sin(2 * np.pi * freq * t).astype(np.float32)

        # Black, mid-grey, and white video tones at full amplitude.
        audio = np.concatenate([tone(1500, 30), tone(1900, 30), tone(2300, 30)])

        assert detector.detect_in_buffer(audio) == []


class TestScottieS1Decoder:
    """Tests for Scottie S1 decoder."""

    def test_decoder_config_defaults(self):
        from sstv_core.decode.scottie_decoder import ScottieS1Config
        config = ScottieS1Config()
        assert config.width == 320
        assert config.height == 256
        assert config.sync_duration_ms == 9.0

    def test_decoder_creation(self):
        from sstv_core.decode.scottie_decoder import ScottieS1Decoder
        decoder = ScottieS1Decoder()
        assert decoder.width == 320
        assert decoder.height == 256

    def test_decoder_reset(self):
        from sstv_core.decode.scottie_decoder import ScottieS1Decoder
        decoder = ScottieS1Decoder()
        decoder.reset()
        progress = decoder.get_progress()
        assert progress.lines_decoded == 0

    def test_scanline_to_rgb(self):
        from sstv_core.decode.scottie_decoder import ScanlineData
        import numpy as np
        scanline = ScanlineData(
            line_number=0,
            green=np.full(320, 100, dtype=np.uint8),
            blue=np.full(320, 150, dtype=np.uint8),
            red=np.full(320, 200, dtype=np.uint8),
        )
        rgb = scanline.to_rgb_row()
        assert rgb.shape == (320, 3)
        assert rgb[0, 0] == 200  # Red
        assert rgb[0, 1] == 100  # Green
        assert rgb[0, 2] == 150  # Blue


class TestMartinM1Decoder:
    """Tests for Martin M1 decoder."""

    def test_decoder_config_defaults(self):
        from sstv_core.decode.martin_decoder import MartinM1Config
        config = MartinM1Config()
        assert config.width == 320
        assert config.height == 256
        assert config.sync_duration_ms == 4.862

    def test_decoder_creation(self):
        from sstv_core.decode.martin_decoder import MartinM1Decoder
        decoder = MartinM1Decoder()
        assert decoder.width == 320
        assert decoder.height == 256

    def test_decoder_reset(self):
        from sstv_core.decode.martin_decoder import MartinM1Decoder
        decoder = MartinM1Decoder()
        decoder.reset()
        progress = decoder.get_progress()
        assert progress.lines_decoded == 0

    def test_scanline_to_rgb(self):
        from sstv_core.decode.martin_decoder import ScanlineData
        import numpy as np
        scanline = ScanlineData(
            line_number=0,
            green=np.full(320, 100, dtype=np.uint8),
            blue=np.full(320, 150, dtype=np.uint8),
            red=np.full(320, 200, dtype=np.uint8),
        )
        rgb = scanline.to_rgb_row()
        assert rgb.shape == (320, 3)
        assert rgb[0, 0] == 200  # Red
        assert rgb[0, 1] == 100  # Green
        assert rgb[0, 2] == 150  # Blue

    def test_frequency_to_luma_conversion(self):
        from sstv_core.decode.martin_decoder import MartinM1Decoder
        decoder = MartinM1Decoder()
        # Test black (1500 Hz -> 0)
        assert decoder._freq_to_luma(1500.0) == 0
        # Test white (2300 Hz -> 255)
        assert decoder._freq_to_luma(2300.0) == 255
        # Test mid-gray (1900 Hz -> ~127)
        mid_luma = decoder._freq_to_luma(1900.0)
        assert 120 < mid_luma < 135


class TestRobot36Decoder:
    """Tests for Robot 36 decoder."""

    def test_decoder_config_defaults(self):
        from sstv_core.decode.robot_decoder import Robot36Config
        config = Robot36Config()
        assert config.width == 320
        assert config.height == 240
        assert config.sync_duration_ms == 9.0

    def test_decoder_creation(self):
        from sstv_core.decode.robot_decoder import Robot36Decoder
        decoder = Robot36Decoder()
        assert decoder.width == 320
        assert decoder.height == 240

    def test_decoder_reset(self):
        from sstv_core.decode.robot_decoder import Robot36Decoder
        decoder = Robot36Decoder()
        decoder.reset()
        progress = decoder.get_progress()
        assert progress.lines_decoded == 0

    def test_yuv_to_rgb_white(self):
        from sstv_core.decode.robot_decoder import Robot36Decoder
        import numpy as np
        decoder = Robot36Decoder()
        # White in YUV: Y=255, U=128, V=128
        y = np.full((240, 320), 255, dtype=np.uint8)
        u = np.full((240, 320), 128, dtype=np.uint8)
        v = np.full((240, 320), 128, dtype=np.uint8)
        rgb = decoder._yuv_to_rgb(y, u, v)
        assert rgb.shape == (240, 320, 3)
        # Should be approximately white
        assert np.all(rgb >= 250)

    def test_yuv_to_rgb_black(self):
        from sstv_core.decode.robot_decoder import Robot36Decoder
        import numpy as np
        decoder = Robot36Decoder()
        # Black in YUV: Y=0, U=128, V=128
        y = np.full((240, 320), 0, dtype=np.uint8)
        u = np.full((240, 320), 128, dtype=np.uint8)
        v = np.full((240, 320), 128, dtype=np.uint8)
        rgb = decoder._yuv_to_rgb(y, u, v)
        # Should be approximately black
        assert np.all(rgb <= 5)
