"""Tests for audio module."""

import sys
import types
import pytest
import numpy as np

# Mock sounddevice before importing
sd_mock = types.ModuleType('sounddevice')
sd_mock.query_devices = lambda: []
sd_mock.query_hostapis = lambda: []
sd_mock.default = types.SimpleNamespace(device=(0, 0))
sd_mock.PortAudioError = Exception
sd_mock.InputStream = object
sd_mock.OutputStream = object
sd_mock.CallbackFlags = int
sd_mock.check_input_settings = lambda **kwargs: None
sd_mock.check_output_settings = lambda **kwargs: None
sys.modules['sounddevice'] = sd_mock


class TestAudioRingBuffer:
    """Tests for AudioRingBuffer."""

    def test_buffer_creation(self):
        from sstv_core.audio.ring_buffer import AudioRingBuffer
        buffer = AudioRingBuffer(max_samples=1000, sample_rate=48000)
        assert buffer.max_samples == 1000
        assert buffer.sample_rate == 48000
        assert len(buffer) == 0
        assert buffer.is_empty()

    def test_add_and_get(self):
        from sstv_core.audio.ring_buffer import AudioRingBuffer
        buffer = AudioRingBuffer(max_samples=1000)
        samples = np.array([0.1, 0.2, 0.3, 0.4, 0.5], dtype=np.float32)
        buffer.add(samples)
        assert len(buffer) == 5
        result = buffer.get()
        assert len(result) == 5
        np.testing.assert_array_almost_equal(result, samples)

    def test_pop(self):
        from sstv_core.audio.ring_buffer import AudioRingBuffer
        buffer = AudioRingBuffer(max_samples=1000)
        samples = np.array([0.1, 0.2, 0.3, 0.4, 0.5], dtype=np.float32)
        buffer.add(samples)
        popped = buffer.pop(3)
        assert len(popped) == 3
        np.testing.assert_array_almost_equal(popped, [0.1, 0.2, 0.3])
        assert len(buffer) == 2

    def test_overflow_discards_oldest(self):
        from sstv_core.audio.ring_buffer import AudioRingBuffer
        buffer = AudioRingBuffer(max_samples=5)
        buffer.add(np.array([1, 2, 3, 4, 5]))
        buffer.add(np.array([6, 7]))
        assert len(buffer) == 5
        result = buffer.get()
        np.testing.assert_array_almost_equal(result, [3, 4, 5, 6, 7])

    def test_duration_calculation(self):
        from sstv_core.audio.ring_buffer import AudioRingBuffer
        buffer = AudioRingBuffer(max_samples=48000, sample_rate=48000)
        buffer.add(np.zeros(24000))
        assert abs(buffer.get_duration_sec() - 0.5) < 0.001


class TestPTTController:
    """Tests for PTTController."""

    def test_ptt_none_method(self):
        from sstv_core.audio.ptt_controller import PTTController, PTTMethod
        ptt = PTTController(method=PTTMethod.NONE)
        assert ptt.method == PTTMethod.NONE
        assert not ptt.is_keyed

    def test_vox_preamble_is_audible(self):
        """VOX triggers on audio energy; a silent preamble activates
        nothing. This test used to assert the preamble was all zeros --
        enshrining exactly that defect."""
        from sstv_core.audio.ptt_controller import PTTController, PTTMethod
        ptt = PTTController(method=PTTMethod.VOX, vox_preamble_ms=500, sample_rate=48000)
        preamble = ptt.generate_vox_preamble()
        expected_samples = 48000 * 500 // 1000
        assert len(preamble) == expected_samples
        rms = float(np.sqrt(np.mean(preamble.astype(np.float64) ** 2)))
        assert rms > 0.1, "preamble must carry energy to trip VOX"

    def test_invalid_serial_signal(self):
        from sstv_core.audio.ptt_controller import PTTController, PTTMethod
        with pytest.raises(ValueError):
            PTTController(method=PTTMethod.SERIAL, serial_signal="INVALID")

    def test_timing_properties(self):
        from sstv_core.audio.ptt_controller import PTTController, PTTMethod
        ptt = PTTController(pre_delay_ms=600, post_delay_ms=300)
        assert ptt.pre_delay_ms == 600
        assert ptt.post_delay_ms == 300
