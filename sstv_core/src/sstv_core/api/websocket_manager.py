"""WebSocket manager for real-time SSTV event broadcasting.

Manages WebSocket connections for decode and transmit sessions, buffering
events during disconnects and providing catch-up on reconnection.
"""

import asyncio
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import WebSocket


class WebSocketConnection:
    """Represents a single WebSocket connection."""

    def __init__(self, websocket: WebSocket, session_id: UUID):
        self.websocket = websocket
        self.session_id = session_id
        self.connected_at = datetime.now(timezone.utc)
        self.last_activity = datetime.now(timezone.utc)

    async def send_event(self, event: dict[str, Any]) -> bool:
        """Send event to client.

        Returns:
            True if sent successfully, False if connection is broken

        """
        try:
            await self.websocket.send_json(event)
            self.last_activity = datetime.now(timezone.utc)
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

        # App-channel connections (/ws), which exist while nothing is
        # decoding or transmitting. Every other connection here is keyed by
        # session, so before 2026-08-09 there was no channel at all when the
        # app was idle -- which is what blocked idle metering, device
        # hot-plug, and library pushes to an idle gallery (#57).
        self._app_connections: set[WebSocketConnection] = set()

        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

    # ---- App channel -----------------------------------------------------

    async def connect_app(self, websocket: WebSocket) -> WebSocketConnection:
        """Register an app-channel connection (no session)."""
        async with self._lock:
            # The nil UUID marks "not a session"; nothing looks it up.
            connection = WebSocketConnection(websocket, UUID(int=0))
            self._app_connections.add(connection)
            return connection

    async def disconnect_app(self, connection: WebSocketConnection) -> None:
        """Unregister an app-channel connection."""
        async with self._lock:
            self._app_connections.discard(connection)

    async def broadcast_app(self, event: dict[str, Any]) -> int:
        """Send an event to every app-channel client.

        Deliberately unbuffered: these events describe the world right now
        (devices present, levels, library contents). Replaying a stale
        device list to a reconnecting client would be worse than silence --
        it can re-fetch current state from the REST endpoints.
        """
        async with self._lock:
            connections = set(self._app_connections)

        sent = 0
        failed = set()
        for conn in connections:
            if await conn.send_event(event):
                sent += 1
            else:
                failed.add(conn)

        if failed:
            async with self._lock:
                self._app_connections -= failed
        return sent

    async def get_app_connection_count(self) -> int:
        """How many clients hold the app channel open."""
        async with self._lock:
            return len(self._app_connections)

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
        # Snapshot under the lock, send outside it -- same reason broadcast()
        # does: holding the manager-wide lock across network sends lets one
        # backpressured client stall delivery to everyone else.
        async with self._lock:
            targets = [
                (session_id, conn)
                for session_id, connections in self._connections.items()
                for conn in connections
            ]
            # App-channel clients are the real audience here: an idle gallery
            # has no session, so before 2026-08-09 the watcher's events were
            # broadcast only to clients that happened to be mid-decode.
            app_targets = list(self._app_connections)

        sent_count = 0
        failed_session: set[tuple[UUID, WebSocketConnection]] = set()
        for session_id, conn in targets:
            if await conn.send_event(event):
                sent_count += 1
            else:
                failed_session.add((session_id, conn))

        failed_app = set()
        for conn in app_targets:
            if await conn.send_event(event):
                sent_count += 1
            else:
                failed_app.add(conn)

        if failed_session or failed_app:
            async with self._lock:
                for session_id, failed_conn in failed_session:
                    if session_id in self._connections:
                        self._connections[session_id].discard(failed_conn)
                self._app_connections -= failed_app

        return sent_count


# Global singleton instance
websocket_manager = WebSocketManager()
