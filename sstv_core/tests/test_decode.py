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
        # Duration is measured in whole 2ms blocks, so a 9ms pulse reads as
        # 8-10ms depending on where its edges fall relative to block boundaries.
        assert 7.0 <= pulses[0].duration_ms <= 11.0, "9ms pulse should measure ~9ms"
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


class TestDemodulator:
    """The FM demodulator that recovers brightness from audio frequency."""

    def test_recovers_frequency_accurately(self):
        """Frequency error must be negligible across the video band."""
        import numpy as np

        from sstv_core.decode.demodulator import instantaneous_frequency

        for rate in (11025, 22050, 48000):
            for expected_hz in (1500.0, 1900.0, 2300.0):
                t = np.arange(int(rate * 0.05)) / rate
                signal = np.sin(2 * np.pi * expected_hz * t).astype(np.float32)

                freqs = instantaneous_frequency(signal, rate)
                # Ignore edges, where the Hilbert transform has transients.
                interior = freqs[len(freqs) // 5:-len(freqs) // 5]

                error = abs(float(np.median(interior)) - expected_hz)
                assert error < 1.0, f"{rate}Hz/{expected_hz}Hz: off by {error:.2f} Hz"

    def test_resolves_a_full_grey_ramp(self):
        """A black-to-white sweep must produce a full range of grey levels.

        Regression test for zero-crossing demodulation, which quantised the
        1500-2300 Hz video band to whole-sample periods and could represent
        only 1-3 distinct frequencies depending on sample rate. Decoded images
        came out flat grey.
        """
        import numpy as np

        from sstv_core.decode.demodulator import demodulate_channel

        for rate in (11025, 22050, 48000):
            duration = 0.1
            t = np.arange(int(rate * duration)) / rate
            sweep = 1500.0 + (2300.0 - 1500.0) * t / duration
            signal = np.sin(2 * np.pi * np.cumsum(sweep) / rate).astype(np.float32)

            pixels = demodulate_channel(signal, rate, 320, 1500.0, 2300.0)

            assert len(np.unique(pixels)) > 200, (
                f"{rate}Hz: only {len(np.unique(pixels))} grey levels"
            )
            # The ramp must actually run dark-to-light. The first and last few
            # pixels carry Hilbert edge transients, so judge just inside them.
            assert pixels[5] < 70, f"{rate}Hz: sweep should start dark"
            assert pixels[-5] > 185, f"{rate}Hz: sweep should end light"
            assert int(pixels[-5]) - int(pixels[5]) > 150, "ramp should span the range"

    def test_silence_does_not_produce_noise(self):
        """A silent channel must not emit invented brightness."""
        import numpy as np

        from sstv_core.decode.demodulator import demodulate_channel

        silence = np.zeros(2205, dtype=np.float32)
        pixels = demodulate_channel(silence, 22050, 320, 1500.0, 2300.0)

        assert len(np.unique(pixels)) == 1


class TestModeTimings:
    """Line timings must match the published SSTV specifications.

    Every channel offset in a decoder derives from these durations, so an
    error here misaligns colour and geometry on every line. Robot 36 shipped
    with an implied 194ms line against a spec of 150ms -- chroma duration was
    a copy of the luminance duration rather than the subsampled half -- and
    nothing caught it because no test compared a config against the standard.
    """

    SPEC_LINE_MS = {
        "ScottieS1": 428.22,
        "MartinM1": 446.446,
        "Robot36": 150.0,
    }

    def test_line_durations_match_spec(self):
        from sstv_core.decode.martin_decoder import MartinM1Config
        from sstv_core.decode.robot_decoder import Robot36Config
        from sstv_core.decode.scottie_decoder import ScottieS1Config

        rate = 48000
        configs = {
            "ScottieS1": ScottieS1Config(sample_rate=rate),
            "MartinM1": MartinM1Config(sample_rate=rate),
            "Robot36": Robot36Config(sample_rate=rate),
        }

        for name, config in configs.items():
            actual_ms = config.total_line_samples * 1000.0 / rate
            expected_ms = self.SPEC_LINE_MS[name]
            error_pct = abs(actual_ms - expected_ms) / expected_ms * 100

            assert error_pct < 0.1, (
                f"{name}: line is {actual_ms:.3f}ms, spec says {expected_ms}ms "
                f"({error_pct:.2f}% off)"
            )

    def test_agrees_with_sync_detector_timing_table(self):
        """The decoders and SyncPulseDetector.MODE_TIMINGS must not disagree.

        The timing table already held the correct Robot 36 line time while the
        decoder config implied something 29% different.
        """
        from sstv_core.decode.martin_decoder import MartinM1Config
        from sstv_core.decode.robot_decoder import Robot36Config
        from sstv_core.decode.scottie_decoder import ScottieS1Config
        from sstv_core.decode.sync_detector import SyncPulseDetector

        rate = 48000
        configs = {
            "ScottieS1": ScottieS1Config(sample_rate=rate),
            "MartinM1": MartinM1Config(sample_rate=rate),
            "Robot36": Robot36Config(sample_rate=rate),
        }

        for name, config in configs.items():
            table_ms, _ = SyncPulseDetector.MODE_TIMINGS[name]
            actual_ms = config.total_line_samples * 1000.0 / rate
            assert abs(actual_ms - table_ms) / table_ms < 0.001, (
                f"{name}: decoder says {actual_ms:.3f}ms, "
                f"MODE_TIMINGS says {table_ms}ms"
            )

    def test_channel_windows_fit_inside_the_line(self):
        """No colour channel may extend past the end of its scanline.

        The decoders silently substitute zeros when a channel window overruns,
        which turns a timing error into a plausible-looking green or dark
        image rather than an error.
        """
        from sstv_core.decode.robot_decoder import Robot36Config
        from sstv_core.decode.scottie_decoder import ScottieS1Config

        rate = 48000

        s = ScottieS1Config(sample_rate=rate)
        scottie_sep = int(rate * s.separator_duration_ms / 1000)
        scottie_used = 3 * scottie_sep + 3 * s.samples_per_color_line
        assert scottie_used <= s.total_line_samples

        r = Robot36Config(sample_rate=rate)
        robot_used = (
            r.samples_per_sync
            + 3 * r.samples_per_porch
            + r.samples_per_y_scan
            + r.samples_per_chroma_scan
        )
        assert robot_used <= r.total_line_samples


class TestChannelWindow:
    """Slicing a channel out of a scanline that may be slightly short."""

    def test_takes_what_is_present_when_the_line_is_short(self):
        """A line a few samples short must still yield its channel.

        Regression test for whole-channel loss. Decoders guarded windows with
        `if end <= len(line)` and substituted zeros otherwise. Line lengths
        come from measured sync spacing and are routinely a few samples under
        nominal, so a three-sample shortfall zeroed an entire colour channel.
        """
        import numpy as np

        from sstv_core.decode.demodulator import channel_window

        line = np.ones(997, dtype=np.float32)

        window = channel_window(line, 500, 1000)

        assert len(window) == 497, "should return the 497 samples that exist"
        assert np.all(window == 1.0)

    def test_returns_the_full_window_when_present(self):
        import numpy as np

        from sstv_core.decode.demodulator import channel_window

        line = np.arange(1000, dtype=np.float32)
        window = channel_window(line, 100, 200)

        assert len(window) == 100
        assert window[0] == 100.0

    def test_gives_up_when_too_little_is_present(self):
        """A genuinely truncated line must not invent a channel."""
        import numpy as np

        from sstv_core.decode.demodulator import channel_window

        line = np.ones(510, dtype=np.float32)

        # Only 10 of 500 requested samples exist.
        assert len(channel_window(line, 500, 1000)) == 0

    def test_missing_channel_demodulates_to_neutral_not_black(self):
        """An absent channel must read as mid-scale.

        Zero is fully saturated for a colour-difference channel, so returning
        black would paint a vivid cast across the picture. Mid-scale reads as
        "no information", which is the truth.
        """
        import numpy as np

        from sstv_core.decode.demodulator import demodulate_channel

        pixels = demodulate_channel(
            np.zeros(0, dtype=np.float32), 22050, 320, 1500.0, 2300.0
        )

        assert len(pixels) == 320
        assert np.all(pixels == 128)
