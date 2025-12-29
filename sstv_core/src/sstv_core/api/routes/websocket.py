"""
WebSocket endpoints for real-time SSTV events.

Handles:
- ws://localhost:8000/api/v1/ws/decode/{session_id} - Decode progress events
- ws://localhost:8000/api/v1/ws/transmit/{tx_id} - Transmit progress events
"""

from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from sstv_core.api.websocket_manager import websocket_manager
from sstv_core.api.session_manager import session_manager


router = APIRouter()


@router.websocket("/ws/decode/{session_id}")
async def decode_websocket(websocket: WebSocket, session_id: UUID):
    """
    WebSocket endpoint for decode session events.

    Clients connect to receive real-time updates during SSTV decoding:
    - vis_detected: VIS code detected with mode and confidence
    - scanline_update: Scanline decode progress
    - decode_complete: Final image with quality metrics
    - error: Decode errors

    Buffered events are sent on connection for catch-up after disconnect.

    Protocol:
        1. Client connects
        2. Server sends buffered events (if any)
        3. Server streams real-time events as they occur
        4. Connection persists until client disconnects or session completes
    """
    # Verify session exists
    session = await session_manager.get_decode_session(session_id)
    if session is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Accept connection
    await websocket.accept()

    # Register connection
    connection = await websocket_manager.connect(websocket, session_id)

    try:
        # Send buffered events for catch-up
        await websocket_manager.send_buffered_events(connection)

        # Send current session state
        await connection.send_event({
            "event_type": "session_state",
            "session_id": str(session_id),
            "state": session.state,
            "metadata": session.metadata,
            "timestamp": session.last_activity.isoformat(),
        })

        # Keep connection alive and receive client pings
        while True:
            # Wait for client message (usually just pings)
            data = await websocket.receive_text()

            # Echo pings for keepalive
            if data == "ping":
                await websocket.send_text("pong")

    except WebSocketDisconnect:
        # Client disconnected - unregister but keep buffer
        await websocket_manager.disconnect(connection)


@router.websocket("/ws/transmit/{tx_id}")
async def transmit_websocket(websocket: WebSocket, tx_id: UUID):
    """
    WebSocket endpoint for transmit session events.

    Clients connect to receive real-time updates during SSTV transmission:
    - ptt_engaged: PTT activated
    - transmit_start: Audio transmission started
    - scanline_update: Scanline transmit progress
    - transmit_complete: Transmission finished successfully
    - error: Transmission errors

    Buffered events are sent on connection for catch-up after disconnect.

    Protocol:
        1. Client connects
        2. Server sends buffered events (if any)
        3. Server streams real-time events as they occur
        4. Connection persists until client disconnects or session completes
    """
    # Verify session exists
    session = await session_manager.get_transmit_session(tx_id)
    if session is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Accept connection
    await websocket.accept()

    # Register connection
    connection = await websocket_manager.connect(websocket, tx_id)

    try:
        # Send buffered events for catch-up
        await websocket_manager.send_buffered_events(connection)

        # Send current session state
        await connection.send_event({
            "event_type": "session_state",
            "tx_id": str(tx_id),
            "state": session.state,
            "metadata": session.metadata,
            "timestamp": session.last_activity.isoformat(),
        })

        # Keep connection alive and receive client pings
        while True:
            # Wait for client message (usually just pings)
            data = await websocket.receive_text()

            # Echo pings for keepalive
            if data == "ping":
                await websocket.send_text("pong")

    except WebSocketDisconnect:
        # Client disconnected - unregister but keep buffer
        await websocket_manager.disconnect(connection)
