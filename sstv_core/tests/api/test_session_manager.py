"""
Unit tests for SessionManager.

Tests session creation, half-duplex enforcement, expiry, and cleanup.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from uuid import UUID

from sstv_core.api.session_manager import SessionManager, SessionData
from sstv_core.api.models import DecodeState, TransmitState


@pytest.fixture
def manager():
    """Create a fresh SessionManager for each test."""
    mgr = SessionManager()
    mgr.reset()  # Clear any existing sessions
    yield mgr
    mgr.reset()


class TestSessionData:
    """Test SessionData class."""

    def test_session_creation(self):
        """Session should be created with correct defaults."""
        session = SessionData(UUID("12345678-1234-1234-1234-123456789012"), "decode")
        assert session.session_type == "decode"
        assert session.state == "pending"
        assert isinstance(session.created_at, datetime)
        assert isinstance(session.last_activity, datetime)

    def test_update_activity(self):
        """Activity timestamp should update."""
        session = SessionData(UUID("12345678-1234-1234-1234-123456789012"), "decode")
        old_activity = session.last_activity
        asyncio.sleep(0.01)  # Small delay
        session.update_activity()
        assert session.last_activity >= old_activity

    def test_is_expired(self):
        """Sessions should expire after timeout."""
        session = SessionData(UUID("12345678-1234-1234-1234-123456789012"), "decode")

        # Not expired initially
        assert not session.is_expired(timeout_minutes=5)

        # Simulate expiry by backdating last_activity
        session.last_activity = datetime.utcnow() - timedelta(minutes=6)
        assert session.is_expired(timeout_minutes=5)

    def test_is_terminal_state(self):
        """Terminal states should be detected."""
        session = SessionData(UUID("12345678-1234-1234-1234-123456789012"), "decode")

        # Non-terminal states
        session.state = DecodeState.LISTENING.value
        assert not session.is_terminal_state()

        session.state = DecodeState.DECODING.value
        assert not session.is_terminal_state()

        # Terminal states
        session.state = DecodeState.COMPLETED.value
        assert session.is_terminal_state()

        session.state = DecodeState.FAILED.value
        assert session.is_terminal_state()

        session.state = DecodeState.STOPPED.value
        assert session.is_terminal_state()


class TestSessionManagerCreation:
    """Test session creation."""

    @pytest.mark.asyncio
    async def test_create_decode_session(self, manager):
        """Should create decode session successfully."""
        session = await manager.create_decode_session()

        assert isinstance(session.session_id, UUID)
        assert session.session_type == "decode"
        assert session.state == DecodeState.LISTENING.value

        # Should be tracked as active
        active_id = await manager.get_active_decode_id()
        assert active_id == session.session_id

    @pytest.mark.asyncio
    async def test_create_decode_session_with_metadata(self, manager):
        """Should create decode session with metadata."""
        metadata = {"mode": "MartinM1", "auto_detect": True}
        session = await manager.create_decode_session(metadata=metadata)

        assert session.metadata == metadata

    @pytest.mark.asyncio
    async def test_create_transmit_session(self, manager):
        """Should create transmit session successfully."""
        session = await manager.create_transmit_session()

        assert isinstance(session.session_id, UUID)
        assert session.session_type == "transmit"
        assert session.state == TransmitState.PENDING.value

        # Should be tracked as active
        active_id = await manager.get_active_transmit_id()
        assert active_id == session.session_id

    @pytest.mark.asyncio
    async def test_create_transmit_session_with_metadata(self, manager):
        """Should create transmit session with metadata."""
        metadata = {"image_path": "/test.png", "mode": "ScottieS1"}
        session = await manager.create_transmit_session(metadata=metadata)

        assert session.metadata == metadata


class TestHalfDuplexEnforcement:
    """Test half-duplex constraint enforcement."""

    @pytest.mark.asyncio
    async def test_cant_create_second_decode_session(self, manager):
        """Should reject second decode session when one is active."""
        # Create first session
        session1 = await manager.create_decode_session()

        # Try to create second session
        with pytest.raises(RuntimeError, match="already active"):
            await manager.create_decode_session()

    @pytest.mark.asyncio
    async def test_can_create_decode_after_terminal_state(self, manager):
        """Should allow new decode session after previous completed."""
        # Create and complete first session
        session1 = await manager.create_decode_session()
        await manager.update_decode_state(
            session1.session_id, DecodeState.COMPLETED
        )

        # Should allow new session
        session2 = await manager.create_decode_session()
        assert session2.session_id != session1.session_id

    @pytest.mark.asyncio
    async def test_cant_create_second_transmit_session(self, manager):
        """Should reject second transmit session when one is active."""
        # Create first session
        session1 = await manager.create_transmit_session()

        # Try to create second session
        with pytest.raises(RuntimeError, match="already active"):
            await manager.create_transmit_session()

    @pytest.mark.asyncio
    async def test_cant_decode_while_transmitting(self, manager):
        """Should reject decode session while transmitting (half-duplex)."""
        # Start transmitting
        await manager.create_transmit_session()

        # Try to start decoding
        with pytest.raises(RuntimeError, match="half-duplex"):
            await manager.create_decode_session()

    @pytest.mark.asyncio
    async def test_cant_transmit_while_decoding(self, manager):
        """Should reject transmit session while decoding (half-duplex)."""
        # Start decoding
        await manager.create_decode_session()

        # Try to start transmitting
        with pytest.raises(RuntimeError, match="half-duplex"):
            await manager.create_transmit_session()

    @pytest.mark.asyncio
    async def test_can_transmit_after_decode_completes(self, manager):
        """Should allow transmit after decode completes."""
        # Create and complete decode session
        decode_session = await manager.create_decode_session()
        await manager.update_decode_state(
            decode_session.session_id, DecodeState.COMPLETED
        )

        # Should allow transmit session
        tx_session = await manager.create_transmit_session()
        assert tx_session is not None

    @pytest.mark.asyncio
    async def test_can_decode_after_transmit_completes(self, manager):
        """Should allow decode after transmit completes."""
        # Create and complete transmit session
        tx_session = await manager.create_transmit_session()
        await manager.update_transmit_state(
            tx_session.session_id, TransmitState.COMPLETED
        )

        # Should allow decode session
        decode_session = await manager.create_decode_session()
        assert decode_session is not None


class TestSessionRetrieval:
    """Test session retrieval."""

    @pytest.mark.asyncio
    async def test_get_decode_session(self, manager):
        """Should retrieve decode session by ID."""
        session = await manager.create_decode_session()

        retrieved = await manager.get_decode_session(session.session_id)
        assert retrieved is not None
        assert retrieved.session_id == session.session_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_decode_session(self, manager):
        """Should return None for nonexistent session."""
        fake_id = UUID("12345678-1234-1234-1234-123456789012")
        retrieved = await manager.get_decode_session(fake_id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_get_transmit_session(self, manager):
        """Should retrieve transmit session by ID."""
        session = await manager.create_transmit_session()

        retrieved = await manager.get_transmit_session(session.session_id)
        assert retrieved is not None
        assert retrieved.session_id == session.session_id

    @pytest.mark.asyncio
    async def test_get_session_updates_activity(self, manager):
        """Getting a session should update activity timestamp."""
        session = await manager.create_decode_session()
        old_activity = session.last_activity

        await asyncio.sleep(0.01)  # Small delay

        retrieved = await manager.get_decode_session(session.session_id)
        assert retrieved.last_activity >= old_activity


class TestSessionStateUpdates:
    """Test session state updates."""

    @pytest.mark.asyncio
    async def test_update_decode_state(self, manager):
        """Should update decode session state."""
        session = await manager.create_decode_session()

        await manager.update_decode_state(
            session.session_id,
            DecodeState.VIS_DETECTED,
            metadata={"mode": "ScottieS1", "confidence": 0.95},
        )

        updated = await manager.get_decode_session(session.session_id)
        assert updated.state == DecodeState.VIS_DETECTED.value
        assert updated.metadata["mode"] == "ScottieS1"

    @pytest.mark.asyncio
    async def test_update_nonexistent_decode_raises(self, manager):
        """Should raise error when updating nonexistent session."""
        fake_id = UUID("12345678-1234-1234-1234-123456789012")

        with pytest.raises(ValueError, match="not found"):
            await manager.update_decode_state(fake_id, DecodeState.DECODING)

    @pytest.mark.asyncio
    async def test_update_transmit_state(self, manager):
        """Should update transmit session state."""
        session = await manager.create_transmit_session()

        await manager.update_transmit_state(
            session.session_id,
            TransmitState.TRANSMITTING,
            metadata={"progress": 45.5},
        )

        updated = await manager.get_transmit_session(session.session_id)
        assert updated.state == TransmitState.TRANSMITTING.value
        assert updated.metadata["progress"] == 45.5

    @pytest.mark.asyncio
    async def test_terminal_state_clears_active(self, manager):
        """Updating to terminal state should clear active session."""
        session = await manager.create_decode_session()

        # Verify it's active
        active_id = await manager.get_active_decode_id()
        assert active_id == session.session_id

        # Update to terminal state
        await manager.update_decode_state(session.session_id, DecodeState.COMPLETED)

        # Should no longer be active
        active_id = await manager.get_active_decode_id()
        assert active_id is None


class TestSessionStopping:
    """Test session stopping/cancellation."""

    @pytest.mark.asyncio
    async def test_stop_decode_session(self, manager):
        """Should stop decode session."""
        session = await manager.create_decode_session()

        await manager.stop_decode_session(session.session_id)

        stopped = await manager.get_decode_session(session.session_id)
        assert stopped.state == DecodeState.STOPPED.value

    @pytest.mark.asyncio
    async def test_cancel_transmit_session(self, manager):
        """Should cancel transmit session."""
        session = await manager.create_transmit_session()

        await manager.cancel_transmit_session(session.session_id)

        cancelled = await manager.get_transmit_session(session.session_id)
        assert cancelled.state == TransmitState.CANCELLED.value


class TestSessionCleanup:
    """Test session cleanup and expiry."""

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions(self, manager):
        """Should clean up expired sessions."""
        # Create session and manually expire it
        session = await manager.create_decode_session()
        session.last_activity = datetime.utcnow() - timedelta(minutes=6)

        # Run cleanup
        cleaned = await manager.cleanup_expired_sessions()
        assert cleaned == 1

        # Session should be gone
        retrieved = await manager.get_decode_session(session.session_id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_cleanup_terminal_sessions(self, manager):
        """Should clean up sessions in terminal state."""
        # Create and complete session
        session = await manager.create_decode_session()
        await manager.update_decode_state(session.session_id, DecodeState.COMPLETED)

        # Run cleanup
        cleaned = await manager.cleanup_expired_sessions()
        assert cleaned == 1

        # Session should be gone
        retrieved = await manager.get_decode_session(session.session_id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_cleanup_preserves_active_sessions(self, manager):
        """Should preserve active non-expired sessions."""
        # Create active session
        session = await manager.create_decode_session()

        # Run cleanup
        cleaned = await manager.cleanup_expired_sessions()
        assert cleaned == 0

        # Session should still exist
        retrieved = await manager.get_decode_session(session.session_id)
        assert retrieved is not None

    @pytest.mark.asyncio
    async def test_cleanup_clears_active_id_when_expired(self, manager):
        """Should clear active session ID when cleaning expired session."""
        # Create and expire session
        session = await manager.create_decode_session()
        session.last_activity = datetime.utcnow() - timedelta(minutes=6)

        # Verify it's tracked as active
        active_id = await manager.get_active_decode_id()
        assert active_id == session.session_id

        # Run cleanup
        await manager.cleanup_expired_sessions()

        # Active ID should be cleared
        active_id = await manager.get_active_decode_id()
        assert active_id is None


class TestCleanupTask:
    """Test background cleanup task."""

    @pytest.mark.asyncio
    async def test_start_cleanup_task(self, manager):
        """Should start cleanup task."""
        await manager.start_cleanup_task()

        assert manager._cleanup_task is not None
        assert not manager._cleanup_task.done()

        await manager.stop_cleanup_task()

    @pytest.mark.asyncio
    async def test_stop_cleanup_task(self, manager):
        """Should stop cleanup task."""
        await manager.start_cleanup_task()
        await manager.stop_cleanup_task()

        assert manager._cleanup_task is None or manager._cleanup_task.done()


class TestActiveSessionQueries:
    """Test queries for active sessions."""

    @pytest.mark.asyncio
    async def test_has_active_sessions_decode(self, manager):
        """Should detect active decode session."""
        assert not await manager.has_active_sessions()

        await manager.create_decode_session()
        assert await manager.has_active_sessions()

    @pytest.mark.asyncio
    async def test_has_active_sessions_transmit(self, manager):
        """Should detect active transmit session."""
        assert not await manager.has_active_sessions()

        await manager.create_transmit_session()
        assert await manager.has_active_sessions()

    @pytest.mark.asyncio
    async def test_has_active_sessions_after_completion(self, manager):
        """Should not detect active sessions after completion."""
        session = await manager.create_decode_session()
        await manager.update_decode_state(session.session_id, DecodeState.COMPLETED)

        assert not await manager.has_active_sessions()


class TestSingletonPattern:
    """Test SessionManager singleton behavior."""

    def test_singleton_instance(self):
        """Should return same instance."""
        mgr1 = SessionManager()
        mgr2 = SessionManager()
        assert mgr1 is mgr2
