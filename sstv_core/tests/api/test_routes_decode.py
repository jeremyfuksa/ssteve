"""
Unit tests for decode endpoints.

Tests /decode/start, /decode/status, and /decode/stop endpoints.
"""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import numpy as np
import pytest
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


class TestStartDecode:
    """Test POST /decode/start endpoint."""

    def test_start_decode_minimal(self):
        """Should start decode with minimal request."""
        response = client.post("/api/v1/decode/start", json={})

        assert response.status_code == 201
        data = response.json()

        assert "session_id" in data
        assert data["state"] == "listening"
        assert "websocket_url" in data
        assert "started_at" in data

    def test_failed_dsp_start_releases_half_duplex(self, mock_dsp_manager):
        """A setup error must not leave a phantom active receiver."""
        mock_dsp_manager.start_decode.side_effect = ValueError("bad device")

        response = client.post("/api/v1/decode/start", json={})

        assert response.status_code == 400
        assert session_manager._active_decode_id is None

    def test_start_decode_with_mode(self):
        """Should start decode with explicit mode."""
        response = client.post(
            "/api/v1/decode/start",
            json={
                "mode": "MartinM1",
                "auto_detect": False,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["state"] == "listening"

    def test_start_decode_with_callsign(self):
        """Should start decode with callsign."""
        response = client.post(
            "/api/v1/decode/start",
            json={
                "callsign": "W1AW",
                "save_image": True,
            },
        )

        assert response.status_code == 201

    def test_start_decode_with_timeout(self):
        """Should start decode with timeout."""
        response = client.post(
            "/api/v1/decode/start",
            json={"timeout_seconds": 300},
        )

        assert response.status_code == 201

    def test_start_decode_invalid_timeout(self):
        """Should reject invalid timeout."""
        response = client.post(
            "/api/v1/decode/start",
            json={"timeout_seconds": 5},  # Too short
        )

        assert response.status_code == 422  # Validation error

    def test_start_decode_invalid_callsign(self):
        """Should reject invalid callsign."""
        response = client.post(
            "/api/v1/decode/start",
            json={"callsign": "AB"},  # Too short
        )

        assert response.status_code == 422

    def test_start_second_decode_fails(self):
        """Should reject second decode session (half-duplex)."""
        # Start first session
        response1 = client.post("/api/v1/decode/start", json={})
        assert response1.status_code == 201

        # Try to start second session
        response2 = client.post("/api/v1/decode/start", json={})
        assert response2.status_code == 409
        data = response2.json()
        assert data["detail"]["error"] == "SESSION_CONFLICT"

    def test_websocket_url_format(self):
        """Should return properly formatted WebSocket URL."""
        response = client.post("/api/v1/decode/start", json={})
        data = response.json()

        session_id = data["session_id"]
        # The URL is built from the host the client actually reached
        # (hardcoded localhost:8000 broke remote clients).
        assert data["websocket_url"].startswith("ws://")
        assert data["websocket_url"].endswith(f"/api/v1/ws/decode/{session_id}")


class TestGetDecodeStatus:
    """Test GET /decode/status/{session_id} endpoint."""

    def test_get_status_listening(self):
        """Should get status for listening session."""
        # Start session
        start_resp = client.post("/api/v1/decode/start", json={})
        session_id = start_resp.json()["session_id"]

        # Get status
        status_resp = client.get(f"/api/v1/decode/status/{session_id}")
        assert status_resp.status_code == 200

        data = status_resp.json()
        assert data["session_id"] == session_id
        assert data["state"] == "listening"
        assert data["progress_percent"] == 0.0
        assert data["scanlines_received"] == 0

    def test_get_status_nonexistent_session(self):
        """Should return 404 for nonexistent session."""
        fake_id = uuid4()
        response = client.get(f"/api/v1/decode/status/{fake_id}")

        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"] == "SESSION_NOT_FOUND"

    def test_get_status_invalid_uuid(self):
        """Should return 422 for invalid UUID."""
        response = client.get("/api/v1/decode/status/not-a-uuid")
        assert response.status_code == 422


class TestStopDecode:
    """Test POST /decode/stop/{session_id} endpoint."""

    def test_stop_active_session(self):
        """Should stop active decode session."""
        # Start session
        start_resp = client.post("/api/v1/decode/start", json={})
        session_id = start_resp.json()["session_id"]

        # Stop session
        stop_resp = client.post(f"/api/v1/decode/stop/{session_id}")
        assert stop_resp.status_code == 204

        # Verify stopped state
        status_resp = client.get(f"/api/v1/decode/status/{session_id}")
        data = status_resp.json()
        assert data["state"] == "stopped"

    def test_stop_nonexistent_session(self):
        """Should return 404 for nonexistent session."""
        fake_id = uuid4()
        response = client.post(f"/api/v1/decode/stop/{fake_id}")

        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"] == "SESSION_NOT_FOUND"

    def test_stop_already_stopped_session(self):
        """Should return 409 if session already stopped."""
        # Start and stop session
        start_resp = client.post("/api/v1/decode/start", json={})
        session_id = start_resp.json()["session_id"]

        client.post(f"/api/v1/decode/stop/{session_id}")

        # Try to stop again
        response = client.post(f"/api/v1/decode/stop/{session_id}")
        assert response.status_code == 409
        data = response.json()
        assert data["detail"]["error"] == "SESSION_ALREADY_STOPPED"

    def test_can_start_new_session_after_stop(self):
        """Should allow new session after stopping previous."""
        # Start and stop first session
        start_resp1 = client.post("/api/v1/decode/start", json={})
        session_id1 = start_resp1.json()["session_id"]
        client.post(f"/api/v1/decode/stop/{session_id1}")

        # Start second session
        start_resp2 = client.post("/api/v1/decode/start", json={})
        assert start_resp2.status_code == 201

        session_id2 = start_resp2.json()["session_id"]
        assert session_id2 != session_id1


class TestDecodeWorkflow:
    """Test complete decode workflows."""

    def test_start_listen_stop_workflow(self):
        """Should complete start → listen → stop workflow."""
        # Start
        start_resp = client.post(
            "/api/v1/decode/start",
            json={
                "mode": "ScottieS1",
                "callsign": "N0CALL",
            },
        )
        assert start_resp.status_code == 201
        session_id = start_resp.json()["session_id"]

        # Check status
        status_resp = client.get(f"/api/v1/decode/status/{session_id}")
        assert status_resp.status_code == 200
        assert status_resp.json()["state"] == "listening"

        # Stop
        stop_resp = client.post(f"/api/v1/decode/stop/{session_id}")
        assert stop_resp.status_code == 204

        # Verify stopped
        final_status = client.get(f"/api/v1/decode/status/{session_id}")
        assert final_status.json()["state"] == "stopped"


class TestDetectMode:
    """Test POST /decode/detect_mode endpoint."""

    def _mock_detection(self, wav_path, detection_result, candidates=None):
        """Build the patch stack for a file-based detection request."""
        # soundfile may not be installed in the test env (the route imports it
        # lazily), so inject a mock module instead of patching an attribute.
        mock_sf = MagicMock()
        mock_sf.read.return_value = (np.zeros(48000), 48000)
        return (
            patch.dict(sys.modules, {"soundfile": mock_sf}),
            patch(
                "sstv_core.api.routes.decode.detect_mode_from_sync_timing",
                return_value=detection_result,
            ),
            patch(
                "sstv_core.api.routes.decode.get_top_mode_candidates",
                return_value=candidates or [],
            ),
            patch(
                "sstv_core.api.routes.decode.get_suggestion_message",
                return_value="Looks like Scottie S1 to me.",
            ),
        )

    def test_detect_mode_from_audio_file(self, tmp_path):
        """Should detect mode from an audio file with high confidence."""
        wav_path = tmp_path / "signal.wav"
        wav_path.write_bytes(b"fake wav")

        detection_result = SimpleNamespace(
            mode="ScottieS1",
            confidence=0.92,
            measured_intervals=[0.4275, 0.4276, 0.4274],
            expected_interval=0.4275,
        )
        candidates = [("ScottieS1", 0.92), ("ScottieS2", 0.45), ("MartinM1", 0.30)]

        sf_read, detect, top, suggest = self._mock_detection(
            wav_path, detection_result, candidates
        )
        with sf_read, detect, top, suggest:
            response = client.post(
                "/api/v1/decode/detect_mode",
                json={"audio_file": str(wav_path)},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "ScottieS1"
        assert data["confidence"] == 0.92
        assert data["expected_interval"] == 0.4275
        assert data["fallback_modes"] == [
            {"mode": "ScottieS1", "confidence": 0.92},
            {"mode": "ScottieS2", "confidence": 0.45},
            {"mode": "MartinM1", "confidence": 0.30},
        ]
        assert data["suggestion_message"] == "Looks like Scottie S1 to me."

    def test_detect_mode_detection_fails(self, tmp_path):
        """Should return mode=None with manual fallback message when detection fails."""
        wav_path = tmp_path / "noise.wav"
        wav_path.write_bytes(b"fake wav")

        sf_read, detect, top, suggest = self._mock_detection(wav_path, None)
        with sf_read, detect, top, suggest:
            response = client.post(
                "/api/v1/decode/detect_mode",
                json={"audio_file": str(wav_path)},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] is None
        assert data["confidence"] == 0.0
        assert data["measured_intervals"] == []
        assert data["fallback_modes"] == []
        assert "choose the mode manually" in data["suggestion_message"]

    def test_detect_mode_from_session_not_supported(self):
        """Should return 400 for an existing session (not yet implemented)."""
        start_resp = client.post("/api/v1/decode/start", json={})
        session_id = start_resp.json()["session_id"]

        response = client.post(
            "/api/v1/decode/detect_mode",
            json={"session_id": session_id},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"] == "SESSION_ANALYSIS_NOT_SUPPORTED"

    def test_detect_mode_unknown_session(self):
        """Should return 404 for a nonexistent session."""
        fake_id = str(uuid4())
        response = client.post(
            "/api/v1/decode/detect_mode",
            json={"session_id": fake_id},
        )

        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"] == "SESSION_NOT_FOUND"

    def test_detect_mode_no_audio_source(self):
        """Should reject a request with neither session_id nor audio_file.

        The Pydantic model validator rejects this before the route runs,
        so it surfaces as a 422 validation error.
        """
        response = client.post("/api/v1/decode/detect_mode", json={})

        assert response.status_code == 422

    def test_detect_mode_nonexistent_audio_file(self):
        """Should return 404 for an audio file that doesn't exist."""
        response = client.post(
            "/api/v1/decode/detect_mode",
            json={"audio_file": "/nonexistent/audio.wav"},
        )

        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"] == "AUDIO_FILE_NOT_FOUND"


class TestDecodeErrorHandling:
    """Test error handling and SSTeVe voice."""

    def test_error_messages_use_ssteve_voice(self):
        """Error messages should use conversational SSTeVe voice."""
        # Try to get nonexistent session
        fake_id = uuid4()
        response = client.get(f"/api/v1/decode/status/{fake_id}")

        data = response.json()
        message = data["detail"]["message"]

        # Should use contractions and friendly language
        assert "Can't find" in message or "can't find" in message
        assert "suggested_action" in data["detail"]

    def test_conflict_error_provides_suggestion(self):
        """Conflict errors should suggest resolution."""
        # Start first session
        client.post("/api/v1/decode/start", json={})

        # Try to start second
        response = client.post("/api/v1/decode/start", json={})

        data = response.json()
        assert "suggested_action" in data["detail"]
        assert "Stop" in data["detail"]["suggested_action"]
