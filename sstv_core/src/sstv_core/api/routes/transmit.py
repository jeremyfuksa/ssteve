"""
Transmit endpoints for SSTV transmission.

Handles:
- POST /transmit - Start SSTV transmission
- GET /transmit/status/{tx_id} - Get transmission progress
- POST /transmit/cancel/{tx_id} - Cancel active transmission
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from sstv_core.api.models import (
    SSTVMode,
    TransmitRequest,
    TransmitResponse,
    TransmitStatusResponse,
    TransmitState,
)
from sstv_core.api.dsp_manager import dsp_manager
from sstv_core.api.session_manager import session_manager


router = APIRouter(prefix="/transmit", tags=["transmit"])


@router.post("", response_model=TransmitResponse, status_code=status.HTTP_201_CREATED)
async def start_transmit(request: TransmitRequest) -> TransmitResponse:
    """
    Start a new SSTV transmission.

    Encodes the image, engages PTT (if configured), and transmits the SSTV signal.
    The transmission duration depends on the SSTV mode selected.

    Returns:
        TransmitResponse with transmission ID and WebSocket URL for real-time updates.

    Raises:
        409 Conflict: If another decode/transmit session is already active (half-duplex)
        404 Not Found: If image file doesn't exist
        400 Bad Request: If image format is unsupported or invalid
    """
    session = None
    try:
        # Create session with request metadata
        metadata = {
            "image_path": request.image_path,
            "mode": request.mode.value,
            "callsign": request.callsign,
            "include_vis": request.include_vis,
            "vox_enabled": request.vox_enabled,
        }

        session = await session_manager.create_transmit_session(metadata=metadata)

        # Start real DSP transmit operation
        await dsp_manager.start_transmit(
            session_id=session.session_id,
            image_path=request.image_path,
            mode=request.mode.value,
            device_id=request.device_id,
            vox_enabled=request.vox_enabled,
            serial_port=request.serial_port,
        )

        # Build WebSocket URL
        ws_url = f"ws://localhost:8000/api/v1/ws/transmit/{session.session_id}"

        # Estimate transmission duration based on mode
        # TODO: Calculate actual duration from mode timing
        estimated_duration = _estimate_duration(request.mode)

        return TransmitResponse(
            tx_id=session.session_id,
            state=TransmitState.PENDING,
            websocket_url=ws_url,
            estimated_duration_seconds=estimated_duration,
            started_at=session.created_at,
        )

    except RuntimeError as e:
        if session is not None:
            # Mark FAILED first so the half-duplex lock is released even if
            # DSP teardown itself raises.
            await session_manager.update_transmit_state(
                session.session_id,
                TransmitState.FAILED,
                {"error": str(e)},
            )
            await dsp_manager.stop_transmit(session.session_id)
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
    except Exception as e:
        if session is not None:
            # Mark FAILED first so the half-duplex lock is released even if
            # DSP teardown itself raises.
            await session_manager.update_transmit_state(
                session.session_id,
                TransmitState.FAILED,
                {"error": str(e)},
            )
            await dsp_manager.stop_transmit(session.session_id)
        raise


@router.get("/status/{tx_id}", response_model=TransmitStatusResponse)
async def get_transmit_status(tx_id: UUID) -> TransmitStatusResponse:
    """
    Get the current status of a transmission.

    Returns detailed progress information including:
    - Current state (pending, ptt_engaged, transmitting, completed, etc.)
    - Progress percentage and scanlines transmitted
    - Elapsed time and estimated total duration

    Raises:
        404 Not Found: If transmission doesn't exist
    """
    session = await session_manager.get_transmit_session(tx_id)

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "SESSION_NOT_FOUND",
                "message": f"Can't find transmission {tx_id}",
                "suggested_action": "Check the transmission ID",
            },
        )

    # Extract metadata
    metadata = session.metadata
    mode_str = metadata.get("mode")
    mode = None
    if mode_str:
        try:
            mode = SSTVMode(mode_str)
        except ValueError:
            pass

    # If mode couldn't be determined, use a default
    if mode is None:
        mode = SSTVMode.MARTIN_M1

    estimated_duration = _estimate_duration(mode)

    return TransmitStatusResponse(
        tx_id=session.session_id,
        state=TransmitState(session.state),
        mode=mode,
        progress_percent=metadata.get("progress_percent", 0.0),
        scanlines_transmitted=metadata.get("scanlines_transmitted", 0),
        elapsed_seconds=metadata.get("elapsed_seconds", 0.0),
        estimated_duration_seconds=estimated_duration,
        image_id=metadata.get("image_id"),
        error=metadata.get("error"),
        started_at=session.created_at,
        completed_at=metadata.get("completed_at"),
    )


@router.post("/cancel/{tx_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_transmit(tx_id: UUID) -> None:
    """
    Cancel an active transmission.

    Releases PTT and stops transmitting. The partial transmission will be aborted.

    Raises:
        404 Not Found: If transmission doesn't exist
        409 Conflict: If transmission is already in a terminal state
    """
    session = await session_manager.get_transmit_session(tx_id)

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "SESSION_NOT_FOUND",
                "message": f"Can't find transmission {tx_id}",
                "suggested_action": "Check the transmission ID",
            },
        )

    # Check if already in terminal state
    if session.is_terminal_state():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "SESSION_ALREADY_STOPPED",
                "message": f"Transmission is already in state '{session.state}'",
                "suggested_action": "No action needed - transmission already stopped",
            },
        )

    await dsp_manager.stop_transmit(tx_id)
    try:
        await session_manager.cancel_transmit_session(tx_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "SESSION_NOT_FOUND",
                "message": str(e),
            },
        )


def _estimate_duration(mode) -> float:
    """Estimate transmission duration for a given mode (in seconds)."""
    # Approximate durations for common modes (including VIS and sync overhead)
    from sstv_core.api.models import SSTVMode

    durations = {
        SSTVMode.MARTIN_M1: 114.0,
        SSTVMode.MARTIN_M2: 58.0,
        SSTVMode.SCOTTIE_S1: 110.0,
        SSTVMode.SCOTTIE_S2: 71.0,
        SSTVMode.SCOTTIE_DX: 269.0,
        SSTVMode.ROBOT_36: 36.0,
        SSTVMode.ROBOT_72: 72.0,
        SSTVMode.PD_90: 90.0,
        SSTVMode.PD_120: 120.0,
        SSTVMode.PD_180: 180.0,
        SSTVMode.PD_240: 240.0,
        SSTVMode.WRAASE_SC2_180: 180.0,
    }

    return durations.get(mode, 60.0)  # Default fallback
