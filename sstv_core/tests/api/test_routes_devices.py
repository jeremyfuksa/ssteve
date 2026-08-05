"""
Unit tests for device endpoints.

Tests /devices/audio and /devices/serial endpoints.
"""

import sys
import types
from unittest.mock import MagicMock

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


@pytest.fixture
def mock_config_manager():
    """Override the ConfigManager dependency with a mock."""
    mock_cm = MagicMock()
    mock_cm.to_dict.return_value = {"ptt_method": "serial_rts"}
    app.dependency_overrides[devices_route._get_config_manager] = lambda: mock_cm
    yield mock_cm
    del app.dependency_overrides[devices_route._get_config_manager]


class TestApplySettings:
    """Test POST /devices/apply_settings endpoint."""

    def test_apply_ptt_and_audio_settings(self, client, mock_config_manager):
        """Should pass explicit PTT/audio settings to config_manager.update()."""
        response = client.post(
            "/api/v1/devices/apply_settings",
            json={
                "ptt_method": "serial_rts",
                "ptt_serial_signal": "RTS",
                "ptt_pre_delay_ms": 500,
                "ptt_post_delay_ms": 200,
                "audio_input_device_id": "dev0",
                "audio_output_device_id": "dev1",
            },
        )

        assert response.status_code == 200
        mock_config_manager.update.assert_called_once_with({
            "ptt_method": "serial_rts",
            "ptt_serial_signal": "RTS",
            "ptt_pre_delay_ms": 500,
            "ptt_post_delay_ms": 200,
            "audio_input_device_id": "dev0",
            "audio_output_device_id": "dev1",
        })

    def test_profile_does_not_override_explicit_settings(
        self, client, mock_config_manager, monkeypatch
    ):
        """Profile defaults must not clobber explicitly-passed settings."""
        profile = MagicMock()
        profile.name = "Digirig Mobile"

        detector = MagicMock()
        detector.detect_hardware_device.return_value = profile
        detector.get_recommended_settings.return_value = {
            "ptt_method": "vox",  # Conflicts with explicit setting below
            "vox_preamble_ms": 750,  # Not passed explicitly - should apply
        }

        monkeypatch.setattr(devices_route, "device_detector", detector)
        monkeypatch.setattr(devices_route, "_device_detector_available", True)

        response = client.post(
            "/api/v1/devices/apply_settings",
            json={
                "profile_name": "Digirig Mobile",
                "ptt_method": "serial_rts",
            },
        )

        assert response.status_code == 200
        mock_config_manager.update.assert_called_once_with({
            "ptt_method": "serial_rts",  # Explicit setting wins
            "vox_preamble_ms": 750,  # Profile fills the gap
        })

    def test_apply_settings_response_shape(self, client, mock_config_manager):
        """Should return updated configuration and list of applied fields."""
        mock_config_manager.to_dict.return_value = {
            "ptt_method": "vox",
            "vox_preamble_ms": 500,
        }

        response = client.post(
            "/api/v1/devices/apply_settings",
            json={"ptt_method": "vox", "vox_preamble_ms": 500},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["updated_configuration"] == {
            "ptt_method": "vox",
            "vox_preamble_ms": 500,
        }
        assert sorted(data["applied_fields"]) == ["ptt_method", "vox_preamble_ms"]

    def test_apply_settings_empty_request(self, client, mock_config_manager):
        """Should reject a request with no settings as 400 NO_SETTINGS_TO_APPLY."""
        response = client.post("/api/v1/devices/apply_settings", json={})

        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"] == "NO_SETTINGS_TO_APPLY"
        mock_config_manager.update.assert_not_called()

    def test_apply_settings_validation_error(self, client, mock_config_manager):
        """Should return 400 VALIDATION_ERROR when config update rejects a value."""
        mock_config_manager.update.side_effect = ValueError("Unknown device ID: dev9")

        response = client.post(
            "/api/v1/devices/apply_settings",
            json={"audio_input_device_id": "dev9"},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"] == "VALIDATION_ERROR"
        assert "Unknown device ID" in data["detail"]["message"]


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
