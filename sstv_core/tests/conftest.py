"""Pytest configuration and fixtures for SSTeVe tests.

This file provides mocks for audio hardware dependencies to allow tests
to run in CI environments without actual audio devices.
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Isolate the app database BEFORE any SSTeVe modules are imported. The API
# initializes its DB lazily from SSTVE_DB_PATH with a ~/.ssteve/ssteve.db
# default -- until 2026-08-07 the route tests hit (and reset!) the
# developer's real database on every `pytest` run.
_TEST_DB_DIR = tempfile.mkdtemp(prefix="ssteve-test-db-")
os.environ["SSTVE_DB_PATH"] = str(Path(_TEST_DB_DIR) / "test.db")


@pytest.fixture(scope="session", autouse=True)
def _assert_db_isolated():
    """Guarantee no test run can touch ~/.ssteve."""
    configured = os.environ.get("SSTVE_DB_PATH", "")
    assert configured, "SSTVE_DB_PATH must be set for the test session"
    assert str(Path.home() / ".ssteve") not in configured
    yield


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
