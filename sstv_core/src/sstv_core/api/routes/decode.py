"""
Decode endpoints for SSTV reception.

Handles:
- POST /decode/start - Start listening for SSTV signal
- GET /decode/status/{session_id} - Get decode progress
- POST /decode/stop/{session_id} - Stop active decode session
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from sstv_core.api.models import (
    DecodeStartRequest,
    DecodeStartResponse,
    DecodeStatusResponse,
    DecodeState,
)
from sstv_core.api.dsp_manager import dsp_manager
from sstv_core.api.session_manager import session_manager


router = APIRouter(prefix="/decode", tags=["decode"])


@router.post("/start", response_model=DecodeStartResponse, status_code=status.HTTP_201_CREATED)
async def start_decode(request: DecodeStartRequest) -> DecodeStartResponse:
    """
    Start a new decode session.

    Creates a listening session that waits for SSTV signals. The session
    will auto-detect the SSTV mode from VIS code (if enabled) or use the
    specified mode.

    Returns:
        DecodeStartResponse with session ID and WebSocket URL for real-time updates.

    Raises:
        409 Conflict: If another decode/transmit session is already active (half-duplex)
    """
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
        ws_url = f"ws://localhost:8000/api/v1/ws/decode/{session.session_id}"

        return DecodeStartResponse(
            session_id=session.session_id,
            state=DecodeState.LISTENING,
            websocket_url=ws_url,
            started_at=session.created_at,
        )

    except RuntimeError as e:
        # Half-duplex constraint violated
        if "already active" in str(e) or "half-duplex" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "SESSION_CONFLICT",
                    "message": str(e),
                    "suggested_action": "Stop the active session before starting a new one",
                },
            )
        raise


@router.get("/status/{session_id}", response_model=DecodeStatusResponse)
async def get_decode_status(session_id: UUID) -> DecodeStatusResponse:
    """
    Get the current status of a decode session.

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
    """
    Stop an active decode session.

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
        )
