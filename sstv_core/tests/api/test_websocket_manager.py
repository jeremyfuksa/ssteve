"""
Unit tests for WebSocketManager.

Tests connection management, event buffering, and broadcasting.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock
from uuid import uuid4

from sstv_core.api.websocket_manager import (
    WebSocketManager,
    WebSocketConnection,
)


@pytest.fixture
def manager():
    """Create fresh WebSocketManager."""
    return WebSocketManager()


@pytest.fixture
def mock_websocket():
    """Create mock WebSocket."""
    ws = Mock()
    ws.send_json = AsyncMock()
    return ws


class TestWebSocketConnection:
    """Test WebSocketConnection class."""

    @pytest.mark.asyncio
    async def test_send_event_success(self, mock_websocket):
        """Should send event successfully."""
        session_id = uuid4()
        conn = WebSocketConnection(mock_websocket, session_id)

        event = {"event_type": "test", "data": "hello"}
        success = await conn.send_event(event)

        assert success is True
        mock_websocket.send_json.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_send_event_failure(self, mock_websocket):
        """Should return False on send failure."""
        mock_websocket.send_json.side_effect = Exception("Connection lost")

        session_id = uuid4()
        conn = WebSocketConnection(mock_websocket, session_id)

        success = await conn.send_event({"test": "data"})
        assert success is False


class TestWebSocketManagerConnection:
    """Test WebSocket connection management."""

    @pytest.mark.asyncio
    async def test_connect(self, manager, mock_websocket):
        """Should register connection."""
        session_id = uuid4()

        conn = await manager.connect(mock_websocket, session_id)

        assert isinstance(conn, WebSocketConnection)
        assert conn.session_id == session_id

        count = await manager.get_connection_count(session_id)
        assert count == 1

    @pytest.mark.asyncio
    async def test_multiple_connections_same_session(self, manager):
        """Should support multiple connections per session."""
        session_id = uuid4()

        ws1 = Mock()
        ws1.send_json = AsyncMock()
        ws2 = Mock()
        ws2.send_json = AsyncMock()

        conn1 = await manager.connect(ws1, session_id)
        conn2 = await manager.connect(ws2, session_id)

        count = await manager.get_connection_count(session_id)
        assert count == 2

    @pytest.mark.asyncio
    async def test_disconnect(self, manager, mock_websocket):
        """Should unregister connection."""
        session_id = uuid4()

        conn = await manager.connect(mock_websocket, session_id)
        assert await manager.get_connection_count(session_id) == 1

        await manager.disconnect(conn)
        assert await manager.get_connection_count(session_id) == 0

    @pytest.mark.asyncio
    async def test_disconnect_preserves_event_buffer(self, manager, mock_websocket):
        """Should keep event buffer after disconnect."""
        session_id = uuid4()

        # Connect and broadcast event
        conn = await manager.connect(mock_websocket, session_id)
        await manager.broadcast(session_id, {"event": "test1"})

        # Disconnect
        await manager.disconnect(conn)

        # Broadcast another event
        await manager.broadcast(session_id, {"event": "test2"})

        # Reconnect - should get both buffered events
        ws2 = Mock()
        ws2.send_json = AsyncMock()
        conn2 = await manager.connect(ws2, session_id)

        sent = await manager.send_buffered_events(conn2)
        assert sent == 2


class TestEventBroadcasting:
    """Test event broadcasting."""

    @pytest.mark.asyncio
    async def test_broadcast_to_single_connection(self, manager, mock_websocket):
        """Should broadcast to single connection."""
        session_id = uuid4()

        await manager.connect(mock_websocket, session_id)

        event = {"event_type": "test", "data": "hello"}
        sent = await manager.broadcast(session_id, event)

        assert sent == 1
        mock_websocket.send_json.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_broadcast_to_multiple_connections(self, manager):
        """Should broadcast to all connections."""
        session_id = uuid4()

        ws1 = Mock()
        ws1.send_json = AsyncMock()
        ws2 = Mock()
        ws2.send_json = AsyncMock()

        await manager.connect(ws1, session_id)
        await manager.connect(ws2, session_id)

        event = {"event_type": "test"}
        sent = await manager.broadcast(session_id, event)

        assert sent == 2
        ws1.send_json.assert_called_once_with(event)
        ws2.send_json.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_broadcast_removes_failed_connections(self, manager):
        """Should remove failed connections."""
        session_id = uuid4()

        ws1 = Mock()
        ws1.send_json = AsyncMock()

        ws2 = Mock()
        ws2.send_json = AsyncMock(side_effect=Exception("Failed"))

        await manager.connect(ws1, session_id)
        await manager.connect(ws2, session_id)

        event = {"event_type": "test"}
        sent = await manager.broadcast(session_id, event)

        # Only ws1 succeeded
        assert sent == 1

        # ws2 should be removed
        count = await manager.get_connection_count(session_id)
        assert count == 1

    @pytest.mark.asyncio
    async def test_broadcast_without_connections(self, manager):
        """Should buffer events even without connections."""
        session_id = uuid4()

        event = {"event_type": "test"}
        sent = await manager.broadcast(session_id, event)

        assert sent == 0  # No active connections

        # But event should be buffered
        ws = Mock()
        ws.send_json = AsyncMock()
        conn = await manager.connect(ws, session_id)

        buffered_sent = await manager.send_buffered_events(conn)
        assert buffered_sent == 1


class TestEventBuffering:
    """Test event buffering and catch-up."""

    @pytest.mark.asyncio
    async def test_buffer_events(self, manager):
        """Should buffer events for catch-up."""
        session_id = uuid4()

        # Broadcast events without connections
        await manager.broadcast(session_id, {"event": 1})
        await manager.broadcast(session_id, {"event": 2})
        await manager.broadcast(session_id, {"event": 3})

        # Connect and get buffered events
        ws = Mock()
        ws.send_json = AsyncMock()
        conn = await manager.connect(ws, session_id)

        sent = await manager.send_buffered_events(conn)
        assert sent == 3

    @pytest.mark.asyncio
    async def test_buffer_max_size(self, manager):
        """Should limit buffer to 100 events (FIFO)."""
        session_id = uuid4()

        # Broadcast 150 events
        for i in range(150):
            await manager.broadcast(session_id, {"event": i})

        # Connect and get buffered events
        ws = Mock()
        ws.send_json = AsyncMock()
        conn = await manager.connect(ws, session_id)

        sent = await manager.send_buffered_events(conn)

        # Should only get last 100
        assert sent == 100

        # First call should be event 50 (events 0-49 dropped)
        first_call = ws.send_json.call_args_list[0]
        assert first_call[0][0]["event"] == 50


class TestSessionManagement:
    """Test session management."""

    @pytest.mark.asyncio
    async def test_get_active_sessions(self, manager, mock_websocket):
        """Should track active sessions."""
        session1 = uuid4()
        session2 = uuid4()

        await manager.connect(mock_websocket, session1)
        await manager.broadcast(session2, {"event": "test"})

        active = await manager.get_active_sessions()

        assert session1 in active
        assert session2 in active

    @pytest.mark.asyncio
    async def test_clear_session(self, manager, mock_websocket):
        """Should clear session data."""
        session_id = uuid4()

        # Create connection and buffer events
        conn = await manager.connect(mock_websocket, session_id)
        await manager.broadcast(session_id, {"event": "test"})

        # Clear session
        await manager.clear_session(session_id)

        # Connection should be gone
        count = await manager.get_connection_count(session_id)
        assert count == 0

        # Session should not be active
        active = await manager.get_active_sessions()
        assert session_id not in active
