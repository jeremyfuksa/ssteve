"""Pytest configuration and fixtures for SSTeVe tests.

This file provides mocks for audio hardware dependencies to allow tests
to run in CI environments without actual audio devices.
"""

import sys
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Mock sounddevice BEFORE any SSTeVe modules are imported
# This prevents PortAudio library errors in CI environments
mock_sounddevice = MagicMock()
mock_sounddevice.query_devices = MagicMock(return_value=[
    {
        "name": "Mock Input Device",
        "index": 0,
        "hostapi": 0,
        "max_input_channels": 2,
        "max_output_channels": 0,
        "default_samplerate": 48000.0,
    },
    {
        "name": "Mock Output Device",
        "index": 1,
        "hostapi": 0,
        "max_input_channels": 0,
        "max_output_channels": 2,
        "default_samplerate": 48000.0,
    },
])
mock_sounddevice.default = MagicMock()
mock_sounddevice.default.device = [0, 1]
mock_sounddevice.InputStream = MagicMock()
mock_sounddevice.OutputStream = MagicMock()
sys.modules["sounddevice"] = mock_sounddevice

# Mock pyserial to prevent serial port access
mock_serial = MagicMock()
sys.modules["serial"] = mock_serial

# Mock missing/incomplete DSP modules
from unittest.mock import MagicMock as MM

# Create mock classes for missing DSP components
class MockSyncDetector:
    def __init__(self, **kwargs):
        self.sample_rate = kwargs.get("sample_rate", 48000)

    def detect_sync_pulses(self, samples):
        return []

    def estimate_mode_from_timing(self):
        return None

class MockConfig:
    """Mock config object for decoder tests."""
    def __init__(self):
        self.width = 320
        self.height = 256
        self.samples_per_sync = 1000

class MockScanlineData:
    """Mock scanline data result."""
    def __init__(self):
        self.decode_quality = 0.8
        self.lines_decoded = 0

    def to_rgb_row(self):
        return np.zeros((320, 3), dtype=np.uint8)

class MockDecoder:
    def __init__(self):
        self.config = MockConfig()
        self.height = 256
        self.width = 320
        self.lines_decoded = 0
        self._freq_to_luma = lambda f: int(f * 255 / 3000)
        self._yuv_to_rgb = lambda y, u, v: (y, u, v)

    def reset(self):
        self.lines_decoded = 0

    def decode_scanline(self, samples, line_number):
        result = MockScanlineData()
        return result

    def get_progress(self):
        result = MockScanlineData()
        result.percent_complete = 50.0
        return result

    def get_image(self):
        import numpy as np
        return np.zeros((256, 320, 3), dtype=np.uint8)

# Mock decode module classes
sync_module = MM()
sync_module.SyncDetector = MockSyncDetector
sys.modules["sstv_core.decode.sync_detector"] = sync_module

scottie_module = MM()
scottie_module.ScottieS1Config = MockConfig
scottie_module.ScottieS1Decoder = MockDecoder
sys.modules["sstv_core.decode.scottie_decoder"] = scottie_module

martin_module = MM()
martin_module.MartinM1Config = MockConfig
martin_module.MartinM1Decoder = MockDecoder
sys.modules["sstv_core.decode.martin_decoder"] = martin_module

robot_module = MM()
robot_module.Robot36Config = MockConfig
robot_module.Robot36Decoder = MockDecoder
sys.modules["sstv_core.decode.robot_decoder"] = robot_module


@pytest.fixture(autouse=True)
def mock_audio_devices():
    """Mock audio device access to prevent PortAudio errors in CI."""
    with patch("sounddevice.query_devices") as mock_query:
        # Mock audio device list
        mock_query.return_value = [
            {
                "name": "Mock Input Device",
                "index": 0,
                "hostapi": 0,
                "max_input_channels": 2,
                "max_output_channels": 0,
                "default_samplerate": 48000.0,
            },
            {
                "name": "Mock Output Device",
                "index": 1,
                "hostapi": 0,
                "max_input_channels": 0,
                "max_output_channels": 2,
                "default_samplerate": 48000.0,
            },
        ]
        yield mock_query


@pytest.fixture(autouse=True)
def mock_dsp_manager():
    """Mock DSP manager to prevent real audio I/O during tests."""
    from sstv_core.api import dsp_manager as dsp_module

    original_start_decode = dsp_module.dsp_manager.start_decode
    original_stop_decode = dsp_module.dsp_manager.stop_decode
    original_start_transmit = dsp_module.dsp_manager.start_transmit
    original_stop_transmit = dsp_module.dsp_manager.stop_transmit

    # Replace with async mocks
    dsp_module.dsp_manager.start_decode = AsyncMock()
    dsp_module.dsp_manager.stop_decode = AsyncMock()
    dsp_module.dsp_manager.start_transmit = AsyncMock()
    dsp_module.dsp_manager.stop_transmit = AsyncMock()

    yield dsp_module.dsp_manager

    # Restore original methods
    dsp_module.dsp_manager.start_decode = original_start_decode
    dsp_module.dsp_manager.stop_decode = original_stop_decode
    dsp_module.dsp_manager.start_transmit = original_start_transmit
    dsp_module.dsp_manager.stop_transmit = original_stop_transmit


@pytest.fixture
def mock_audio_stream():
    """Mock audio stream for testing audio I/O."""
    mock_stream = MagicMock()
    mock_stream.start = Mock()
    mock_stream.stop = Mock()
    mock_stream.close = Mock()
    mock_stream.active = True
    return mock_stream


@pytest.fixture
def mock_serial_port():
    """Mock serial port for PTT control testing."""
    with patch("serial.Serial") as mock_serial:
        mock_port = MagicMock()
        mock_port.is_open = True
        mock_port.rts = False
        mock_port.dtr = False
        mock_serial.return_value = mock_port
        yield mock_port
