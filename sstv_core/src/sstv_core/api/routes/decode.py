"""Decode endpoints for SSTV reception.

Handles:
- POST /decode/start - Start listening for SSTV signal
- POST /decode/detect_mode - Detect mode from sync timing (when VIS fails)
- GET /decode/status/{session_id} - Get decode progress
- POST /decode/stop/{session_id} - Stop active decode session
"""

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from sstv_core.api.dsp_manager import dsp_manager
from sstv_core.api.models import (
    DecodeStartRequest,
    DecodeStartResponse,
    DecodeState,
    DecodeStatusResponse,
    ModeDetectionRequest,
    ModeDetectionResponse,
)
from sstv_core.api.session_manager import session_manager
from sstv_core.smart_features.mode_detector import (
    detect_mode_from_sync_timing,
    get_suggestion_message,
    get_top_mode_candidates,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/decode", tags=["decode"])

# Modes with actual decoder implementations. The SSTVMode enum advertises 12
# modes, but forcing any other one used to 201 and then die silently inside
# the swallowed background task.
SUPPORTED_DECODE_MODES = {"ScottieS1", "MartinM1", "Robot36"}


@router.post("/detect_mode", response_model=ModeDetectionResponse, status_code=status.HTTP_200_OK)
async def detect_mode(request: ModeDetectionRequest) -> ModeDetectionResponse:
    """Detect SSTV mode from sync pulse timing.

    Used when VIS code detection fails or returns low confidence.
    Analyzes audio for sync timing patterns and suggests most likely SSTV mode.

    Returns:
        - Detected mode (if confidence >= 0.70)
        - Confidence score
        - Measured inter-pulse intervals
        - Expected interval for detected mode
        - Top 3 alternative mode suggestions
        - User-friendly suggestion message

    Raises:
        400 Bad Request: If neither session_id nor audio_file provided
        404 Not Found: If session_id not found
        500 Internal Server Error: If analysis fails

    """
    try:
        # Get audio samples
        audio_samples = None

        if request.session_id is not None:
            # Analyze audio from active decode session
            session = await session_manager.get_decode_session(request.session_id)

            if session is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "error": "SESSION_NOT_FOUND",
                        "message": f"Can't find decode session {request.session_id}",
                    },
                )

            # The session's RXManager keeps a rolling raw-audio window for
            # exactly this. Until 2026-08-08 this branch was a stub that
            # asked the user to upload a file instead.
            audio_samples = dsp_manager.get_session_audio(request.session_id)
            if audio_samples is None or len(audio_samples) < 48000 * 2:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "NOT_ENOUGH_AUDIO",
                        "message": (
                            "I haven't heard enough audio on that session yet "
                            "to analyze the timing."
                        ),
                        "suggested_action": "Give it a few seconds of signal and try again.",
                    },
                )

        elif request.audio_file is not None:
            # Analyze audio from file
            from pathlib import Path

            audio_path = Path(request.audio_file)

            if not audio_path.exists():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "error": "AUDIO_FILE_NOT_FOUND",
                        "message": f"Audio file not found: {request.audio_file}",
                    },
                )

            # Load audio file
            import soundfile as sf

            try:
                # Off the event loop: this can be a 60 s file, and the loop
                # also services live decode and WebSocket traffic.
                loop = asyncio.get_event_loop()
                audio_data, sample_rate = await loop.run_in_executor(
                    None, sf.read, audio_path
                )

                if len(audio_data.shape) == 1:
                    audio_samples = audio_data
                else:
                    # Convert to mono by averaging channels
                    audio_samples = audio_data.mean(axis=1)

            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={
                        "error": "AUDIO_LOAD_ERROR",
                        "message": f"Failed to load audio file: {e!s}",
                    },
                ) from e
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "INVALID_REQUEST",
                    "message": "Either session_id or audio_file must be provided",
                },
            )

        # Perform mode detection off-loop (Goertzel over the whole clip).
        loop = asyncio.get_event_loop()
        detection_result = await loop.run_in_executor(
            None,
            lambda: detect_mode_from_sync_timing(
                audio_stream=audio_samples,
                sample_rate=sample_rate if request.audio_file else 48000,
                duration_sec=request.duration_sec,
                min_samples=10,
            ),
        )

        # Build response
        if detection_result is None:
            # Detection failed (not enough sync pulses or too much noise)
            return ModeDetectionResponse(
                mode=None,
                confidence=0.0,
                measured_intervals=[],
                expected_interval=None,
                fallback_modes=[],
                suggestion_message="I'm having trouble reading this signal. "
                "You'll need to choose the mode manually.",
            )

        # Get top 3 fallback modes for low confidence (also off-loop)
        top_candidates = await loop.run_in_executor(
            None,
            lambda: get_top_mode_candidates(
                audio_stream=audio_samples,
                sample_rate=sample_rate if request.audio_file else 48000,
                duration_sec=request.duration_sec,
                top_n=3,
            ),
        )

        fallback_modes = [
            {
                "mode": mode_name,
                "confidence": float(confidence),
            }
            for mode_name, confidence in top_candidates
        ]

        # Generate suggestion message
        suggestion = get_suggestion_message(
            mode=detection_result.mode,
            confidence=detection_result.confidence,
        )

        # Return detection result
        return ModeDetectionResponse(
            mode=detection_result.mode,
            confidence=detection_result.confidence,
            measured_intervals=detection_result.measured_intervals,
            expected_interval=detection_result.expected_interval,
            fallback_modes=fallback_modes,
            suggestion_message=suggestion,
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log error and return 500
        logger.error("Mode detection error: %s", e, exc_info=True)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "MODE_DETECTION_ERROR",
                "message": f"Mode detection failed: {e!s}",
            },
        ) from e


@router.post("/start", response_model=DecodeStartResponse, status_code=status.HTTP_201_CREATED)
async def start_decode(
    request: DecodeStartRequest, http_request: Request
) -> DecodeStartResponse:
    """Start a new decode session.

    Creates a listening session that waits for SSTV signals. The session
    will auto-detect the SSTV mode from VIS code (if enabled) or use the
    specified mode.

    Returns:
        DecodeStartResponse with session ID and WebSocket URL for real-time updates.

    Raises:
        409 Conflict: If another decode/transmit session is already active (half-duplex)

    """
    # Gate on the modes that actually have decoders. Without this, a forced
    # unsupported mode returned 201 and the session silently died inside the
    # background task.
    if request.mode and request.mode.value not in SUPPORTED_DECODE_MODES:
        supported = ", ".join(sorted(SUPPORTED_DECODE_MODES))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "UNSUPPORTED_MODE",
                "message": (
                    f"I can't decode {request.mode.value} yet -- "
                    f"I only have decoders for {supported}."
                ),
                "suggested_action": f"Pick one of: {supported}, or omit mode to auto-detect.",
            },
        )

    session = None
    try:
        # Create session with request metadata
        metadata = {
            "mode": request.mode.value if request.mode else None,
            "auto_detect": request.auto_detect,
            "timeout_seconds": request.timeout_seconds,
            "save_image": request.save_image,
            "callsign": request.callsign,
        }

        session = await session_manager.create_decode_session(metadata=metadata)

        # Start real DSP decode operation
        await dsp_manager.start_decode(
            session_id=session.session_id,
            mode=request.mode.value if request.mode else None,
            auto_detect=request.auto_detect,
            timeout_seconds=float(request.timeout_seconds or 120.0),
            save_image=request.save_image,
            callsign=request.callsign,
            device_id=request.device_id,
        )

        # Build WebSocket URL
        ws_url = _ws_url(http_request, f"/api/v1/ws/decode/{session.session_id}")

        return DecodeStartResponse(
            session_id=session.session_id,
            state=DecodeState.LISTENING,
            websocket_url=ws_url,
            started_at=session.created_at,
        )

    except ValueError as e:
        # Unknown audio device (or other rejected input) from dsp_manager.
        if session is not None:
            await session_manager.update_decode_state(
                session.session_id,
                DecodeState.FAILED,
                {"error": str(e)},
            )
            await dsp_manager.stop_decode(session.session_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "INVALID_REQUEST",
                "message": str(e),
                "suggested_action": "Check GET /devices/audio for valid device IDs.",
            },
        ) from e
    except RuntimeError as e:
        if session is not None:
            # Mark FAILED first so the half-duplex lock is released even if
            # DSP teardown itself raises.
            await session_manager.update_decode_state(
                session.session_id,
                DecodeState.FAILED,
                {"error": str(e)},
            )
            await dsp_manager.stop_decode(session.session_id)
        # Half-duplex constraint violated
        if "already active" in str(e) or "half-duplex" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "SESSION_CONFLICT",
                    "message": str(e),
                    "suggested_action": "Stop the active session before starting a new one",
                },
            ) from e
        raise
    except Exception as e:
        if session is not None:
            # Mark FAILED first so the half-duplex lock is released even if
            # DSP teardown itself raises.
            await session_manager.update_decode_state(
                session.session_id,
                DecodeState.FAILED,
                {"error": str(e)},
            )
            await dsp_manager.stop_decode(session.session_id)
        raise


@router.get("/status/{session_id}", response_model=DecodeStatusResponse)
async def get_decode_status(session_id: UUID) -> DecodeStatusResponse:
    """Get the current status of a decode session.

    Returns detailed progress information including:
    - Current state (listening, decoding, completed, etc.)
    - Detected SSTV mode and confidence
    - Progress percentage and scanlines received
    - Signal quality metrics (SNR, frequency offset)

    Raises:
        404 Not Found: If session doesn't exist

    """
    session = await session_manager.get_decode_session(session_id)

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "SESSION_NOT_FOUND",
                "message": f"Can't find decode session {session_id}",
                "suggested_action": "Check the session ID or start a new session",
            },
        )

    # Extract metadata
    metadata = session.metadata
    mode_str = metadata.get("mode")
    mode = None
    if mode_str:
        from sstv_core.api.models import SSTVMode
        try:
            mode = SSTVMode(mode_str)
        except ValueError:
            pass

    return DecodeStatusResponse(
        session_id=session.session_id,
        state=DecodeState(session.state),
        mode=mode,
        mode_confidence=metadata.get("mode_confidence"),
        progress_percent=metadata.get("progress_percent", 0.0),
        scanlines_received=metadata.get("scanlines_received", 0),
        snr_db=metadata.get("snr_db"),
        frequency_offset_hz=metadata.get("frequency_offset_hz"),
        image_id=metadata.get("image_id"),
        error=metadata.get("error"),
        started_at=session.created_at,
        completed_at=metadata.get("completed_at"),
    )


@router.post("/stop/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def stop_decode(session_id: UUID) -> None:
    """Stop an active decode session.

    Gracefully stops listening for SSTV signals. If a decode is in progress,
    the partial image will be discarded.

    Raises:
        404 Not Found: If session doesn't exist
        409 Conflict: If session is already in a terminal state

    """
    session = await session_manager.get_decode_session(session_id)

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "SESSION_NOT_FOUND",
                "message": f"Can't find decode session {session_id}",
                "suggested_action": "Check the session ID",
            },
        )

    # Check if already in terminal state
    if session.is_terminal_state():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "SESSION_ALREADY_STOPPED",
                "message": f"Session is already in state '{session.state}'",
                "suggested_action": "No action needed - session already stopped",
            },
        )

    await dsp_manager.stop_decode(session_id)
    try:
        await session_manager.stop_decode_session(session_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "SESSION_NOT_FOUND",
                "message": str(e),
            },
        ) from e


def _ws_url(request: Request, path: str) -> str:
    """WebSocket URL for the host the client actually reached us on.

    Hardcoding ws://localhost:8000 broke any client not on the same
    machine with the default port.
    """
    scheme = "wss" if request.url.scheme == "https" else "ws"
    return f"{scheme}://{request.url.netloc}{path}"
