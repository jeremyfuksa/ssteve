"""Manage background decode/transmit operations for SSTeVe sessions.

Each operation runs in its own asyncio.Task, updates the session state via
SessionManager, and emits WebSocket events so clients can keep in sync.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from datetime import datetime
from uuid import UUID, uuid4

from sstv_core.api.models import DecodeState, SSTVMode, TransmitState
from sstv_core.api.session_manager import SessionData, session_manager
from sstv_core.api.websocket_manager import websocket_manager

logger = logging.getLogger(__name__)


class OperationManager:
    """Orchestrates synthetic decode/transmit workloads."""

    DECODE_TOTAL_LINES = 12
    DECODE_LINE_DELAY = 0.02
    TRANSMIT_TOTAL_LINES = 16
    TRANSMIT_LINE_DELAY = 0.015
    _VIS_CODE = 60

    def __init__(self) -> None:
        self._decode_tasks: dict[UUID, asyncio.Task] = {}
        self._transmit_tasks: dict[UUID, asyncio.Task] = {}

    def start_decode(self, session: SessionData) -> None:
        """Start the background decode worker for a session."""
        session_id = session.session_id
        if session_id in self._decode_tasks:
            return

        task = asyncio.create_task(self._decode_worker(session_id))
        self._decode_tasks[session_id] = task
        task.add_done_callback(lambda _: self._decode_tasks.pop(session_id, None))

    def start_transmit(self, session: SessionData) -> None:
        """Start transmit worker for an active transmission."""
        session_id = session.session_id
        if session_id in self._transmit_tasks:
            return

        task = asyncio.create_task(self._transmit_worker(session_id))
        self._transmit_tasks[session_id] = task
        task.add_done_callback(lambda _: self._transmit_tasks.pop(session_id, None))

    async def stop_decode(self, session_id: UUID) -> None:
        """Stop the decode worker, waiting for it to cancel."""
        task = self._decode_tasks.get(session_id)
        if not task:
            return

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def stop_transmit(self, session_id: UUID) -> None:
        """Cancel the transmit worker."""
        task = self._transmit_tasks.get(session_id)
        if not task:
            return

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def stop_all(self) -> None:
        """Cancel all running operations."""
        tasks = list(self._decode_tasks.values()) + list(self._transmit_tasks.values())
        for task in tasks:
            task.cancel()

        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass

    # Test helpers for synchronization

    def get_decode_task(self, session_id: UUID) -> asyncio.Task | None:
        """Get the running decode task (for testing)."""
        return self._decode_tasks.get(session_id)

    def get_transmit_task(self, session_id: UUID) -> asyncio.Task | None:
        """Get the running transmit task (for testing)."""
        return self._transmit_tasks.get(session_id)

    async def wait_for_decode(self, session_id: UUID, timeout: float = 5.0) -> None:
        """Wait for decode task to complete (for testing).

        Args:
            session_id: The decode session ID
            timeout: Maximum seconds to wait (default 5.0)

        Raises:
            asyncio.TimeoutError: If task doesn't complete within timeout

        """
        task = self._decode_tasks.get(session_id)
        if task:
            try:
                await asyncio.wait_for(task, timeout=timeout)
            except asyncio.CancelledError:
                # Expected when task is cancelled via stop_decode
                pass

    async def wait_for_transmit(self, session_id: UUID, timeout: float = 5.0) -> None:
        """Wait for transmit task to complete (for testing).

        Args:
            session_id: The transmit session ID
            timeout: Maximum seconds to wait (default 5.0)

        Raises:
            asyncio.TimeoutError: If task doesn't complete within timeout

        """
        task = self._transmit_tasks.get(session_id)
        if task:
            try:
                await asyncio.wait_for(task, timeout=timeout)
            except asyncio.CancelledError:
                # Expected when task is cancelled via stop_transmit
                pass

    async def _decode_worker(self, session_id: UUID) -> None:
        """Simulate decode progress for a session."""
        session = await session_manager.get_decode_session(session_id)
        if session is None:
            logger.debug("Decode worker aborted - session %s missing", session_id)
            return

        mode = self._resolve_mode(session.metadata.get("mode"))
        vis_confidence = 0.92
        last_metadata = {
            "progress_percent": 0.0,
            "scanlines_received": 0,
            "snr_db": -10.0,
            "frequency_offset_hz": -15.0,
        }

        start_time = time.monotonic()
        try:
            await session_manager.update_decode_state(
                session_id,
                DecodeState.VIS_DETECTED,
                metadata={
                    "mode": mode.value,
                    "mode_confidence": vis_confidence,
                    "vis_code": self._VIS_CODE,
                },
            )

            await websocket_manager.broadcast(
                session_id,
                {
                    "event_type": "vis_detected",
                    "mode": mode.value,
                    "confidence": vis_confidence,
                    "vis_code": self._VIS_CODE,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

            await asyncio.sleep(0.05)
            await session_manager.update_decode_state(
                session_id,
                DecodeState.DECODING,
                metadata={"progress_percent": 0.0, "scanlines_received": 0},
            )

            for line in range(1, self.DECODE_TOTAL_LINES + 1):
                progress = round((line / self.DECODE_TOTAL_LINES) * 100, 1)
                # Simulated demo values, not security-sensitive.
                snr = -10.0 + random.uniform(0.0, 2.0)  # noqa: S311
                frequency_offset = -15.0 + random.uniform(-1.0, 1.0)  # noqa: S311
                metadata = {
                    "progress_percent": progress,
                    "scanlines_received": line,
                    "snr_db": snr,
                    "frequency_offset_hz": frequency_offset,
                }
                last_metadata = metadata

                await session_manager.update_decode_state(
                    session_id,
                    DecodeState.DECODING,
                    metadata=metadata,
                )

                await websocket_manager.broadcast(
                    session_id,
                    {
                        "event_type": "scanline_update",
                        "scanline_number": line,
                        "total_scanlines": self.DECODE_TOTAL_LINES,
                        "progress_percent": progress,
                        "snr_db": snr,
                        "frequency_offset_hz": frequency_offset,
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                )

                await asyncio.sleep(self.DECODE_LINE_DELAY)

            elapsed = time.monotonic() - start_time
            image_id = uuid4()
            complete_metadata = {
                "progress_percent": 100.0,
                "scanlines_received": self.DECODE_TOTAL_LINES,
                "mode_confidence": vis_confidence,
                "snr_db": last_metadata["snr_db"],
                "frequency_offset_hz": last_metadata["frequency_offset_hz"],
                "image_id": image_id,
                "completed_at": datetime.utcnow(),
            }

            await session_manager.update_decode_state(
                session_id,
                DecodeState.COMPLETED,
                metadata=complete_metadata,
            )

            await websocket_manager.broadcast(
                session_id,
                {
                    "event_type": "decode_complete",
                    "image_id": str(image_id),
                    "mode": mode.value,
                    "snr_db": complete_metadata["snr_db"],
                    "duration_seconds": elapsed,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

        except asyncio.CancelledError:
            await session_manager.update_decode_state(
                session_id,
                DecodeState.STOPPED,
                metadata={
                    "progress_percent": last_metadata["progress_percent"],
                    "scanlines_received": last_metadata["scanlines_received"],
                    "completed_at": datetime.utcnow(),
                },
            )
            await websocket_manager.broadcast(
                session_id,
                {
                    "event_type": "error",
                    "error_code": "DECODE_CANCELLED",
                    "message": "Decode stopped before completion",
                    "recoverable": True,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
            raise

        except Exception as exc:  # pragma: no cover - best effort logging
            logger.exception("Decode worker failed (%s): %s", session_id, exc)
            await session_manager.update_decode_state(
                session_id,
                DecodeState.FAILED,
                metadata={
                    "error": str(exc),
                    "progress_percent": last_metadata["progress_percent"],
                    "scanlines_received": last_metadata["scanlines_received"],
                },
            )
            await websocket_manager.broadcast(
                session_id,
                {
                    "event_type": "error",
                    "error_code": "DECODE_FAILED",
                    "message": "Something went wrong while decoding",
                    "recoverable": False,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

    async def _transmit_worker(self, session_id: UUID) -> None:
        """Simulate transmit progress including PTT/scanline events."""
        session = await session_manager.get_transmit_session(session_id)
        if session is None:
            logger.debug("Transmit worker aborted - session %s missing", session_id)
            return

        mode = self._resolve_mode(session.metadata.get("mode"))
        last_metadata = {
            "progress_percent": 0.0,
            "scanlines_transmitted": 0,
        }
        start_time = time.monotonic()

        try:
            await session_manager.update_transmit_state(
                session_id,
                TransmitState.PTT_ENGAGED,
                metadata={"progress_percent": 0.0, "scanlines_transmitted": 0},
            )

            await websocket_manager.broadcast(
                session_id,
                {
                    "event_type": "ptt_engaged",
                    "message": "Keying radio",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

            await asyncio.sleep(0.05)
            await session_manager.update_transmit_state(
                session_id,
                TransmitState.TRANSMITTING,
                metadata={"progress_percent": 0.0, "scanlines_transmitted": 0},
            )

            await websocket_manager.broadcast(
                session_id,
                {
                    "event_type": "transmit_start",
                    "mode": mode.value,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

            for line in range(1, self.TRANSMIT_TOTAL_LINES + 1):
                progress = round((line / self.TRANSMIT_TOTAL_LINES) * 100, 1)
                metadata = {
                    "progress_percent": progress,
                    "scanlines_transmitted": line,
                }
                last_metadata = metadata

                await session_manager.update_transmit_state(
                    session_id,
                    TransmitState.TRANSMITTING,
                    metadata=metadata,
                )

                await websocket_manager.broadcast(
                    session_id,
                    {
                        "event_type": "scanline_update",
                        "scanline_number": line,
                        "total_scanlines": self.TRANSMIT_TOTAL_LINES,
                        "progress_percent": progress,
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                )

                await asyncio.sleep(self.TRANSMIT_LINE_DELAY)

            elapsed = time.monotonic() - start_time
            complete_metadata = {
                "progress_percent": 100.0,
                "scanlines_transmitted": self.TRANSMIT_TOTAL_LINES,
                "elapsed_seconds": elapsed,
                "completed_at": datetime.utcnow(),
            }

            await session_manager.update_transmit_state(
                session_id,
                TransmitState.COMPLETED,
                metadata=complete_metadata,
            )

            await websocket_manager.broadcast(
                session_id,
                {
                    "event_type": "transmit_complete",
                    "tx_id": str(session_id),
                    "mode": mode.value,
                    "duration_seconds": elapsed,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

        except asyncio.CancelledError:
            await session_manager.update_transmit_state(
                session_id,
                TransmitState.CANCELLED,
                metadata={
                    "progress_percent": last_metadata["progress_percent"],
                    "scanlines_transmitted": last_metadata["scanlines_transmitted"],
                    "completed_at": datetime.utcnow(),
                },
            )

            await websocket_manager.broadcast(
                session_id,
                {
                    "event_type": "error",
                    "error_code": "TRANSMIT_CANCELLED",
                    "message": "Transmission cancelled",
                    "recoverable": True,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
            raise

        except Exception as exc:  # pragma: no cover - best effort
            logger.exception("Transmit worker failed (%s): %s", session_id, exc)
            await session_manager.update_transmit_state(
                session_id,
                TransmitState.FAILED,
                metadata={
                    "error": str(exc),
                    "progress_percent": last_metadata["progress_percent"],
                    "scanlines_transmitted": last_metadata["scanlines_transmitted"],
                },
            )
            await websocket_manager.broadcast(
                session_id,
                {
                    "event_type": "error",
                    "error_code": "TRANSMIT_FAILED",
                    "message": "Transmission failed",
                    "recoverable": False,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

    def _resolve_mode(self, mode_value: str | None) -> SSTVMode:
        """Resolve SSTV mode string, defaulting to Scottie S1."""
        if mode_value:
            try:
                return SSTVMode(mode_value)
            except ValueError:
                pass
        return SSTVMode.SCOTTIE_S1


operation_manager = OperationManager()
