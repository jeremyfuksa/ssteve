"""DSP manager for coordinating RX/TX instances with API sessions.

Bridges the gap between the API layer (FastAPI routes) and the DSP modules
(rx_manager, tx_manager). Manages lifecycle of decode/transmit operations,
wires progress callbacks to WebSocket events, and handles session state updates.
"""

import asyncio
import logging
import time
from pathlib import Path
from uuid import UUID

import numpy as np
from sqlalchemy.orm import Session, sessionmaker

from sstv_core.accessibility.guidance_player import GuidancePlayer
from sstv_core.api.image_ids import db_image_id_to_uuid
from sstv_core.api.models import (
    AudioLevelsEvent,
    DecodeCompleteEvent,
    DecodeState,
    ErrorEvent,
    ScanlineUpdateEvent,
    SSTVMode,
    TransmitCompleteEvent,
    TransmitProgressEvent,
    TransmitState,
    VISDetectedEvent,
)
from sstv_core.api.session_manager import session_manager
from sstv_core.api.websocket_manager import websocket_manager
from sstv_core.audio.device_manager import AudioDeviceManager
from sstv_core.audio.ptt_controller import PTTController, PTTMethod
from sstv_core.audio.stream_manager import AudioStreamManager
from sstv_core.decode.fsk_decoder import FSKIDResult
from sstv_core.decode.rsv import DecodeMetrics, RSVCalculator
from sstv_core.decode.rx_manager import RXManager, RXProgress, RXState
from sstv_core.encode.tx_manager import TXManager, TXProgress, TXState

logger = logging.getLogger(__name__)


class DSPManager:
    """Manages DSP module lifecycle and wiring to API sessions.

    Responsibilities:
    - Create and manage RXManager/TXManager instances
    - Wire DSP progress callbacks to WebSocket events
    - Update session state based on DSP progress
    - Handle completion and cleanup
    - Manage shared audio infrastructure
    """

    def __init__(self, db_session_factory: sessionmaker[Session] | None = None):
        # Shared audio infrastructure. The device manager is created lazily:
        # constructing it queries PortAudio, and this class is instantiated
        # as a module-level singleton -- eager construction made `import
        # sstv_core.api.dsp_manager` itself fail on hosts with no audio
        # stack (a stated headless operating situation), so the server could
        # never even start to report the problem.
        self._device_manager_instance: AudioDeviceManager | None = None
        self._stream_manager = AudioStreamManager()

        # Database session factory (for creating database records)
        self._db_session_factory = db_session_factory

        # Active RX/TX instances (session_id -> manager instance)
        self._rx_managers: dict[UUID, RXManager] = {}
        self._tx_managers: dict[UUID, TXManager] = {}

        # Background tasks (session_id -> asyncio.Task)
        self._decode_tasks: dict[UUID, asyncio.Task] = {}
        self._transmit_tasks: dict[UUID, asyncio.Task] = {}

        # Track image paths for transmit operations (needed for database records)
        self._transmit_image_paths: dict[UUID, Path] = {}

        # Wall-clock start per session, for honest duration_seconds in
        # completion events (previously hardcoded `timestamp: 0  # TODO`).
        self._session_started: dict[UUID, float] = {}

        # Accessibility guidance player per decode session (absent = disabled).
        self._guidance_players: dict[UUID, GuidancePlayer] = {}

        logger.info(
            "DSPManager initialized (database: %s)",
            "enabled" if db_session_factory else "disabled",
        )

    @property
    def _device_manager(self) -> AudioDeviceManager:
        if self._device_manager_instance is None:
            self._device_manager_instance = AudioDeviceManager()
        return self._device_manager_instance

    def _resolve_device_index(self, device_id: str | None) -> int | None:
        """Translate a public device ID into a sounddevice index.

        Device IDs from GET /devices/audio are strings like "ca_USB_Audio"
        (macOS) or "hw:1,0" (Linux). Until 2026-08-07 this class only
        accepted bare integers, so every real ID silently fell through to
        None -- the default device -- and the user's selection was ignored.

        Raises:
            ValueError: If the ID matches no known device. Silently using
                the default device instead would transmit through the wrong
                hardware.

        """
        if not device_id:
            return None
        if device_id.isdigit():
            return int(device_id)
        index = self._device_manager.get_device_index(device_id)
        if index is None:
            raise ValueError(
                f"I can't find an audio device with ID '{device_id}'. "
                "Ask GET /devices/audio for the current list."
            )
        return int(index)

    def get_session_audio(self, session_id: UUID) -> "np.ndarray | None":
        """Recent raw audio from an active decode session, or None."""
        rx_mgr = self._rx_managers.get(session_id)
        if rx_mgr is None:
            return None
        audio = rx_mgr.get_recent_audio()
        return audio if len(audio) else None

    async def _build_guidance_player(self) -> "GuidancePlayer | None":
        """Guidance playback for this decode, when enabled in config.

        Eyes-free operation (PRODUCT.md) hangs off this: the operator hears
        the lock chime when VIS is found and a double chime on completion.
        """
        session_factory = self._db_session_factory
        if session_factory is None:
            return None

        def read() -> "GuidancePlayer | None":
            from sstv_core.config.manager import ConfigManager

            with session_factory() as db_session:
                guidance_config = ConfigManager(db_session).get_guidance_config()
            if not guidance_config.enabled:
                return None
            return GuidancePlayer(guidance_config)

        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(None, read)
        except Exception as exc:
            logger.warning("Guidance unavailable: %s", exc)
            return None

    async def _read_decode_config(self) -> dict:
        """Read AFC/squelch settings; documented defaults without a DB."""
        defaults = {
            "auto_afc": True,
            "afc_range_hz": 100.0,
            "auto_squelch": True,
            "squelch_threshold_db": -40.0,
            "image_save_directory": str(Path.home() / ".ssteve" / "images"),
        }
        session_factory = self._db_session_factory
        if session_factory is None:
            return defaults

        def read() -> dict:
            from sstv_core.config.manager import ConfigManager

            with session_factory() as db_session:
                config = ConfigManager(db_session)
                return {
                    key: config.get(key, default)
                    for key, default in defaults.items()
                }

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, read)

    async def _read_ptt_config(self) -> dict:
        """Read PTT settings from the configuration database.

        Falls back to the documented defaults when no database is wired.
        Until 2026-08-07 start_transmit never read config at all, so a
        DTR-keyed rig could never key regardless of what the user saved.
        """
        defaults = {
            "ptt_method": "vox",
            "ptt_serial_port": None,
            "ptt_serial_signal": "RTS",
            "ptt_pre_delay_ms": 500,
            "ptt_post_delay_ms": 200,
            "vox_preamble_ms": 500,
        }
        session_factory = self._db_session_factory
        if session_factory is None:
            return defaults

        def read() -> dict:
            from sstv_core.config.manager import ConfigManager

            with session_factory() as db_session:
                config = ConfigManager(db_session)
                return {
                    key: config.get(key, default)
                    for key, default in defaults.items()
                }

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, read)

    def _build_ptt_controller(
        self,
        ptt_config: dict,
        serial_port: str | None,
        vox_enabled: bool,
    ) -> PTTController:
        """Construct a PTTController from request overrides plus saved config.

        Explicit request values (serial_port, vox_enabled) pick the method;
        everything else -- RTS-vs-DTR signal, delays, VOX preamble length --
        comes from configuration.
        """
        if serial_port:
            method = PTTMethod.SERIAL
            port = serial_port
        elif vox_enabled:
            method = PTTMethod.VOX
            port = None
        else:
            method = {
                "serial": PTTMethod.SERIAL,
                "vox": PTTMethod.VOX,
            }.get(str(ptt_config["ptt_method"]), PTTMethod.NONE)
            port = ptt_config["ptt_serial_port"]

        return PTTController(
            method=method,
            serial_port=port,
            serial_signal=str(ptt_config["ptt_serial_signal"]),
            pre_delay_ms=int(ptt_config["ptt_pre_delay_ms"]),
            post_delay_ms=int(ptt_config["ptt_post_delay_ms"]),
            vox_preamble_ms=int(ptt_config["vox_preamble_ms"]),
        )

    async def start_decode(
        self,
        session_id: UUID,
        mode: str | None,
        auto_detect: bool,
        timeout_seconds: float,
        save_image: bool,
        callsign: str | None,
        device_id: str | None,
    ) -> None:
        """Start real decode operation for a session.

        Args:
            session_id: UUID of the decode session
            mode: SSTV mode (e.g., "ScottieS1") or None for auto-detect
            auto_detect: Whether to auto-detect mode from VIS code
            timeout_seconds: Timeout for VIS detection
            save_image: Whether to save decoded image to disk
            callsign: Optional callsign for filename
            device_id: Audio input device ID as returned by GET /devices/audio

        Raises:
            ValueError: If device_id matches no known audio device

        """
        logger.info(
            "Starting decode session %s: mode=%s, auto_detect=%s, device=%s",
            session_id,
            mode,
            auto_detect,
            device_id,
        )

        # Resolve the device BEFORE creating any state, so an unknown ID
        # fails the request instead of silently opening the default device.
        device_index = self._resolve_device_index(device_id)

        # Create RX manager with the user's AFC/squelch settings -- these
        # knobs were stored and served by /config but consumed by nothing
        # until 2026-08-08.
        decode_config = await self._read_decode_config()
        guidance_player = await self._build_guidance_player()
        if guidance_player is not None:
            self._guidance_players[session_id] = guidance_player
        # Save where the user configured -- one directory, watched by the
        # library watcher and written by the decoder. (Previously hardcoded
        # here while the watcher watched the CONFIGURED directory, so
        # decoded images could land outside the library.)
        save_directory = Path(
            decode_config["image_save_directory"]
            or (Path.home() / ".ssteve" / "images")
        ).expanduser()
        rx_mgr = RXManager(
            stream_manager=self._stream_manager,
            sample_rate=48000,
            save_directory=save_directory,
            auto_afc=bool(decode_config["auto_afc"]),
            afc_range_hz=float(decode_config["afc_range_hz"]),
            auto_squelch=bool(decode_config["auto_squelch"]),
            squelch_threshold_db=float(decode_config["squelch_threshold_db"]),
        )

        # Wire progress callback
        def on_progress(progress: RXProgress):
            """Relay rx_manager progress updates to the event loop."""
            # Fire-and-forget by design: task lifetime is tied to the running loop.
            _task = asyncio.create_task(  # noqa: RUF006
                self._handle_rx_progress(session_id, progress)
            )

        rx_mgr.set_progress_callback(on_progress)
        self._rx_managers[session_id] = rx_mgr
        self._session_started[session_id] = time.time()

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
        """Stop active decode operation.

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

        self._rx_managers.pop(session_id, None)
        self._decode_tasks.pop(session_id, None)

        logger.info("Decode session %s stopped", session_id)

    async def start_transmit(
        self,
        session_id: UUID,
        image_path: str,
        mode: str,
        device_id: str | None,
        vox_enabled: bool,
        serial_port: str | None,
        callsign: str | None = None,
    ) -> None:
        """Start real transmit operation for a session.

        Args:
            session_id: UUID of the transmit session
            image_path: Path to image file to transmit
            mode: SSTV mode (e.g., "ScottieS1")
            device_id: Audio output device ID (string integer)
            vox_enabled: Whether to use VOX (voice-activated) PTT
            serial_port: Serial port for PTT control (e.g., "/dev/ttyUSB0")
            callsign: Optional operator callsign to overlay on the image

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

        # Map public API values explicitly so unsupported modes cannot be sent
        # with a mismatched VIS header and scanline encoder.
        from sstv_core.encode.vis_generator import SSTVMode

        mode_map = {
            "ScottieS1": SSTVMode.SCOTTIE_S1,
            "MartinM1": SSTVMode.MARTIN_M1,
            "Robot36": SSTVMode.ROBOT_36,
        }
        try:
            sstv_mode = mode_map[mode]
        except KeyError as exc:
            supported = ", ".join(mode_map)
            raise ValueError(
                f"Unsupported transmit mode {mode!r}; implemented modes: {supported}"
            ) from exc

        # Resolve the device BEFORE creating any state, so an unknown ID
        # fails the request instead of silently keying the default device.
        device_index = self._resolve_device_index(device_id)

        # PTT: the request picks the method; RTS-vs-DTR, delays, and VOX
        # preamble come from saved configuration.
        ptt_config = await self._read_ptt_config()
        ptt = self._build_ptt_controller(ptt_config, serial_port, vox_enabled)
        logger.info(
            "PTT: method=%s signal=%s pre=%dms post=%dms",
            ptt.method.name,
            ptt_config["ptt_serial_signal"],
            int(ptt_config["ptt_pre_delay_ms"]),
            int(ptt_config["ptt_post_delay_ms"]),
        )

        # Create TX manager
        tx_mgr = TXManager(
            stream_manager=self._stream_manager,
            ptt_controller=ptt,
            sample_rate=48000,
        )

        # Wire progress callback
        def on_progress(progress: TXProgress):
            """Relay tx_manager progress updates to the event loop."""
            # Fire-and-forget by design: task lifetime is tied to the running loop.
            _task = asyncio.create_task(  # noqa: RUF006
                self._handle_tx_progress(session_id, progress)
            )

        tx_mgr.set_progress_callback(on_progress)
        self._tx_managers[session_id] = tx_mgr

        # Store image path for later database record creation
        self._transmit_image_paths[session_id] = Path(image_path)
        self._session_started[session_id] = time.time()

        # Start transmit as background task
        transmit_task = asyncio.create_task(
            tx_mgr.transmit(
                image_source=Path(image_path),
                mode=sstv_mode,
                output_device_index=device_index,
                callsign=callsign,
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
        """Stop active transmit operation.

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

        self._tx_managers.pop(session_id, None)
        self._transmit_tasks.pop(session_id, None)
        self._transmit_image_paths.pop(session_id, None)

        logger.info("Transmit session %s stopped", session_id)

    async def shutdown(self) -> None:
        """Stop every active operation. Called from the API lifespan on exit.

        Transmits go first: a decode left running leaks an input stream, but a
        transmit left running can leave the radio keyed (RTS/DTR still
        asserted) after the process is gone. Shutdown is time-bounded by
        SIGTERM, so the hazard gets the guaranteed slot.

        Each stop is isolated -- one session failing must not strand the rest,
        since the whole point is that nothing is left keyed. Session IDs are
        snapshotted because stop_* mutates the dicts we would be iterating.
        """
        transmit_ids = list(self._transmit_tasks.keys())
        decode_ids = list(self._decode_tasks.keys())
        if not transmit_ids and not decode_ids:
            return

        logger.info(
            "Shutdown: stopping %d transmit and %d decode session(s)",
            len(transmit_ids),
            len(decode_ids),
        )
        for session_id in transmit_ids:
            try:
                await self.stop_transmit(session_id)
            except Exception as e:
                logger.error(
                    "Shutdown: failed to stop transmit session %s: %s",
                    session_id,
                    e,
                    exc_info=True,
                )
        for session_id in decode_ids:
            try:
                await self.stop_decode(session_id)
            except Exception as e:
                logger.error(
                    "Shutdown: failed to stop decode session %s: %s",
                    session_id,
                    e,
                    exc_info=True,
                )

    @staticmethod
    def _mode_enum(mode: str | None) -> SSTVMode | None:
        """Public mode string to enum; None when unknown rather than a guess."""
        if not mode:
            return None
        try:
            return SSTVMode(mode)
        except ValueError:
            return None

    def _session_duration(self, session_id: UUID) -> float:
        started = self._session_started.get(session_id)
        return max(0.0, time.time() - started) if started else 0.0

    async def _handle_rx_progress(
        self, session_id: UUID, progress: RXProgress
    ) -> None:
        """Handle decode progress updates and emit WebSocket events.

        Args:
            session_id: UUID of the decode session
            progress: RXProgress object from rx_manager

        """
        # Update session metadata
        rx_mgr = self._rx_managers.get(session_id)
        live_snr = rx_mgr.current_snr_db if rx_mgr else None
        metadata = {
            "mode": progress.mode,
            "mode_confidence": progress.mode_confidence,
            "progress_percent": progress.percent_complete,
            "scanlines_received": progress.current_line,
            "signal_quality": progress.signal_quality,
            "snr_db": live_snr,
        }

        # Emit audio levels event (mono monitoring - single channel)
        # Audio levels are calculated by AudioStreamManager and passed via progress
        # Emit at 10Hz rate (throttled in rx_manager to avoid spam)
        audio_levels = getattr(progress, "audio_levels", None)
        if audio_levels:
            # Convert linear RMS/peak to dB for display
            rms_db = 20.0 * np.log10(audio_levels.rms + 1e-10) if audio_levels.rms > 0 else -120.0
            peak_db = (
                20.0 * np.log10(audio_levels.peak + 1e-10) if audio_levels.peak > 0 else -120.0
            )

            await websocket_manager.broadcast(
                session_id,
                AudioLevelsEvent(
                    left_db=rms_db,
                    right_db=rms_db,  # Mono = same left/right
                    peak_db=peak_db,
                    is_clipping=bool(audio_levels.is_clipping),
                ).model_dump(mode="json"),
            )

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
            player = self._guidance_players.get(session_id)
            if player is not None:
                player.play_lock_chime()
            mode_enum = self._mode_enum(progress.mode)
            if mode_enum is not None:
                await websocket_manager.broadcast(
                    session_id,
                    VISDetectedEvent(
                        mode=mode_enum,
                        confidence=progress.mode_confidence,
                    ).model_dump(mode="json"),
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
                    ScanlineUpdateEvent(
                        scanline_number=progress.current_line,
                        total_scanlines=max(1, progress.total_lines),
                        progress_percent=min(100.0, max(0.0, progress.percent_complete)),
                        signal_quality=min(1.0, max(0.0, progress.signal_quality)),
                        snr_db=live_snr,
                    ).model_dump(mode="json"),
                )

    async def _handle_decode_complete(
        self, session_id: UUID, task: asyncio.Task
    ) -> None:
        """Handle decode completion or error.

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
                player = self._guidance_players.get(session_id)
                if player is not None:
                    player.play_complete_chime()

                # Create database record if database is enabled
                image_id = None
                if self._db_session_factory:
                    rx_mgr = self._rx_managers.get(session_id)
                    metrics = rx_mgr.get_decode_metrics() if rx_mgr else None
                    fskid = rx_mgr.get_fskid_result() if rx_mgr else None
                    db_image_id = await self._create_image_record(
                        session_id, result, metrics, fskid
                    )
                    if db_image_id is not None:
                        image_id = str(db_image_id_to_uuid(db_image_id))

                await session_manager.update_decode_state(
                    session_id,
                    DecodeState.COMPLETED,
                    {
                        "filepath": str(result),
                        "image_id": image_id,
                    },
                )

                session_data = await session_manager.get_decode_session(session_id)
                mode_str = (
                    session_data.metadata.get("mode") if session_data else None
                )
                await websocket_manager.broadcast(
                    session_id,
                    DecodeCompleteEvent(
                        image_id=UUID(image_id) if image_id else None,
                        filepath=str(result),
                        mode=self._mode_enum(mode_str),
                        duration_seconds=self._session_duration(session_id),
                    ).model_dump(mode="json"),
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
                ErrorEvent(
                    error_code="DECODE_ERROR",
                    message=str(e),
                ).model_dump(mode="json"),
            )

        finally:
            # Cleanup
            self._rx_managers.pop(session_id, None)
            self._decode_tasks.pop(session_id, None)
            self._session_started.pop(session_id, None)
            self._guidance_players.pop(session_id, None)
            logger.info("Decode resources cleaned up for session %s", session_id)

    async def _create_image_record(
        self,
        session_id: UUID,
        filepath: Path,
        metrics: "DecodeMetrics | None" = None,
        fskid: "FSKIDResult | None" = None,
    ) -> int | None:
        """Create database record for decoded image.

        Args:
            session_id: UUID of the decode session
            filepath: Path to saved image file
            metrics: Measured decode metrics for Auto-RSV (None = not collected)
            fskid: FSKID decode result, if a callsign ID followed the image

        Returns:
            Database ID of created record, or None if failed

        """
        session_factory = self._db_session_factory
        if session_factory is None:
            logger.info("Database disabled; skipping record for image %s", filepath)
            return None

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
            from sstv_core.database.models import SSTVImage

            def create_record() -> int:
                """Create the database record synchronously."""
                with session_factory() as db_session:
                    # Extract filename from path
                    filename = filepath.name

                    # Measured signal metrics + Auto-RSV report, when the
                    # decode collected them. Absent metrics stay NULL --
                    # never fabricated.
                    rsv_kwargs = {}
                    if metrics is not None:
                        report = RSVCalculator().calculate(metrics)
                        rsv_kwargs = {
                            "rx_snr_db": round(metrics.snr_db, 1)
                            if metrics.noise_floor > 0
                            else None,
                            "rx_peak_amplitude": metrics.peak_amplitude or None,
                            "rx_noise_floor": metrics.noise_floor or None,
                            "rsv_readability": report.readability,
                            "rsv_signal": report.signal,
                            "rsv_video": report.video,
                            "rsv_report": report.to_string(),
                            "decode_metrics_json": metrics.to_json(),
                        }

                    # FSKID: store the detection outcome; adopt the decoded
                    # callsign only when the checksum validated and the user
                    # didn't supply one themselves.
                    fskid_kwargs = {}
                    record_callsign = callsign
                    if fskid is not None:
                        fskid_kwargs = {
                            "fskid_detected": True,
                            "fskid_confidence": float(fskid.confidence),
                            "fskid_checksum_valid": bool(fskid.checksum_valid),
                        }
                        if fskid.checksum_valid and not record_callsign:
                            record_callsign = fskid.callsign

                    # Create record
                    db_image = SSTVImage(
                        filename=filename,
                        filepath=str(filepath),
                        mode=mode,
                        callsign=record_callsign,
                        rx_quality_score=signal_quality,
                        is_received=True,  # This is a received image
                        **rsv_kwargs,
                        **fskid_kwargs,
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
    ) -> int | None:
        """Create database record for transmitted image.

        Args:
            session_id: UUID of the transmit session
            filepath: Path to transmitted image file

        Returns:
            Database ID of created record, or None if failed

        """
        session_factory = self._db_session_factory
        if session_factory is None:
            logger.info("Database disabled; skipping record for image %s", filepath)
            return None

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
            from sstv_core.database.models import SSTVImage

            def create_record() -> int:
                """Create the database record synchronously."""
                with session_factory() as db_session:
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
        """Handle transmit progress updates and emit WebSocket events.

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
                TransmitProgressEvent(
                    progress_percent=min(100.0, max(0.0, progress.percent_complete)),
                    current_scanline=max(0, progress.current_line),
                    time_remaining_seconds=max(0.0, progress.remaining_sec),
                ).model_dump(mode="json"),
            )

    async def _handle_transmit_complete(
        self, session_id: UUID, task: asyncio.Task
    ) -> None:
        """Handle transmit completion or error.

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
                    db_image_id = await self._create_transmit_image_record(session_id, filepath)
                    if db_image_id is not None:
                        image_id = str(db_image_id_to_uuid(db_image_id))

                await session_manager.update_transmit_state(
                    session_id,
                    TransmitState.COMPLETED,
                    {
                        "image_id": image_id,
                    },
                )

                session_data = await session_manager.get_transmit_session(session_id)
                mode_str = (
                    session_data.metadata.get("mode") if session_data else None
                )
                await websocket_manager.broadcast(
                    session_id,
                    TransmitCompleteEvent(
                        tx_id=session_id,
                        mode=self._mode_enum(mode_str),
                        duration_seconds=self._session_duration(session_id),
                    ).model_dump(mode="json"),
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
                ErrorEvent(
                    error_code="TRANSMIT_ERROR",
                    message=str(e),
                ).model_dump(mode="json"),
            )

        finally:
            # Cleanup
            self._tx_managers.pop(session_id, None)
            self._transmit_tasks.pop(session_id, None)
            self._transmit_image_paths.pop(session_id, None)
            self._session_started.pop(session_id, None)
            logger.info("Transmit resources cleaned up for session %s", session_id)


# Global singleton instance (session factory will be set during app startup)
dsp_manager = DSPManager()
