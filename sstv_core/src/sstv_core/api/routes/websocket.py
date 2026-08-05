"""WebSocket endpoints for real-time SSTV events.

Handles:
- ws://localhost:8000/api/v1/ws/decode/{session_id} - Decode progress events
- ws://localhost:8000/api/v1/ws/transmit/{tx_id} - Transmit progress events

Events emitted:
- vis_detected: VIS code detected with mode and confidence
- scanline_update: Scanline decoded/transmitted with progress
- decode_complete: Decode finished with image path
- tx_progress: Transmission progress with time remaining
- tx_complete: Transmission finished
- error: Operation error occurred
- session_resume: Client reconnected (includes buffered events)
"""

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from sstv_core.api.session_manager import session_manager
from sstv_core.api.websocket_manager import websocket_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/decode/{session_id}")
async def decode_websocket(websocket: WebSocket, session_id: UUID):
    """WebSocket endpoint for decode session real-time updates.

    Clients connect to receive live events during SSTV decoding:
    - vis_detected: VIS code detected with mode and confidence
    - scanline_update: Scanline decode progress (every 5 lines)
    - decode_complete: Final image with quality metrics
    - error: Decode errors

    Buffered events are sent on connection for catch-up after disconnect.
    The connection supports reconnection with event replay within 5 minutes.

    Protocol:
        1. Client connects
        2. Server validates session exists
        3. Server sends buffered events (if reconnecting)
        4. Server sends session_resume event with current state
        5. Server streams real-time events as they occur
        6. Connection persists until client disconnects or session completes
    """
    logger.info("WebSocket connection requested for decode session %s", session_id)

    # Verify session exists
    session = await session_manager.get_decode_session(session_id)
    if session is None:
        logger.warning("WebSocket rejected: session %s not found", session_id)
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason=f"Decode session {session_id} not found"
        )
        return

    # Accept connection
    await websocket.accept()
    logger.info("WebSocket accepted for decode session %s", session_id)

    # Register connection with manager
    connection = await websocket_manager.connect(websocket, session_id)

    try:
        # Send buffered events (catch-up for reconnections)
        buffered_count = await websocket_manager.send_buffered_events(connection)
        if buffered_count > 0:
            logger.info(
                "Sent %d buffered events to reconnected client (session %s)",
                buffered_count,
                session_id
            )

        # Send session resume event with current state
        await connection.send_event({
            "event": "session_resume",
            "state": session.state,
            "metadata": session.metadata,
            "timestamp": session.last_activity.isoformat(),
        })

        # Keep connection alive and handle client messages
        while True:
            try:
                # Wait for client messages (ping/pong for keepalive)
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0  # 30-second timeout
                )

                # Handle ping (respond with pong)
                if data == "ping":
                    await connection.send_event({"event": "pong"})
                    logger.debug("Pong sent to session %s", session_id)

            except asyncio.TimeoutError:
                # No message received in 30s, send keepalive ping
                try:
                    await connection.send_event({"event": "keepalive"})
                except Exception:
                    # Connection dead, break out
                    logger.warning("Keepalive failed for session %s, closing", session_id)
                    break

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for session %s", session_id)

    except Exception as e:
        logger.error(
            "WebSocket error for session %s: %s",
            session_id,
            e,
            exc_info=True
        )

    finally:
        # Unregister connection
        await websocket_manager.disconnect(connection)
        logger.info("WebSocket cleaned up for session %s", session_id)


@router.websocket("/ws/transmit/{tx_id}")
async def transmit_websocket(websocket: WebSocket, tx_id: UUID):
    """WebSocket endpoint for transmit session real-time updates.

    Clients connect to receive live events during SSTV transmission:
    - ptt_engaged: PTT activated
    - transmit_start: Audio transmission started
    - tx_progress: Transmission progress (every 10%)
    - tx_complete: Transmission finished successfully
    - error: Transmission errors

    Buffered events are sent on connection for catch-up after disconnect.
    The connection supports reconnection with event replay within 5 minutes.

    Protocol:
        1. Client connects
        2. Server validates session exists
        3. Server sends buffered events (if reconnecting)
        4. Server sends session_resume event with current state
        5. Server streams real-time events as they occur
        6. Connection persists until client disconnects or session completes
    """
    logger.info("WebSocket connection requested for transmit session %s", tx_id)

    # Verify session exists
    session = await session_manager.get_transmit_session(tx_id)
    if session is None:
        logger.warning("WebSocket rejected: transmit session %s not found", tx_id)
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason=f"Transmit session {tx_id} not found"
        )
        return

    # Accept connection
    await websocket.accept()
    logger.info("WebSocket accepted for transmit session %s", tx_id)

    # Register connection with manager
    connection = await websocket_manager.connect(websocket, tx_id)

    try:
        # Send buffered events (catch-up for reconnections)
        buffered_count = await websocket_manager.send_buffered_events(connection)
        if buffered_count > 0:
            logger.info(
                "Sent %d buffered events to reconnected client (transmit %s)",
                buffered_count,
                tx_id
            )

        # Send session resume event with current state
        await connection.send_event({
            "event": "session_resume",
            "state": session.state,
            "metadata": session.metadata,
            "timestamp": session.last_activity.isoformat(),
        })

        # Keep connection alive and handle client messages
        while True:
            try:
                # Wait for client messages (ping/pong for keepalive)
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0  # 30-second timeout
                )

                # Handle ping (respond with pong)
                if data == "ping":
                    await connection.send_event({"event": "pong"})
                    logger.debug("Pong sent to transmit session %s", tx_id)

            except asyncio.TimeoutError:
                # No message received in 30s, send keepalive ping
                try:
                    await connection.send_event({"event": "keepalive"})
                except Exception:
                    # Connection dead, break out
                    logger.warning("Keepalive failed for transmit %s, closing", tx_id)
                    break

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for transmit session %s", tx_id)

    except Exception as e:
        logger.error(
            "WebSocket error for transmit session %s: %s",
            tx_id,
            e,
            exc_info=True
        )

    finally:
        # Unregister connection
        await websocket_manager.disconnect(connection)
        logger.info("WebSocket cleaned up for transmit session %s", tx_id)
