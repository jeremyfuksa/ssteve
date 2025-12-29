"""
Unit tests for transmit endpoints.

Tests /transmit, /transmit/status, and /transmit/cancel endpoints.
"""

import pytest
from uuid import uuid4
from fastapi.testclient import TestClient

from sstv_core.api.main import app
from sstv_core.api.session_manager import session_manager


@pytest.fixture(autouse=True)
def reset_session_manager():
    """Reset session manager before each test."""
    session_manager.reset()
    yield
    session_manager.reset()


client = TestClient(app)


class TestStartTransmit:
    """Test POST /transmit endpoint."""

    def test_start_transmit_minimal(self):
        """Should start transmit with minimal request."""
        response = client.post(
            "/api/v1/transmit",
            json={
                "image_path": "/home/admin/test.png",
                "mode": "MartinM1",
            },
        )

        assert response.status_code == 201
        data = response.json()

        assert "tx_id" in data
        assert data["state"] == "pending"
        assert "websocket_url" in data
        assert "estimated_duration_seconds" in data
        assert data["estimated_duration_seconds"] > 0

    def test_start_transmit_with_callsign(self):
        """Should start transmit with callsign overlay."""
        response = client.post(
            "/api/v1/transmit",
            json={
                "image_path": "/home/admin/test.png",
                "mode": "ScottieS1",
                "callsign": "W1AW",
            },
        )

        assert response.status_code == 201

    def test_start_transmit_vox_mode(self):
        """Should start transmit with VOX mode."""
        response = client.post(
            "/api/v1/transmit",
            json={
                "image_path": "/home/admin/test.png",
                "mode": "Robot36",
                "vox_enabled": True,
            },
        )

        assert response.status_code == 201

    def test_start_transmit_relative_path_rejected(self):
        """Should reject relative image paths."""
        response = client.post(
            "/api/v1/transmit",
            json={
                "image_path": "images/test.png",  # Relative!
                "mode": "MartinM1",
            },
        )

        assert response.status_code == 422

    def test_start_transmit_path_traversal_rejected(self):
        """Should reject path traversal."""
        response = client.post(
            "/api/v1/transmit",
            json={
                "image_path": "/home/../etc/passwd",
                "mode": "MartinM1",
            },
        )

        assert response.status_code == 422

    def test_start_second_transmit_fails(self):
        """Should reject second transmit (half-duplex)."""
        # Start first transmit
        response1 = client.post(
            "/api/v1/transmit",
            json={
                "image_path": "/home/admin/test1.png",
                "mode": "MartinM1",
            },
        )
        assert response1.status_code == 201

        # Try second transmit
        response2 = client.post(
            "/api/v1/transmit",
            json={
                "image_path": "/home/admin/test2.png",
                "mode": "ScottieS1",
            },
        )
        assert response2.status_code == 409

    def test_cant_transmit_while_decoding(self):
        """Should reject transmit while decode active (half-duplex)."""
        # Start decode
        client.post("/api/v1/decode/start", json={})

        # Try transmit
        response = client.post(
            "/api/v1/transmit",
            json={
                "image_path": "/home/admin/test.png",
                "mode": "MartinM1",
            },
        )
        assert response.status_code == 409


class TestGetTransmitStatus:
    """Test GET /transmit/status/{tx_id} endpoint."""

    def test_get_status_pending(self):
        """Should get status for pending transmission."""
        # Start transmit
        start_resp = client.post(
            "/api/v1/transmit",
            json={
                "image_path": "/home/admin/test.png",
                "mode": "PD120",
            },
        )
        tx_id = start_resp.json()["tx_id"]

        # Get status
        status_resp = client.get(f"/api/v1/transmit/status/{tx_id}")
        assert status_resp.status_code == 200

        data = status_resp.json()
        assert data["tx_id"] == tx_id
        assert data["state"] == "pending"
        assert data["mode"] == "PD120"
        assert data["progress_percent"] == 0.0

    def test_get_status_nonexistent(self):
        """Should return 404 for nonexistent transmission."""
        fake_id = uuid4()
        response = client.get(f"/api/v1/transmit/status/{fake_id}")

        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"] == "SESSION_NOT_FOUND"


class TestCancelTransmit:
    """Test POST /transmit/cancel/{tx_id} endpoint."""

    def test_cancel_active_transmit(self):
        """Should cancel active transmission."""
        # Start transmit
        start_resp = client.post(
            "/api/v1/transmit",
            json={
                "image_path": "/home/admin/test.png",
                "mode": "MartinM1",
            },
        )
        tx_id = start_resp.json()["tx_id"]

        # Cancel
        cancel_resp = client.post(f"/api/v1/transmit/cancel/{tx_id}")
        assert cancel_resp.status_code == 204

        # Verify cancelled state
        status_resp = client.get(f"/api/v1/transmit/status/{tx_id}")
        data = status_resp.json()
        assert data["state"] == "cancelled"

    def test_cancel_nonexistent(self):
        """Should return 404 for nonexistent transmission."""
        fake_id = uuid4()
        response = client.post(f"/api/v1/transmit/cancel/{fake_id}")

        assert response.status_code == 404

    def test_cancel_already_cancelled(self):
        """Should return 409 if already cancelled."""
        # Start and cancel
        start_resp = client.post(
            "/api/v1/transmit",
            json={
                "image_path": "/home/admin/test.png",
                "mode": "MartinM1",
            },
        )
        tx_id = start_resp.json()["tx_id"]
        client.post(f"/api/v1/transmit/cancel/{tx_id}")

        # Try to cancel again
        response = client.post(f"/api/v1/transmit/cancel/{tx_id}")
        assert response.status_code == 409


class TestDurationEstimates:
    """Test transmission duration estimates."""

    def test_martin_m1_duration(self):
        """MartinM1 should estimate ~114 seconds."""
        response = client.post(
            "/api/v1/transmit",
            json={
                "image_path": "/home/admin/test.png",
                "mode": "MartinM1",
            },
        )

        data = response.json()
        assert 110 <= data["estimated_duration_seconds"] <= 120

    def test_robot36_duration(self):
        """Robot36 should estimate ~36 seconds."""
        response = client.post(
            "/api/v1/transmit",
            json={
                "image_path": "/home/admin/test.png",
                "mode": "Robot36",
            },
        )

        data = response.json()
        assert 30 <= data["estimated_duration_seconds"] <= 40

    def test_pd240_duration(self):
        """PD240 should estimate ~240 seconds."""
        response = client.post(
            "/api/v1/transmit",
            json={
                "image_path": "/home/admin/test.png",
                "mode": "PD240",
            },
        )

        data = response.json()
        assert 235 <= data["estimated_duration_seconds"] <= 245
