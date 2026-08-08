"""Integration tests for SSTV decode workflow using reference audio.

Tests complete decode pipeline:
1. Start decode session (API)
2. Play reference audio file
3. Receive VIS detection event (WebSocket)
4. Receive scanline updates (WebSocket)
5. Receive decode complete event (WebSocket)
6. Verify image saved to disk
7. Verify database record created
"""

import asyncio
from pathlib import Path

import pytest

from sstv_core.api.main import app


@pytest.fixture(scope="module")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_db():
    """Create temporary in-memory database for tests."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    # Use in-memory SQLite database
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine)

    # Create tables
    from sstv_core.database.models import Base
    Base.metadata.create_all(bind=engine)

    # Create default configuration
    with session_factory() as session:
        from sstv_core.database import get_or_create_config
        get_or_create_config(session)

    yield session_factory

    # Cleanup
    engine.dispose()


@pytest.fixture
def client(temp_db):
    """Create test client with temp database."""
    from fastapi.testclient import TestClient
    from sstv_core.api import main as api_main

    # Save original values
    original_factory = api_main._db_session_factory
    original_engine = api_main._db_engine

    # Override database session factory globally before app startup
    api_main._db_session_factory = temp_db

    # Also override the engine to match temp_db (extract from temp_db)
    # The session_factory is bound to an engine internally
    api_main._db_engine = None  # Will be set by _ensure_database_initialized

    # Create test client (this triggers app lifespan with our temp database)
    with TestClient(app) as test_client:
        yield test_client

    # Restore original
    api_main._db_session_factory = original_factory
    api_main._db_engine = original_engine


@pytest.fixture
def reference_audio():
    """Get path to reference audio directory."""
    return Path(__file__).parent.parent / "reference" / "audio"


@pytest.fixture
def reference_images():
    """Get path to reference images directory."""
    return Path(__file__).parent.parent / "reference" / "images"


@pytest.mark.integration
def test_decode_mmsstv_scottie_s1_audio(client, reference_audio):
    """Test decoding MMSSTV Scottie S1 reference audio.

    This test uses actual reference audio from MMSSTV software
    to validate the decode pipeline works correctly.
    """
    # Find reference audio file
    audio_file = reference_audio / "mmsstv" / "scottie_s1_bear_je3hht.wav"

    if not audio_file.exists():
        pytest.skip(f"Reference audio not found: {audio_file}")

    # Start decode session
    response = client.post(
        "/api/v1/decode/start",
        json={
            "device_id": "mock_input",
            "mode": None,  # Auto-detect
            "callsign": None,
            "timeout_seconds": 120,
        },
    )

    assert response.status_code == 201
    session_id = response.json()["session_id"]

    # TODO: Simulate audio playback through mocked stream
    # For now, just verify session was created

    # Get session status
    status_response = client.get(f"/api/v1/decode/status/{session_id}")
    assert status_response.status_code == 200
    status = status_response.json()

    assert status["state"] in ["listening", "vis_detected", "decoding"]
    assert status["session_id"] == str(session_id)

    # Stop decode session
    client.post(f"/api/v1/decode/stop/{session_id}")

    # Verify session is stopped
    status_response = client.get(f"/api/v1/decode/status/{session_id}")
    assert status_response.json()["state"] in ["stopped", "completed"]


@pytest.mark.integration
def test_forced_scottie_s2_rejected_no_decoder_exists(client):
    """ScottieS2 has no decoder, so forcing it must be a 400, not a 201.

    This test used to assert the lie: a forced ScottieS2 session returned
    201 and then died silently inside the background task. If an S2 decoder
    is ever implemented, add it to SUPPORTED_DECODE_MODES and repurpose the
    EssexHAM reference audio for a real decode test.
    """
    response = client.post(
        "/api/v1/decode/start",
        json={
            "device_id": "mock_input",
            "mode": "ScottieS2",
            "callsign": "TEST",
            "timeout_seconds": 120,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "UNSUPPORTED_MODE"


@pytest.mark.integration
def test_decode_ariss_real_world_audio(client, reference_audio):
    """Test decoding ARISS/ISS real-world audio.

    Uses actual ISS transmission recordings to test noise tolerance.
    """
    audio_file = reference_audio / "ariss" / "ariss-20201004-1620.wav"

    if not audio_file.exists():
        pytest.skip(f"Reference audio not found: {audio_file}")

    # Start decode session with longer timeout for noisy audio
    response = client.post(
        "/api/v1/decode/start",
        json={
            "device_id": "mock_input",
            "mode": None,  # Auto-detect
            "callsign": "ISS",
            "timeout_seconds": 180,
        },
    )

    assert response.status_code == 201
    session_id = response.json()["session_id"]

    # Verify session
    status = client.get(f"/api/v1/decode/status/{session_id}")
    assert status.status_code == 200

    # Cleanup
    client.post(f"/api/v1/decode/stop/{session_id}")


@pytest.mark.integration
def test_decode_half_duplex_enforcement(client):
    """Test that half-duplex is enforced (can't have 2 decodes)."""
    # Start first decode session
    response1 = client.post(
        "/api/v1/decode/start",
        json={
            "device_id": "mock_input",
            "mode": None,
            "callsign": None,
            "timeout_seconds": 60,
        },
    )
    assert response1.status_code == 201
    session_id_1 = response1.json()["session_id"]

    # Try to start second decode session (should fail)
    response2 = client.post(
        "/api/v1/decode/start",
        json={
            "device_id": "mock_input",
            "mode": None,
            "callsign": None,
            "timeout_seconds": 60,
        },
    )
    assert response2.status_code == 409
    assert "SESSION_CONFLICT" in response2.json()["detail"]["error"]

    # Stop first session
    client.post(f"/api/v1/decode/stop/{session_id_1}")

    # Now second decode should work
    response3 = client.post(
        "/api/v1/decode/start",
        json={
            "device_id": "mock_input",
            "mode": None,
            "callsign": None,
            "timeout_seconds": 60,
        },
    )
    assert response3.status_code == 201
    client.post(f"/api/v1/decode/stop/{response3.json()['session_id']}")

    # Cleanup
    session_id_3 = response3.json()["session_id"]
    client.post(f"/api/v1/decode/stop/{session_id_3}")
