"""WebSocket manager for real-time SSTV event broadcasting.

Manages WebSocket connections for decode and transmit sessions, buffering
events during disconnects and providing catch-up on reconnection.
"""

import asyncio
from collections import defaultdict, deque
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import WebSocket


class WebSocketConnection:
    """Represents a single WebSocket connection."""

    def __init__(self, websocket: WebSocket, session_id: UUID):
        self.websocket = websocket
        self.session_id = session_id
        self.connected_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()

    async def send_event(self, event: dict[str, Any]) -> bool:
        """Send event to client.

        Returns:
            True if sent successfully, False if connection is broken

        """
        try:
            await self.websocket.send_json(event)
            self.last_activity = datetime.utcnow()
            return True
        except Exception:
            return False


class WebSocketManager:
    """Manages WebSocket connections and event broadcasting.

    Features:
    - Multiple connections per session (e.g., desktop + mobile)
    - Event buffering during disconnect (max 100 events, FIFO)
    - Catch-up events on reconnection
    - Session persistence for 5 minutes after disconnect
    """

    def __init__(self):
        # Active connections: session_id -> set of WebSocketConnection
        self._connections: dict[UUID, set[WebSocketConnection]] = defaultdict(set)

        # Event buffers: session_id -> deque of events
        # Persists events during disconnect for catch-up
        self._event_buffers: dict[UUID, deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=100)  # Max 100 buffered events
        )

        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

    async def connect(
        self, websocket: WebSocket, session_id: UUID
    ) -> WebSocketConnection:
        """Register a new WebSocket connection.

        Args:
            websocket: FastAPI WebSocket instance
            session_id: Session ID this connection belongs to

        Returns:
            WebSocketConnection instance

        """
        async with self._lock:
            connection = WebSocketConnection(websocket, session_id)
            self._connections[session_id].add(connection)
            return connection

    async def disconnect(self, connection: WebSocketConnection) -> None:
        """Unregister a WebSocket connection.

        Events continue to be buffered for this session for 5 minutes
        to allow reconnection.
        """
        async with self._lock:
            session_id = connection.session_id
            if session_id in self._connections:
                self._connections[session_id].discard(connection)

                # Remove session entry if no connections remain
                if not self._connections[session_id]:
                    del self._connections[session_id]

    async def broadcast(self, session_id: UUID, event: dict[str, Any]) -> int:
        """Broadcast event to all connections for a session.

        Event is also buffered for catch-up if client reconnects.

        Args:
            session_id: Target session ID
            event: Event data to broadcast

        Returns:
            Number of connections successfully notified

        """
        # Snapshot under the lock, send outside it. Holding the manager-wide
        # lock across network sends meant one slow or backpressured client
        # stalled event delivery for every session -- and the decode worker
        # awaits broadcast inline, so it stalled decoding too.
        async with self._lock:
            self._event_buffers[session_id].append(event)
            connections = set(self._connections.get(session_id, set()))

        sent_count = 0
        failed_connections = set()
        for conn in connections:
            success = await conn.send_event(event)
            if success:
                sent_count += 1
            else:
                failed_connections.add(conn)

        if failed_connections:
            async with self._lock:
                for failed_conn in failed_connections:
                    self._connections[session_id].discard(failed_conn)

        return sent_count

    async def send_buffered_events(
        self, connection: WebSocketConnection
    ) -> int:
        """Send buffered events to a reconnected client (catch-up).

        Returns:
            Number of buffered events sent

        """
        async with self._lock:
            session_id = connection.session_id
            buffered = self._event_buffers.get(session_id, deque())

            sent_count = 0
            for event in buffered:
                success = await connection.send_event(event)
                if success:
                    sent_count += 1
                else:
                    # Connection failed, stop sending
                    break

            return sent_count

    async def get_connection_count(self, session_id: UUID) -> int:
        """Get number of active connections for a session."""
        async with self._lock:
            return len(self._connections.get(session_id, set()))

    async def clear_session(self, session_id: UUID) -> None:
        """Clear all connections and buffered events for a session.

        Called when a session completes or expires.
        """
        async with self._lock:
            # Disconnect all connections
            if session_id in self._connections:
                del self._connections[session_id]

            # Clear event buffer
            if session_id in self._event_buffers:
                del self._event_buffers[session_id]

    async def get_active_sessions(self) -> set[UUID]:
        """Get all session IDs with active connections or buffered events."""
        async with self._lock:
            active = set(self._connections.keys())
            active.update(self._event_buffers.keys())
            return active

    async def broadcast_library_event(self, event: dict[str, Any]) -> int:
        """Broadcast library event to all connected clients.

        Library events (image created/modified/deleted) are broadcast to all
        WebSocket connections regardless of session ID.

        Args:
            event: Event data to broadcast

        Returns:
            Number of connections successfully notified

        """
        async with self._lock:
            # Broadcast to all connections across all sessions
            sent_count = 0

            # Track failed connections for removal
            failed_connections = set()

            for session_id, connections in self._connections.items():
                for conn in connections:
                    success = await conn.send_event(event)
                    if success:
                        sent_count += 1
                    else:
                        failed_connections.add((session_id, conn))

            # Remove failed connections
            for session_id, failed_conn in failed_connections:
                if session_id in self._connections:
                    self._connections[session_id].discard(failed_conn)

            return sent_count


# Global singleton instance
websocket_manager = WebSocketManager()
