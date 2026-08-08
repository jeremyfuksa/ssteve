"""Session manager for tracking decode and transmit sessions.

Enforces half-duplex constraint: only one decode session and one transmit
session can be active at a time. Sessions are tracked by UUID and expire
after 5 minutes of inactivity.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4

from sstv_core.api.models import DecodeState, TransmitState


class SessionData:
    """Data for a single session (decode or transmit)."""

    def __init__(self, session_id: UUID, session_type: str):
        self.session_id = session_id
        self.session_type = session_type  # "decode" or "transmit"
        self.state: str = "pending"
        self.created_at = datetime.now(timezone.utc)
        self.last_activity = datetime.now(timezone.utc)
        self.metadata: dict = {}

    def update_activity(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = datetime.now(timezone.utc)

    def is_expired(self, timeout_minutes: int = 5) -> bool:
        """Check if session has expired due to inactivity."""
        expiry_time = self.last_activity + timedelta(minutes=timeout_minutes)
        return datetime.now(timezone.utc) > expiry_time

    def is_terminal_state(self) -> bool:
        """Check if session is in a terminal state."""
        terminal_states = {
            DecodeState.COMPLETED.value,
            DecodeState.FAILED.value,
            DecodeState.STOPPED.value,
            TransmitState.COMPLETED.value,
            TransmitState.FAILED.value,
            TransmitState.CANCELLED.value,
        }
        return self.state in terminal_states


class SessionManager:
    """Singleton session manager for tracking SSTV sessions.

    Enforces half-duplex constraint:
    - At most one active decode session
    - At most one active transmit session
    - Decode and transmit sessions can't overlap

    Sessions expire after 5 minutes of inactivity.
    """

    _instance: Optional["SessionManager"] = None
    _lock = asyncio.Lock()

    def __new__(cls):
        """Ensure singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize session manager (only once)."""
        if self._initialized:
            return

        self._decode_sessions: dict[UUID, SessionData] = {}
        self._transmit_sessions: dict[UUID, SessionData] = {}
        self._active_decode_id: UUID | None = None
        self._active_transmit_id: UUID | None = None
        self._cleanup_task: asyncio.Task | None = None
        self._initialized = True

    async def start_cleanup_task(self) -> None:
        """Start background cleanup task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_cleanup_task(self) -> None:
        """Stop background cleanup task."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    async def _cleanup_loop(self) -> None:
        """Background task that cleans up expired sessions every 60s."""
        while True:
            try:
                await asyncio.sleep(60)  # Run every 60 seconds
                await self.cleanup_expired_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Log error but don't crash cleanup loop
                print(f"Error in cleanup loop: {e}")

    async def cleanup_expired_sessions(self) -> int:
        """Remove expired sessions. Returns number of sessions cleaned up."""
        # Stop active DSP operations before deleting their bookkeeping. The
        # import is local to avoid the module-level session/DSP dependency cycle.
        async with self._lock:
            expired_active_decode = [
                sid
                for sid, session in self._decode_sessions.items()
                if session.is_expired() and not session.is_terminal_state()
            ]
            expired_active_transmit = [
                sid
                for sid, session in self._transmit_sessions.items()
                if session.is_expired() and not session.is_terminal_state()
            ]

        if expired_active_decode or expired_active_transmit:
            from sstv_core.api.dsp_manager import dsp_manager

            for sid in expired_active_decode:
                await dsp_manager.stop_decode(sid)
            for sid in expired_active_transmit:
                await dsp_manager.stop_transmit(sid)

        async with self._lock:
            cleaned = 0

            # Clean decode sessions
            expired_decode = [
                sid
                for sid, session in self._decode_sessions.items()
                if session.is_expired() or session.is_terminal_state()
            ]
            for sid in expired_decode:
                del self._decode_sessions[sid]
                if self._active_decode_id == sid:
                    self._active_decode_id = None
                cleaned += 1

            # Clean transmit sessions
            expired_transmit = [
                sid
                for sid, session in self._transmit_sessions.items()
                if session.is_expired() or session.is_terminal_state()
            ]
            for sid in expired_transmit:
                del self._transmit_sessions[sid]
                if self._active_transmit_id == sid:
                    self._active_transmit_id = None
                cleaned += 1

            return cleaned

    async def create_decode_session(
        self, metadata: dict | None = None
    ) -> SessionData:
        """Create a new decode session.

        Raises:
            RuntimeError: If a decode session is already active (half-duplex)

        """
        async with self._lock:
            # Check for active decode session
            if self._active_decode_id is not None:
                active = self._decode_sessions.get(self._active_decode_id)
                if active and not active.is_terminal_state():
                    raise RuntimeError(
                        f"Decode session {self._active_decode_id} already active. "
                        "Stop it before starting a new one."
                    )

            # Check for active transmit session (half-duplex enforcement)
            if self._active_transmit_id is not None:
                active = self._transmit_sessions.get(self._active_transmit_id)
                if active and not active.is_terminal_state():
                    raise RuntimeError(
                        f"Transmit session {self._active_transmit_id} is active. "
                        "Can't decode while transmitting (half-duplex)."
                    )

            # Create new session
            session_id = uuid4()
            session = SessionData(session_id, "decode")
            session.state = DecodeState.LISTENING.value
            if metadata:
                session.metadata = metadata

            self._decode_sessions[session_id] = session
            self._active_decode_id = session_id

            return session

    async def create_transmit_session(
        self, metadata: dict | None = None
    ) -> SessionData:
        """Create a new transmit session.

        Raises:
            RuntimeError: If a transmit session is already active (half-duplex)

        """
        async with self._lock:
            # Check for active transmit session
            if self._active_transmit_id is not None:
                active = self._transmit_sessions.get(self._active_transmit_id)
                if active and not active.is_terminal_state():
                    raise RuntimeError(
                        f"Transmit session {self._active_transmit_id} already active. "
                        "Stop it before starting a new one."
                    )

            # Check for active decode session (half-duplex enforcement)
            if self._active_decode_id is not None:
                active = self._decode_sessions.get(self._active_decode_id)
                if active and not active.is_terminal_state():
                    raise RuntimeError(
                        f"Decode session {self._active_decode_id} is active. "
                        "Can't transmit while decoding (half-duplex)."
                    )

            # Create new session
            tx_id = uuid4()
            session = SessionData(tx_id, "transmit")
            session.state = TransmitState.PENDING.value
            if metadata:
                session.metadata = metadata

            self._transmit_sessions[tx_id] = session
            self._active_transmit_id = tx_id

            return session

    async def get_decode_session(self, session_id: UUID) -> SessionData | None:
        """Get decode session by ID."""
        async with self._lock:
            session = self._decode_sessions.get(session_id)
            if session:
                session.update_activity()
            return session

    async def get_transmit_session(self, tx_id: UUID) -> SessionData | None:
        """Get transmit session by ID."""
        async with self._lock:
            session = self._transmit_sessions.get(tx_id)
            if session:
                session.update_activity()
            return session

    async def update_decode_state(
        self, session_id: UUID, state: DecodeState, metadata: dict | None = None
    ) -> None:
        """Update decode session state."""
        async with self._lock:
            session = self._decode_sessions.get(session_id)
            if session is None:
                raise ValueError(f"Decode session {session_id} not found")

            session.state = state.value
            session.update_activity()

            if metadata:
                session.metadata.update(metadata)

            # Clear active session if terminal state
            if session.is_terminal_state() and self._active_decode_id == session_id:
                self._active_decode_id = None

    async def update_transmit_state(
        self, tx_id: UUID, state: TransmitState, metadata: dict | None = None
    ) -> None:
        """Update transmit session state."""
        async with self._lock:
            session = self._transmit_sessions.get(tx_id)
            if session is None:
                raise ValueError(f"Transmit session {tx_id} not found")

            session.state = state.value
            session.update_activity()

            if metadata:
                session.metadata.update(metadata)

            # Clear active session if terminal state
            if session.is_terminal_state() and self._active_transmit_id == tx_id:
                self._active_transmit_id = None

    async def stop_decode_session(self, session_id: UUID) -> None:
        """Stop a decode session."""
        await self.update_decode_state(session_id, DecodeState.STOPPED)

    async def cancel_transmit_session(self, tx_id: UUID) -> None:
        """Cancel a transmit session."""
        await self.update_transmit_state(tx_id, TransmitState.CANCELLED)

    async def get_active_decode_id(self) -> UUID | None:
        """Get active decode session ID."""
        async with self._lock:
            return self._active_decode_id

    async def get_active_transmit_id(self) -> UUID | None:
        """Get active transmit session ID."""
        async with self._lock:
            return self._active_transmit_id

    async def has_active_sessions(self) -> bool:
        """Check if any sessions are active."""
        async with self._lock:
            has_decode = (
                self._active_decode_id is not None
                and not self._decode_sessions[self._active_decode_id].is_terminal_state()
            )
            has_transmit = (
                self._active_transmit_id is not None
                and not self._transmit_sessions[
                    self._active_transmit_id
                ].is_terminal_state()
            )
            return has_decode or has_transmit

    def reset(self) -> None:
        """Reset session manager (for testing only)."""
        self._decode_sessions.clear()
        self._transmit_sessions.clear()
        self._active_decode_id = None
        self._active_transmit_id = None


# Global singleton instance
session_manager = SessionManager()
