import sys
import types

import pytest
from fastapi.testclient import TestClient

from sstv_core.api import main as api_main
from sstv_core.api.main import _ensure_database_initialized, app
from sstv_core.api.routes import devices as devices_route
from sstv_core.config import ConfigManager


@pytest.fixture(scope="module")
def client():
    _ensure_database_initialized()
    with TestClient(app) as cli:
        yield cli

class DummyAudioDevice:
    def __init__(self, device_id: str, name: str, is_default: bool = True):
        self.id = device_id
        self.name = name
        self.channels = 2
        self.sample_rates = [48000]
        self.is_input = True
        self.is_output = True
        self.is_default = is_default


class DummyAudioDeviceManager:
    def list_all_devices(self):
        return [
            DummyAudioDevice("dev0", "Built-in Audio", is_default=True),
            DummyAudioDevice("dev1", "USB Audio", is_default=False),
        ]


class DummyListPorts:
    @staticmethod
    def comports():
        class Port:
            def __init__(self, device, description, manufacturer):
                self.device = device
                self.description = description
                self.manufacturer = manufacturer

        return [
            Port("/dev/ttyUSB0", "USB Serial Device", "FTDI"),
            Port("COM3", "Arduino Uno", "Arduino"),
        ]


class DummyAudioError(Exception):
    pass


@pytest.fixture(autouse=True)
def stub_audio_and_serial(monkeypatch):
    dummy_module = types.ModuleType("sstv_core.audio.device_manager")
    dummy_module.AudioDeviceManager = DummyAudioDeviceManager
    dummy_module.AudioDeviceError = DummyAudioError
    monkeypatch.setitem(sys.modules, "sstv_core.audio.device_manager", dummy_module)
    monkeypatch.setattr(devices_route, "list_ports", DummyListPorts)
    yield


@pytest.fixture(autouse=True)
def reset_config(client):
    """Reset configuration before and after each test."""
    _ensure_database_initialized()
    session = api_main._db_session_factory()
    manager = ConfigManager(session)
    manager.reset_to_defaults()
    session.close()
    yield
    session = api_main._db_session_factory()
    manager = ConfigManager(session)
    manager.reset_to_defaults()
    session.close()


class TestGetConfig:
    def test_get_default_config(self, client):
        response = client.get("/api/v1/config")
        assert response.status_code == 200
        data = response.json()
        assert data["ptt_method"] == "vox"
        assert data["auto_detect_mode"] is True
        assert "image_library_path" in data


class TestUpdateConfig:
    def test_update_entire_config(self, client):
        new_config = {
            "ptt_method": "serial_rts",
            "ptt_serial_port": "/dev/ttyUSB0",
            "default_transmit_mode": "ScottieS1",
            "operating_mode": "night_vision",
        }

        response = client.post("/api/v1/config", json=new_config)
        assert response.status_code == 200
        data = response.json()
        assert data["ptt_method"] == "serial_rts"
        assert data["ptt_serial_port"] == "/dev/ttyUSB0"
        assert data["operating_mode"] == "night_vision"

    def test_update_invalid_config_rejected(self, client):
        invalid_config = {
            "ptt_method": "serial_rts",
            "ptt_serial_port": None,
        }

        response = client.post("/api/v1/config", json=invalid_config)
        assert response.status_code == 422


class TestPatchConfig:
    def test_patch_single_field(self, client):
        response = client.patch("/api/v1/config", json={"operating_mode": "sunlight"})
        assert response.status_code == 200
        assert response.json()["operating_mode"] == "sunlight"

    def test_patch_multiple_fields(self, client):
        response = client.patch(
            "/api/v1/config",
            json={
                "auto_detect_mode": False,
                "afc_range_hz": 200,
                "squelch_threshold_db": -50.0,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["auto_detect_mode"] is False
        assert data["afc_range_hz"] == 200
        assert data["squelch_threshold_db"] == -50.0

    def test_patch_ptt_config(self, client):
        response = client.patch(
            "/api/v1/config",
            json={
                "ptt_method": "serial_dtr",
                "ptt_serial_port": "/dev/ttyUSB1",
                "ptt_pre_delay_ms": 700,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ptt_method"] == "serial_dtr"
        assert data["ptt_serial_port"] == "/dev/ttyUSB1"
        assert data["ptt_pre_delay_ms"] == 700

    def test_patch_invalid_rejected(self, client):
        client.patch("/api/v1/config", json={"ptt_method": "vox"})
        response = client.patch("/api/v1/config", json={"ptt_method": "serial_rts"})
        assert response.status_code == 400
        assert response.json()["detail"]["error"] == "VALIDATION_ERROR"

    def test_patch_preserves_other_fields(self, client):
        client.patch("/api/v1/config", json={"afc_range_hz": 150})
        client.patch("/api/v1/config", json={"operating_mode": "night_vision"})
        response = client.get("/api/v1/config")
        data = response.json()
        assert data["afc_range_hz"] == 150
        assert data["operating_mode"] == "night_vision"
