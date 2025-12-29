"""
Unit tests for configuration endpoints.

Tests GET /config, POST /config, and PATCH /config endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from sstv_core.api.main import app
from sstv_core.api.models import Configuration


client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_config():
    """Reset config to defaults before each test."""
    from sstv_core.api.routes import config
    config._config = Configuration()
    yield
    config._config = Configuration()


class TestGetConfig:
    """Test GET /config endpoint."""

    def test_get_default_config(self):
        """Should return default configuration."""
        response = client.get("/api/v1/config")

        assert response.status_code == 200
        data = response.json()

        # Check key fields exist
        assert "ptt_method" in data
        assert "default_transmit_mode" in data
        assert "image_library_path" in data
        assert "operating_mode" in data
        assert "auto_detect_mode" in data

        # Check defaults
        assert data["ptt_method"] == "none"
        assert data["ptt_pre_delay_ms"] == 500
        assert data["ptt_post_delay_ms"] == 200
        assert data["auto_detect_mode"] is True


class TestUpdateConfig:
    """Test POST /config endpoint."""

    def test_update_entire_config(self):
        """Should replace entire configuration."""
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
        assert data["default_transmit_mode"] == "ScottieS1"
        assert data["operating_mode"] == "night_vision"

    def test_update_invalid_config_rejected(self):
        """Should reject invalid configuration."""
        # Serial PTT without port
        invalid_config = {
            "ptt_method": "serial_rts",
            "ptt_serial_port": None,  # Missing!
        }

        response = client.post("/api/v1/config", json=invalid_config)
        assert response.status_code == 422


class TestPatchConfig:
    """Test PATCH /config endpoint."""

    def test_patch_single_field(self):
        """Should update single field."""
        response = client.patch(
            "/api/v1/config",
            json={"operating_mode": "sunlight"},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["operating_mode"] == "sunlight"

    def test_patch_multiple_fields(self):
        """Should update multiple fields."""
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

    def test_patch_ptt_config(self):
        """Should update PTT configuration."""
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

    def test_patch_invalid_rejected(self):
        """Should reject invalid patch."""
        # First ensure we have VOX mode (no serial port)
        client.patch("/api/v1/config", json={"ptt_method": "vox"})

        # Now try to set serial PTT without providing port
        response = client.patch(
            "/api/v1/config",
            json={"ptt_method": "serial_rts"},
        )

        # Should fail validation
        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"] == "VALIDATION_ERROR"

    def test_patch_preserves_other_fields(self):
        """PATCH should only change specified fields."""
        # Set initial value
        client.patch("/api/v1/config", json={"afc_range_hz": 150})

        # Patch different field
        client.patch("/api/v1/config", json={"operating_mode": "night_vision"})

        # Check original field preserved
        response = client.get("/api/v1/config")
        data = response.json()
        assert data["afc_range_hz"] == 150
        assert data["operating_mode"] == "night_vision"
