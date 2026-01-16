"""DSP manager for coordinating RX/TX instances with API sessions.

Bridges the gap between the API layer (FastAPI routes) and the DSP modules
(rx_manager, tx_manager). Manages lifecycle of decode/transmit operations,
wires progress callbacks to WebSocket events, and handles session state updates.
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from sstv_core.audio.device_manager import AudioDeviceManager
from sstv_core.audio.ptt_controller import PTTController, PTTMethod
from sstv_core.audio.stream_manager import AudioStreamManager
from sstv_core.decode.rx_manager import RXManager, RXProgress, RXState
from sstv_core.encode.tx_manager import TXManager, TXProgress, TXState
from sstv_core.api.models import DecodeState, TransmitState
from sstv_core.api.session_manager import session_manager
from sstv_core.api.websocket_manager import websocket_manager

logger = logging.getLogger(__name__)


class DSPManager:
    """
    Manages DSP module lifecycle and wiring to API sessions.

    Responsibilities:
    - Create and manage RXManager/TXManager instances
    - Wire DSP progress callbacks to WebSocket events
    - Update session state based on DSP progress
    - Handle completion and cleanup
    - Manage shared audio infrastructure
    """

    def __init__(self, db_session_factory: Optional[sessionmaker[Session]] = None):
        # Shared audio infrastructure
        self._device_manager = AudioDeviceManager()
        self._stream_manager = AudioStreamManager()

        # Database session factory (for creating database records)
        self._db_session_factory = db_session_factory

        # Active RX/TX instances (session_id -> manager instance)
        self._rx_managers: Dict[UUID, RXManager] = {}
        self._tx_managers: Dict[UUID, TXManager] = {}

        # Background tasks (session_id -> asyncio.Task)
        self._decode_tasks: Dict[UUID, asyncio.Task] = {}
        self._transmit_tasks: Dict[UUID, asyncio.Task] = {}

        # Track image paths for transmit operations (needed for database records)
        self._transmit_image_paths: Dict[UUID, Path] = {}

        logger.info("DSPManager initialized (database: %s)", "enabled" if db_session_factory else "disabled")

    async def start_decode(
        self,
        session_id: UUID,
        mode: Optional[str],
        auto_detect: bool,
        timeout_seconds: float,
        save_image: bool,
        callsign: Optional[str],
        device_id: Optional[str],
    ) -> None:
        """
        Start real decode operation for a session.

        Args:
            session_id: UUID of the decode session
            mode: SSTV mode (e.g., "ScottieS1") or None for auto-detect
            auto_detect: Whether to auto-detect mode from VIS code
            timeout_seconds: Timeout for VIS detection
            save_image: Whether to save decoded image to disk
            callsign: Optional callsign for filename
            device_id: Audio input device ID (string integer)

        Raises:
            RuntimeError: If audio device not found or unavailable
        """
        logger.info(
            "Starting decode session %s: mode=%s, auto_detect=%s, device=%s",
            session_id,
            mode,
            auto_detect,
            device_id,
        )

        # Create RX manager
        rx_mgr = RXManager(
            stream_manager=self._stream_manager,
            sample_rate=48000,
            save_directory=Path.home() / "sstv_images",
        )

        # Wire progress callback
        def on_progress(progress: RXProgress):
            """Callback invoked by rx_manager on progress updates."""
            asyncio.create_task(self._handle_rx_progress(session_id, progress))

        rx_mgr.set_progress_callback(on_progress)
        self._rx_managers[session_id] = rx_mgr

        # Parse device ID (None = default device)
        device_index = int(device_id) if device_id and device_id.isdigit() else None

        # Start decode as background task
        decode_task = asyncio.create_task(
            rx_mgr.receive(
                input_device_index=device_index,
                mode=mode if not auto_detect else None,
                timeout_sec=timeout_seconds,
                save_image=save_image,
                callsign=callsign,
            )
        )
        self._decode_tasks[session_id] = decode_task

        # Handle completion
        decode_task.add_done_callback(
            lambda t: asyncio.create_task(self._handle_decode_complete(session_id, t))
        )

        logger.info("Decode task started for session %s", session_id)

    async def stop_decode(self, session_id: UUID) -> None:
        """
        Stop active decode operation.

        Args:
            session_id: UUID of the decode session to stop
        """
        logger.info("Stopping decode session %s", session_id)

        # Cancel RX manager
        rx_mgr = self._rx_managers.get(session_id)
        if rx_mgr:
            await rx_mgr.cancel()

        # Cancel background task
        task = self._decode_tasks.get(session_id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        logger.info("Decode session %s stopped", session_id)

    async def start_transmit(
        self,
        session_id: UUID,
        image_path: str,
        mode: str,
        device_id: Optional[str],
        vox_enabled: bool,
        serial_port: Optional[str],
    ) -> None:
        """
        Start real transmit operation for a session.

        Args:
            session_id: UUID of the transmit session
            image_path: Path to image file to transmit
            mode: SSTV mode (e.g., "ScottieS1")
            device_id: Audio output device ID (string integer)
            vox_enabled: Whether to use VOX (voice-activated) PTT
            serial_port: Serial port for PTT control (e.g., "/dev/ttyUSB0")

        Raises:
            RuntimeError: If audio device or PTT device not found
        """
        logger.info(
            "Starting transmit session %s: mode=%s, device=%s, vox=%s, port=%s",
            session_id,
            mode,
            device_id,
            vox_enabled,
            serial_port,
        )

        # Create PTT controller based on configuration
        if serial_port:
            ptt = PTTController(method=PTTMethod.SERIAL, port=serial_port)
            logger.info("Using serial PTT on %s", serial_port)
        elif vox_enabled:
            ptt = PTTController(method=PTTMethod.VOX)
            logger.info("Using VOX PTT")
        else:
            ptt = PTTController(method=PTTMethod.NONE)
            logger.info("No PTT control")

        # Create TX manager
        tx_mgr = TXManager(
            stream_manager=self._stream_manager,
            ptt_controller=ptt,
            sample_rate=48000,
        )

        # Wire progress callback
        def on_progress(progress: TXProgress):
            """Callback invoked by tx_manager on progress updates."""
            asyncio.create_task(self._handle_tx_progress(session_id, progress))

        tx_mgr.set_progress_callback(on_progress)
        self._tx_managers[session_id] = tx_mgr

        # Store image path for later database record creation
        self._transmit_image_paths[session_id] = Path(image_path)

        # Parse device ID
        device_index = int(device_id) if device_id and device_id.isdigit() else None

        # Convert mode string to enum
        from sstv_core.encode.vis_generator import SSTVMode

        # Normalize mode name (e.g., "ScottieS1" -> "SCOTTIE_S1")
        mode_normalized = mode.upper().replace(" ", "_")
        try:
            sstv_mode = SSTVMode[mode_normalized]
        except KeyError:
            # Try alternate naming (e.g., "SCOTTIE_S1" exists in enum)
            logger.error("Unknown SSTV mode: %s", mode)
            raise ValueError(f"Unsupported SSTV mode: {mode}")

        # Start transmit as background task
        transmit_task = asyncio.create_task(
            tx_mgr.transmit(
                image_source=Path(image_path),
                mode=sstv_mode,
                output_device_index=device_index,
            )
        )
        self._transmit_tasks[session_id] = transmit_task

        # Handle completion
        transmit_task.add_done_callback(
            lambda t: asyncio.create_task(
                self._handle_transmit_complete(session_id, t)
            )
        )

        logger.info("Transmit task started for session %s", session_id)

    async def stop_transmit(self, session_id: UUID) -> None:
        """
        Stop active transmit operation.

        Args:
            session_id: UUID of the transmit session to stop
        """
        logger.info("Stopping transmit session %s", session_id)

        # Cancel TX manager
        tx_mgr = self._tx_managers.get(session_id)
        if tx_mgr:
            await tx_mgr.cancel()

        # Cancel background task
        task = self._transmit_tasks.get(session_id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        logger.info("Transmit session %s stopped", session_id)

    async def _handle_rx_progress(
        self, session_id: UUID, progress: RXProgress
    ) -> None:
        """
        Handle decode progress updates and emit WebSocket events.

        Args:
            session_id: UUID of the decode session
            progress: RXProgress object from rx_manager
        """
        # Update session metadata
        metadata = {
            "mode": progress.mode,
            "mode_confidence": progress.mode_confidence,
            "progress_percent": progress.percent_complete,
            "scanlines_received": progress.current_line,
            "signal_quality": progress.signal_quality,
        }

        # Map RX state to API state
        state_map = {
            RXState.LISTENING: DecodeState.LISTENING,
            RXState.VIS_DETECTED: DecodeState.LISTENING,
            RXState.DECODING: DecodeState.DECODING,
            RXState.SAVING: DecodeState.DECODING,
            RXState.COMPLETE: DecodeState.COMPLETED,
            RXState.STOPPED: DecodeState.STOPPED,
            RXState.ERROR: DecodeState.FAILED,
        }
        api_state = state_map.get(progress.state, DecodeState.LISTENING)

        # Update session state
        try:
            await session_manager.update_decode_state(session_id, api_state, metadata)
        except ValueError as e:
            logger.warning("Failed to update session state: %s", e)

        # Emit WebSocket events
        if progress.state == RXState.VIS_DETECTED:
            await websocket_manager.broadcast(
                session_id,
                {
                    "event": "vis_detected",
                    "mode": progress.mode,
                    "confidence": progress.mode_confidence,
                    "timestamp": progress.elapsed_sec,
                },
            )
            logger.info(
                "VIS detected for session %s: %s (%.2f confidence)",
                session_id,
                progress.mode,
                progress.mode_confidence,
            )

        elif progress.state == RXState.DECODING:
            # Emit scanline update (throttle to every 5 lines to reduce spam)
            if progress.current_line % 5 == 0 or progress.current_line == progress.total_lines:
                await websocket_manager.broadcast(
                    session_id,
                    {
                        "event": "scanline_update",
                        "line": progress.current_line,
                        "total": progress.total_lines,
                        "progress": progress.percent_complete,
                        "signal_quality": progress.signal_quality,
                    },
                )

    async def _handle_decode_complete(
        self, session_id: UUID, task: asyncio.Task
    ) -> None:
        """
        Handle decode completion or error.

        Args:
            session_id: UUID of the decode session
            task: Completed asyncio.Task from rx_manager.receive()
        """
        logger.info("Decode task completed for session %s", session_id)

        try:
            result = task.result()  # Path to saved image or None

            if result:
                # Decode succeeded
                logger.info("Decode succeeded: %s", result)

                # Create database record if database is enabled
                image_id = None
                if self._db_session_factory:
                    image_id = await self._create_image_record(session_id, result)

                await session_manager.update_decode_state(
                    session_id,
                    DecodeState.COMPLETED,
                    {
                        "filepath": str(result),
                        "image_id": image_id,
                    },
                )

                await websocket_manager.broadcast(
                    session_id,
                    {
                        "event": "decode_complete",
                        "filepath": str(result),
                        "image_id": image_id,
                        "timestamp": 0,  # TODO: Add elapsed time from progress
                    },
                )
            else:
                # Decode failed or cancelled
                logger.warning("Decode failed or cancelled for session %s", session_id)
                await session_manager.update_decode_state(
                    session_id,
                    DecodeState.STOPPED,
                )

        except asyncio.CancelledError:
            logger.info("Decode cancelled for session %s", session_id)
            await session_manager.update_decode_state(
                session_id,
                DecodeState.STOPPED,
            )

        except Exception as e:
            logger.error(
                "Decode error for session %s: %s", session_id, e, exc_info=True
            )
            await session_manager.update_decode_state(
                session_id,
                DecodeState.FAILED,
                {"error": str(e)},
            )

            await websocket_manager.broadcast(
                session_id,
                {
                    "event": "error",
                    "error_code": "DECODE_ERROR",
                    "message": str(e),
                },
            )

        finally:
            # Cleanup
            self._rx_managers.pop(session_id, None)
            self._decode_tasks.pop(session_id, None)
            logger.info("Decode resources cleaned up for session %s", session_id)

    async def _create_image_record(
        self, session_id: UUID, filepath: Path
    ) -> Optional[int]:
        """
        Create database record for decoded image.

        Args:
            session_id: UUID of the decode session
            filepath: Path to saved image file

        Returns:
            Database ID of created record, or None if failed
        """
        try:
            # Get session metadata
            session_data = await session_manager.get_decode_session(session_id)
            if not session_data:
                logger.warning("Session %s not found for database record creation", session_id)
                return None

            metadata = session_data.metadata
            mode = metadata.get("mode", "Unknown")
            callsign = metadata.get("callsign")
            signal_quality = metadata.get("signal_quality", 0.0)

            # Create database record in thread pool (SQLAlchemy is synchronous)
            import functools
            from sstv_core.database.models import SSTVImage

            def create_record() -> int:
                """Synchronous function to create database record."""
                with self._db_session_factory() as db_session:
                    # Extract filename from path
                    filename = filepath.name

                    # Create record
                    db_image = SSTVImage(
                        filename=filename,
                        filepath=str(filepath),
                        mode=mode,
                        callsign=callsign,
                        rx_quality_score=signal_quality,
                        is_received=True,  # This is a received image
                    )

                    db_session.add(db_image)
                    db_session.commit()

                    image_id = db_image.id
                    logger.info(
                        "Created database record for image: id=%d, path=%s",
                        image_id,
                        filepath,
                    )
                    return image_id

            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            image_id = await loop.run_in_executor(None, create_record)
            return image_id

        except Exception as e:
            logger.error(
                "Failed to create database record for image %s: %s",
                filepath,
                e,
                exc_info=True,
            )
            return None

    async def _create_transmit_image_record(
        self, session_id: UUID, filepath: Path
    ) -> Optional[int]:
        """
        Create database record for transmitted image.

        Args:
            session_id: UUID of the transmit session
            filepath: Path to transmitted image file

        Returns:
            Database ID of created record, or None if failed
        """
        try:
            # Get session metadata
            session_data = await session_manager.get_transmit_session(session_id)
            if not session_data:
                logger.warning("Session %s not found for database record creation", session_id)
                return None

            metadata = session_data.metadata
            mode = metadata.get("mode", "Unknown")
            callsign = metadata.get("callsign")

            # Create database record in thread pool (SQLAlchemy is synchronous)
            import functools
            from sstv_core.database.models import SSTVImage

            def create_record() -> int:
                """Synchronous function to create database record."""
                with self._db_session_factory() as db_session:
                    # Extract filename from path
                    filename = filepath.name

                    # Create record
                    db_image = SSTVImage(
                        filename=filename,
                        filepath=str(filepath),
                        mode=mode,
                        callsign=callsign,
                        is_received=False,  # This is a transmitted image
                    )

                    db_session.add(db_image)
                    db_session.commit()

                    image_id = db_image.id
                    logger.info(
                        "Created database record for transmitted image: id=%d, path=%s",
                        image_id,
                        filepath,
                    )
                    return image_id

            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            image_id = await loop.run_in_executor(None, create_record)
            return image_id

        except Exception as e:
            logger.error(
                "Failed to create database record for transmitted image %s: %s",
                filepath,
                e,
                exc_info=True,
            )
            return None

    async def _handle_tx_progress(
        self, session_id: UUID, progress: TXProgress
    ) -> None:
        """
        Handle transmit progress updates and emit WebSocket events.

        Args:
            session_id: UUID of the transmit session
            progress: TXProgress object from tx_manager
        """
        # Update session metadata
        metadata = {
            "progress_percent": progress.percent_complete,
            "scanlines_transmitted": progress.current_line,
            "elapsed_seconds": progress.elapsed_sec,
        }

        # Map TX state to API state
        state_map = {
            TXState.PREPARING: TransmitState.PENDING,
            TXState.KEYING: TransmitState.PTT_ENGAGED,
            TXState.TRANSMITTING: TransmitState.TRANSMITTING,
            TXState.UNKEYING: TransmitState.TRANSMITTING,
            TXState.COMPLETE: TransmitState.COMPLETED,
            TXState.ERROR: TransmitState.FAILED,
        }
        api_state = state_map.get(progress.state, TransmitState.PENDING)

        # Update session state
        try:
            await session_manager.update_transmit_state(
                session_id, api_state, metadata
            )
        except ValueError as e:
            logger.warning("Failed to update transmit session state: %s", e)

        # Emit WebSocket events (throttle to every 10% progress)
        if progress.percent_complete % 10 < 1 or progress.state == TXState.COMPLETE:
            await websocket_manager.broadcast(
                session_id,
                {
                    "event": "tx_progress",
                    "progress": progress.percent_complete,
                    "time_remaining_sec": progress.remaining_sec,
                    "current_scanline": progress.current_line,
                },
            )

    async def _handle_transmit_complete(
        self, session_id: UUID, task: asyncio.Task
    ) -> None:
        """
        Handle transmit completion or error.

        Args:
            session_id: UUID of the transmit session
            task: Completed asyncio.Task from tx_manager.transmit()
        """
        logger.info("Transmit task completed for session %s", session_id)

        try:
            success = task.result()  # Boolean

            if success:
                logger.info("Transmit succeeded for session %s", session_id)

                # Create database record if database is enabled and we have the image path
                image_id = None
                if self._db_session_factory and session_id in self._transmit_image_paths:
                    filepath = self._transmit_image_paths[session_id]
                    image_id = await self._create_transmit_image_record(session_id, filepath)

                await session_manager.update_transmit_state(
                    session_id,
                    TransmitState.COMPLETED,
                    {
                        "image_id": image_id,
                    },
                )

                await websocket_manager.broadcast(
                    session_id,
                    {
                        "event": "tx_complete",
                        "image_id": image_id,
                        "timestamp": 0,  # TODO: Add elapsed time
                    },
                )
            else:
                logger.warning("Transmit failed for session %s", session_id)
                await session_manager.update_transmit_state(
                    session_id,
                    TransmitState.FAILED,
                )

        except asyncio.CancelledError:
            logger.info("Transmit cancelled for session %s", session_id)
            await session_manager.update_transmit_state(
                session_id,
                TransmitState.CANCELLED,
            )

        except Exception as e:
            logger.error(
                "Transmit error for session %s: %s", session_id, e, exc_info=True
            )
            await session_manager.update_transmit_state(
                session_id,
                TransmitState.FAILED,
                {"error": str(e)},
            )

            await websocket_manager.broadcast(
                session_id,
                {
                    "event": "error",
                    "error_code": "TRANSMIT_ERROR",
                    "message": str(e),
                },
            )

        finally:
            # Cleanup
            self._tx_managers.pop(session_id, None)
            self._transmit_tasks.pop(session_id, None)
            self._transmit_image_paths.pop(session_id, None)
            logger.info("Transmit resources cleaned up for session %s", session_id)


# Global singleton instance (session factory will be set during app startup)
dsp_manager = DSPManager()
