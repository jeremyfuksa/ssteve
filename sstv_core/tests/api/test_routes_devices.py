"""
Unit tests for device endpoints.

Tests /devices/audio and /devices/serial endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from sstv_core.api.main import app


client = TestClient(app)


class TestListAudioDevices:
    """Test GET /devices/audio endpoint."""

    def test_list_audio_devices(self):
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

    def test_audio_device_has_default(self):
        """At least one device should be marked as default."""
        response = client.get("/api/v1/devices/audio")
        data = response.json()

        defaults = [d for d in data if d["is_default"]]
        assert len(defaults) >= 1


class TestListSerialPorts:
    """Test GET /devices/serial endpoint."""

    def test_list_serial_ports(self):
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

    def test_serial_port_format(self):
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
