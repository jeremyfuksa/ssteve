"""
Unit tests for device endpoints.

Tests /devices/audio and /devices/serial endpoints.
"""

import sys
import types

import pytest
from fastapi.testclient import TestClient

from sstv_core.api.main import _ensure_database_initialized, app
from sstv_core.api.routes import devices as devices_route

@pytest.fixture(scope="module")
def client():
    _ensure_database_initialized()
    with TestClient(app) as cli:
        yield cli


@pytest.fixture(autouse=True)
def stub_device_enumeration(monkeypatch):
    class DummyAudioDevice:
        def __init__(self, device_id: str, name: str, is_default: bool = True):
            self.id = device_id
            self.name = name
            self.hostapi = "Dummy"
            self.channels = 2
            self.sample_rates = [48000, 44100]
            self.is_input = True
            self.is_output = True
            self.is_default = is_default

    class DummyManager:
        def list_all_devices(self):
            return [
                DummyAudioDevice("dev0", "Built-in Audio", is_default=True),
                DummyAudioDevice("dev1", "USB Audio", is_default=False),
            ]

    dummy_module = types.ModuleType("sstv_core.audio.device_manager")
    dummy_module.AudioDeviceManager = DummyManager
    dummy_module.AudioDeviceError = Exception
    monkeypatch.setitem(sys.modules, "sstv_core.audio.device_manager", dummy_module)

    class DummyPort:
        def __init__(self, device, description, manufacturer):
            self.device = device
            self.description = description
            self.manufacturer = manufacturer

    class DummyListPorts:
        @staticmethod
        def comports():
            return [
                DummyPort("/dev/ttyUSB0", "USB Serial Device", "FTDI"),
                DummyPort("COM3", "Arduino Uno", "Arduino"),
            ]

    monkeypatch.setattr(devices_route, "list_ports", DummyListPorts)
    yield


class TestListAudioDevices:
    """Test GET /devices/audio endpoint."""

    def test_list_audio_devices(self, client):
        """Should return list of audio devices."""
        response = client.get("/api/v1/devices/audio")

        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list)
        assert len(data) > 0

        # Check first device structure
        device = data[0]
        assert "device_id" in device
        assert "name" in device
        assert "channels" in device
        assert "sample_rate" in device
        assert "is_default" in device

    def test_audio_device_has_default(self, client):
        """At least one device should be marked as default."""
        response = client.get("/api/v1/devices/audio")
        data = response.json()

        defaults = [d for d in data if d["is_default"]]
        assert len(defaults) >= 1


class TestListSerialPorts:
    """Test GET /devices/serial endpoint."""

    def test_list_serial_ports(self, client):
        """Should return list of serial ports."""
        response = client.get("/api/v1/devices/serial")

        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list)

        # If ports exist, check structure
        if len(data) > 0:
            port = data[0]
            assert "port" in port
            assert "description" in port
            assert "manufacturer" in port

    def test_serial_port_format(self, client):
        """Serial port names should be valid."""
        response = client.get("/api/v1/devices/serial")
        data = response.json()

        for port in data:
            port_name = port["port"]
            # Should be Linux /dev/tty* or Windows COM*
            assert (
                port_name.startswith("/dev/") or
                port_name.startswith("COM")
            )
