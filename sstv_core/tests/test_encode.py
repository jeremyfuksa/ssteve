"""Tests for encode module."""

import sys
import types
import pytest
import numpy as np
from pathlib import Path
from PIL import Image

# Mock sounddevice
sd_mock = types.ModuleType('sounddevice')
sd_mock.query_devices = lambda: []
sd_mock.query_hostapis = lambda: []
sd_mock.default = types.SimpleNamespace(device=(0, 0))
sd_mock.PortAudioError = Exception
sd_mock.InputStream = object
sd_mock.OutputStream = object
sd_mock.CallbackFlags = int
sys.modules['sounddevice'] = sd_mock


class TestImagePreprocessor:
    """Tests for image preprocessor."""

    def test_scottie_s1_resolution(self):
        from sstv_core.encode.image_preprocessor import ImagePreprocessor, ModeResolution
        preprocessor = ImagePreprocessor.for_scottie_s1()
        assert preprocessor.target_width == 320
        assert preprocessor.target_height == 256

    def test_process_numpy_array(self):
        from sstv_core.encode.image_preprocessor import ImagePreprocessor
        preprocessor = ImagePreprocessor.for_scottie_s1()
        # Create a test image
        test_image = np.random.randint(0, 255, (200, 300, 3), dtype=np.uint8)
        result = preprocessor.process(test_image)
        assert result.image.shape == (256, 320, 3)
        assert result.was_resized

    def test_resize_modes(self):
        from sstv_core.encode.image_preprocessor import ImagePreprocessor, ModeResolution, ResizeMode
        resolution = ModeResolution.scottie_s1()

        # Test FIT mode
        preprocessor = ImagePreprocessor(resolution, resize_mode=ResizeMode.FIT)
        test_image = np.random.randint(0, 255, (100, 400, 3), dtype=np.uint8)
        result = preprocessor.process(test_image)
        assert result.final_size == (320, 256)


class TestVISGenerator:
    """Tests for VIS code generator."""

    def test_scottie_s1_vis_generation(self):
        from sstv_core.encode.vis_generator import VISGenerator, SSTVMode
        generator = VISGenerator(sample_rate=48000)
        audio = generator.generate(SSTVMode.SCOTTIE_S1)

        # Check we got audio samples
        assert len(audio) > 0
        assert audio.dtype == np.float32

        # Check duration is approximately correct
        # VIS = 300ms leader + 10ms break + 300ms leader + 30ms start + 8*30ms data + 30ms stop
        expected_duration_ms = 300 + 10 + 300 + 30 + 240 + 30  # ~910ms
        actual_duration_ms = len(audio) / 48000 * 1000
        assert abs(actual_duration_ms - expected_duration_ms) < 10

    def test_vis_bit_encoding(self):
        from sstv_core.encode.vis_generator import VISGenerator, SSTVMode
        generator = VISGenerator()
        bits = generator._encode_vis_bits(60)  # Scottie S1
        assert len(bits) == 8
        # 60 = 0b00111100, LSB first: [0,0,1,1,1,1,0,parity]
        assert bits[:7] == [0, 0, 1, 1, 1, 1, 0]


class TestScottieS1Encoder:
    """Tests for Scottie S1 encoder."""

    def test_encoder_creation(self):
        from sstv_core.encode.scottie_encoder import ScottieS1Encoder
        encoder = ScottieS1Encoder()
        assert encoder.config.width == 320
        assert encoder.config.height == 256

    def test_encode_single_scanline(self):
        from sstv_core.encode.scottie_encoder import ScottieS1Encoder
        encoder = ScottieS1Encoder()
        # Create a test RGB row
        rgb_row = np.zeros((320, 3), dtype=np.uint8)
        rgb_row[:, 0] = 128  # Red
        rgb_row[:, 1] = 64   # Green
        rgb_row[:, 2] = 192  # Blue

        audio = encoder.encode_scanline(rgb_row, 0)
        assert len(audio) > 0
        assert audio.dtype == np.float32

    def test_encode_full_image(self):
        from sstv_core.encode.scottie_encoder import ScottieS1Encoder
        encoder = ScottieS1Encoder()
        test_image = np.random.randint(0, 255, (256, 320, 3), dtype=np.uint8)
        audio = encoder.encode_image(test_image)

        # Check we got audio
        assert len(audio) > 0

        # Check progress
        progress = encoder.get_progress()
        assert progress.lines_encoded == 256
        assert progress.percent_complete == 100.0

    def test_frequency_conversion(self):
        from sstv_core.encode.scottie_encoder import ScottieS1Encoder
        encoder = ScottieS1Encoder()

        # Black should map to 1500 Hz
        freq_black = encoder._luma_to_freq(0)
        assert freq_black == 1500.0

        # White should map to 2300 Hz
        freq_white = encoder._luma_to_freq(255)
        assert freq_white == 2300.0


# (TestAudioTransmitter removed 2026-08-08 with the class itself: it was
# dead code superseded by TXManager's callback path, and would have
# silently discarded ~100s of a Scottie transmission if ever used.)


class TestTXManager:
    """Tests for TX manager."""

    def test_initial_state(self):
        from sstv_core.encode.tx_manager import TXManager, TXState
        from sstv_core.audio.stream_manager import AudioStreamManager
        from sstv_core.audio.ptt_controller import PTTController

        stream = AudioStreamManager()
        ptt = PTTController()
        tx = TXManager(stream, ptt)

        assert tx.state == TXState.IDLE
        assert not tx.is_transmitting

    def test_estimated_duration(self):
        from sstv_core.encode.tx_manager import TXManager
        from sstv_core.audio.stream_manager import AudioStreamManager
        from sstv_core.audio.ptt_controller import PTTController

        stream = AudioStreamManager()
        ptt = PTTController()
        tx = TXManager(stream, ptt)

        duration = tx.get_estimated_duration()
        # Should be roughly 110 seconds for Scottie S1
        assert 100 < duration < 120


class TestMartinM1Encoder:
    """Tests for Martin M1 encoder."""

    def test_encoder_creation(self):
        from sstv_core.encode.martin_encoder import MartinM1Encoder
        encoder = MartinM1Encoder()
        assert encoder.config.width == 320
        assert encoder.config.height == 256

    def test_encode_single_scanline(self):
        from sstv_core.encode.martin_encoder import MartinM1Encoder
        encoder = MartinM1Encoder()
        # Create a test RGB row
        rgb_row = np.zeros((320, 3), dtype=np.uint8)
        rgb_row[:, 0] = 128  # Red
        rgb_row[:, 1] = 64   # Green
        rgb_row[:, 2] = 192  # Blue

        audio = encoder.encode_scanline(rgb_row, 0)
        assert len(audio) > 0
        assert audio.dtype == np.float32

    def test_encode_full_image(self):
        from sstv_core.encode.martin_encoder import MartinM1Encoder
        encoder = MartinM1Encoder()
        test_image = np.random.randint(0, 255, (256, 320, 3), dtype=np.uint8)
        audio = encoder.encode_image(test_image)

        # Check we got audio
        assert len(audio) > 0

        # Check progress
        progress = encoder.get_progress()
        assert progress.lines_encoded == 256
        assert progress.percent_complete == 100.0

    def test_frequency_conversion(self):
        from sstv_core.encode.martin_encoder import MartinM1Encoder
        encoder = MartinM1Encoder()

        # Black should map to 1500 Hz
        freq_black = encoder._luma_to_freq(0)
        assert freq_black == 1500.0

        # White should map to 2300 Hz
        freq_white = encoder._luma_to_freq(255)
        assert freq_white == 2300.0

    def test_total_duration(self):
        from sstv_core.encode.martin_encoder import MartinM1Encoder
        encoder = MartinM1Encoder()
        duration = encoder.get_total_duration_sec()
        # Martin M1: 256 lines * ~446ms/line = ~114 seconds
        assert 110 < duration < 120


class TestRobot36Encoder:
    """Tests for Robot 36 encoder."""

    def test_encoder_creation(self):
        from sstv_core.encode.robot_encoder import Robot36Encoder
        encoder = Robot36Encoder()
        assert encoder.config.width == 320
        assert encoder.config.height == 240

    def test_rgb_to_yuv_white(self):
        from sstv_core.encode.robot_encoder import Robot36Encoder
        encoder = Robot36Encoder()
        # Create white image
        white_image = np.full((240, 320, 3), 255, dtype=np.uint8)
        y, u, v = encoder._rgb_to_yuv(white_image)
        assert y.shape == (240, 320)
        assert np.all(y >= 250)  # Y should be near 255
        assert np.all(u >= 120) and np.all(u <= 136)  # U should be near 128
        assert np.all(v >= 120) and np.all(v <= 136)  # V should be near 128

    def test_rgb_to_yuv_black(self):
        from sstv_core.encode.robot_encoder import Robot36Encoder
        encoder = Robot36Encoder()
        # Create black image
        black_image = np.zeros((240, 320, 3), dtype=np.uint8)
        y, u, v = encoder._rgb_to_yuv(black_image)
        assert np.all(y <= 5)  # Y should be near 0
        assert np.all(u >= 120) and np.all(u <= 136)  # U should be near 128
        assert np.all(v >= 120) and np.all(v <= 136)  # V should be near 128

    def test_encode_single_scanline(self):
        from sstv_core.encode.robot_encoder import Robot36Encoder
        encoder = Robot36Encoder()
        # Create test Y and chroma rows
        y_row = np.full(320, 128, dtype=np.uint8)
        chroma_row = np.full(320, 128, dtype=np.uint8)

        audio = encoder.encode_scanline(y_row, chroma_row, 0)
        assert len(audio) > 0
        assert audio.dtype == np.float32

    def test_encode_full_image(self):
        from sstv_core.encode.robot_encoder import Robot36Encoder
        encoder = Robot36Encoder()
        test_image = np.random.randint(0, 255, (240, 320, 3), dtype=np.uint8)
        audio = encoder.encode_image(test_image)

        # Check we got audio
        assert len(audio) > 0

        # Check progress
        progress = encoder.get_progress()
        assert progress.lines_encoded == 240
        assert progress.percent_complete == 100.0

    def test_total_duration(self):
        from sstv_core.encode.robot_encoder import Robot36Encoder
        encoder = Robot36Encoder()
        duration = encoder.get_total_duration_sec()
        # Robot 36: 240 lines * 150ms/line = 36 seconds. The mode is named for
        # that duration. This previously asserted 45-50s, matching a chroma
        # scan of 88ms where the standard says 44ms -- the test encoded the
        # bug, so fixing the encoder broke it.
        assert 34 < duration < 38
