# API-to-DSP Wiring Implementation Plan

**Status:** Ready for implementation
**Priority:** 🔴 CRITICAL - Blocks all real decode/transmit functionality
**Estimated Effort:** 1-2 weeks (40-60 hours)
**Last Updated:** 2026-01-15

---

## Executive Summary

The SSTeVe backend has complete DSP modules (`rx_manager.py`, `tx_manager.py`) and a scaffolded API layer (`decode.py`, `transmit.py`), but they are **not connected**. API routes currently trigger `operation_manager.py` which emits synthetic events for testing. This plan details how to wire the real DSP modules to the API endpoints so actual audio processing occurs.

### Current State

```
User → POST /decode/start → session_manager.create_session()
                          → operation_manager.start_decode() ← SIMULATION
                          ❌ rx_manager.receive() ← NOT CALLED
```

### Target State

```
User → POST /decode/start → session_manager.create_session()
                          → rx_manager.receive() ← REAL DSP
                          → WebSocket events (VIS, scanlines, complete)
                          → Database save
```

---

## Architecture Overview

### Data Flow: Decode Pipeline

```
┌─────────────┐
│ Client (UI) │
└──────┬──────┘
       │ HTTP POST /decode/start
       ▼
┌──────────────────────┐
│ api/routes/decode.py │
│                      │
│ 1. Create session    │
│ 2. Initialize RX mgr │
│ 3. Start decode task │
└──────┬───────────────┘
       │ asyncio.create_task()
       ▼
┌─────────────────────────────┐
│ decode/rx_manager.py        │
│                             │
│ 1. Start audio input stream │──────┐
│ 2. Detect VIS code          │      │
│ 3. Select decoder           │      │
│ 4. Decode scanlines         │      │
│ 5. Save image               │      │
└─────────┬───────────────────┘      │
          │                          │
          │ Progress callbacks       │ Audio samples
          ▼                          │
┌──────────────────────────┐         │
│ Progress Handler         │         │
│                          │         │
│ 1. Update session state  │    ┌────▼────────────┐
│ 2. Emit WebSocket events │    │ Audio Hardware  │
│ 3. Update database       │    │ (sounddevice)   │
└──────────────────────────┘    └─────────────────┘
          │
          ▼
┌──────────────────────────┐
│ WebSocket Manager        │
│ → vis_detected event     │
│ → scanline_update event  │
│ → decode_complete event  │
└──────────────────────────┘
          │
          ▼
┌──────────────┐
│ Client (UI)  │
│ Updates UI   │
└──────────────┘
```

### Data Flow: Transmit Pipeline

```
┌─────────────┐
│ Client (UI) │
└──────┬──────┘
       │ HTTP POST /transmit
       ▼
┌──────────────────────────┐
│ api/routes/transmit.py   │
│                          │
│ 1. Create session        │
│ 2. Initialize TX mgr     │
│ 3. Start transmit task   │
└──────┬───────────────────┘
       │ asyncio.create_task()
       ▼
┌──────────────────────────────┐
│ encode/tx_manager.py         │
│                              │
│ 1. Load & preprocess image   │
│ 2. Generate VIS + audio      │
│ 3. Key PTT                   │
│ 4. Start audio output stream │──────┐
│ 5. Transmit audio            │      │
│ 6. Unkey PTT                 │      │
└─────────┬────────────────────┘      │
          │                           │
          │ Progress callbacks        │ Audio samples
          ▼                           │
┌──────────────────────────┐          │
│ Progress Handler         │          │
│                          │     ┌────▼────────────┐
│ 1. Update session state  │     │ Audio Hardware  │
│ 2. Emit WebSocket events │     │ (sounddevice)   │
└──────────────────────────┘     └─────────────────┘
          │
          ▼
┌──────────────────────────┐
│ WebSocket Manager        │
│ → tx_progress event      │
│ → tx_complete event      │
└──────────────────────────┘
          │
          ▼
┌──────────────┐
│ Client (UI)  │
│ Updates UI   │
└──────────────┘
```

---

## Implementation Tasks

### Phase 1: Core Infrastructure (4-6 hours)

#### Task 1.1: Create RX/TX Manager Registry

**File:** `sstv_core/src/sstv_core/api/dsp_manager.py` (NEW FILE)

**Purpose:** Central registry for managing DSP module instances and their lifecycles.

**Implementation:**

```python
"""DSP manager for coordinating RX/TX instances with API sessions."""

import asyncio
from typing import Dict, Optional
from uuid import UUID
from pathlib import Path

from sstv_core.audio.stream_manager import AudioStreamManager
from sstv_core.audio.device_manager import AudioDeviceManager
from sstv_core.audio.ptt_controller import PTTController, PTTMethod
from sstv_core.decode.rx_manager import RXManager, RXProgress
from sstv_core.encode.tx_manager import TXManager, TXProgress
from sstv_core.api.websocket_manager import websocket_manager
from sstv_core.api.session_manager import session_manager
from sstv_core.api.models import DecodeState, TransmitState


class DSPManager:
    """Manages DSP module lifecycle and wiring to API sessions."""

    def __init__(self):
        # Shared audio infrastructure
        self._device_manager = AudioDeviceManager()
        self._stream_manager = AudioStreamManager()

        # Active RX/TX instances
        self._rx_managers: Dict[UUID, RXManager] = {}
        self._tx_managers: Dict[UUID, TXManager] = {}

        # Background tasks
        self._decode_tasks: Dict[UUID, asyncio.Task] = {}
        self._transmit_tasks: Dict[UUID, asyncio.Task] = {}

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
        """Start real decode operation for a session."""

        # Create RX manager
        rx_mgr = RXManager(
            stream_manager=self._stream_manager,
            sample_rate=48000,
            save_directory=Path.home() / "sstv_images",
        )

        # Wire progress callback
        def on_progress(progress: RXProgress):
            asyncio.create_task(self._handle_rx_progress(session_id, progress))

        rx_mgr.set_progress_callback(on_progress)
        self._rx_managers[session_id] = rx_mgr

        # Parse device ID
        device_index = int(device_id) if device_id else None

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

    async def stop_decode(self, session_id: UUID) -> None:
        """Stop active decode operation."""
        rx_mgr = self._rx_managers.get(session_id)
        if rx_mgr:
            await rx_mgr.cancel()

        # Cancel task
        task = self._decode_tasks.get(session_id)
        if task and not task.done():
            task.cancel()

    async def start_transmit(
        self,
        session_id: UUID,
        image_path: str,
        mode: str,
        device_id: Optional[str],
        vox_enabled: bool,
        serial_port: Optional[str],
    ) -> None:
        """Start real transmit operation for a session."""

        # Create PTT controller
        if serial_port:
            ptt = PTTController(method=PTTMethod.SERIAL, port=serial_port)
        elif vox_enabled:
            ptt = PTTController(method=PTTMethod.VOX)
        else:
            ptt = PTTController(method=PTTMethod.NONE)

        # Create TX manager
        tx_mgr = TXManager(
            stream_manager=self._stream_manager,
            ptt_controller=ptt,
            sample_rate=48000,
        )

        # Wire progress callback
        def on_progress(progress: TXProgress):
            asyncio.create_task(self._handle_tx_progress(session_id, progress))

        tx_mgr.set_progress_callback(on_progress)
        self._tx_managers[session_id] = tx_mgr

        # Parse device ID
        device_index = int(device_id) if device_id else None

        # Convert mode string to enum
        from sstv_core.encode.vis_generator import SSTVMode
        sstv_mode = getattr(SSTVMode, mode.upper().replace(" ", "_"))

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
            lambda t: asyncio.create_task(self._handle_transmit_complete(session_id, t))
        )

    async def stop_transmit(self, session_id: UUID) -> None:
        """Stop active transmit operation."""
        tx_mgr = self._tx_managers.get(session_id)
        if tx_mgr:
            await tx_mgr.cancel()

        # Cancel task
        task = self._transmit_tasks.get(session_id)
        if task and not task.done():
            task.cancel()

    async def _handle_rx_progress(self, session_id: UUID, progress: RXProgress) -> None:
        """Handle decode progress updates and emit WebSocket events."""

        # Update session metadata
        metadata = {
            "mode": progress.mode,
            "mode_confidence": progress.mode_confidence,
            "progress_percent": progress.percent_complete,
            "scanlines_received": progress.current_line,
            "signal_quality": progress.signal_quality,
        }

        # Map RX state to API state
        from sstv_core.decode.rx_manager import RXState
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

        await session_manager.update_decode_state(session_id, api_state, metadata)

        # Emit WebSocket events
        if progress.state == RXState.VIS_DETECTED:
            await websocket_manager.broadcast(session_id, {
                "event": "vis_detected",
                "mode": progress.mode,
                "confidence": progress.mode_confidence,
                "timestamp": progress.elapsed_sec,
            })

        elif progress.state == RXState.DECODING:
            await websocket_manager.broadcast(session_id, {
                "event": "scanline_update",
                "line": progress.current_line,
                "total": progress.total_lines,
                "progress": progress.percent_complete,
                "signal_quality": progress.signal_quality,
            })

    async def _handle_decode_complete(
        self, session_id: UUID, task: asyncio.Task
    ) -> None:
        """Handle decode completion or error."""

        try:
            result = task.result()  # Path to saved image or None

            if result:
                # Decode succeeded
                await session_manager.update_decode_state(
                    session_id,
                    DecodeState.COMPLETED,
                    {"filepath": str(result)},
                )

                await websocket_manager.broadcast(session_id, {
                    "event": "decode_complete",
                    "filepath": str(result),
                    "timestamp": 0,  # TODO: Add elapsed time
                })
            else:
                # Decode failed or cancelled
                await session_manager.update_decode_state(
                    session_id,
                    DecodeState.STOPPED,
                )

        except asyncio.CancelledError:
            await session_manager.update_decode_state(
                session_id,
                DecodeState.STOPPED,
            )

        except Exception as e:
            await session_manager.update_decode_state(
                session_id,
                DecodeState.FAILED,
                {"error": str(e)},
            )

            await websocket_manager.broadcast(session_id, {
                "event": "error",
                "error_code": "DECODE_ERROR",
                "message": str(e),
            })

        finally:
            # Cleanup
            self._rx_managers.pop(session_id, None)
            self._decode_tasks.pop(session_id, None)

    async def _handle_tx_progress(self, session_id: UUID, progress: TXProgress) -> None:
        """Handle transmit progress updates and emit WebSocket events."""

        # Update session metadata
        metadata = {
            "progress_percent": progress.percent_complete,
            "scanlines_transmitted": progress.current_line,
            "elapsed_seconds": progress.elapsed_sec,
        }

        # Map TX state to API state
        from sstv_core.encode.tx_manager import TXState
        state_map = {
            TXState.PREPARING: TransmitState.PENDING,
            TXState.KEYING: TransmitState.PTT_ENGAGED,
            TXState.TRANSMITTING: TransmitState.TRANSMITTING,
            TXState.UNKEYING: TransmitState.TRANSMITTING,
            TXState.COMPLETE: TransmitState.COMPLETED,
            TXState.ERROR: TransmitState.FAILED,
        }
        api_state = state_map.get(progress.state, TransmitState.PENDING)

        await session_manager.update_transmit_state(session_id, api_state, metadata)

        # Emit WebSocket events
        await websocket_manager.broadcast(session_id, {
            "event": "tx_progress",
            "progress": progress.percent_complete,
            "time_remaining_sec": progress.remaining_sec,
            "current_scanline": progress.current_line,
        })

    async def _handle_transmit_complete(
        self, session_id: UUID, task: asyncio.Task
    ) -> None:
        """Handle transmit completion or error."""

        try:
            success = task.result()  # Boolean

            if success:
                await session_manager.update_transmit_state(
                    session_id,
                    TransmitState.COMPLETED,
                )

                await websocket_manager.broadcast(session_id, {
                    "event": "tx_complete",
                    "timestamp": 0,  # TODO: Add elapsed time
                })
            else:
                await session_manager.update_transmit_state(
                    session_id,
                    TransmitState.FAILED,
                )

        except asyncio.CancelledError:
            await session_manager.update_transmit_state(
                session_id,
                TransmitState.CANCELLED,
            )

        except Exception as e:
            await session_manager.update_transmit_state(
                session_id,
                TransmitState.FAILED,
                {"error": str(e)},
            )

            await websocket_manager.broadcast(session_id, {
                "event": "error",
                "error_code": "TRANSMIT_ERROR",
                "message": str(e),
            })

        finally:
            # Cleanup
            self._tx_managers.pop(session_id, None)
            self._transmit_tasks.pop(session_id, None)


# Global singleton
dsp_manager = DSPManager()
```

**Acceptance Criteria:**
- ✅ DSPManager class created
- ✅ start_decode() wires RX manager to session
- ✅ start_transmit() wires TX manager to session
- ✅ Progress callbacks emit WebSocket events
- ✅ Completion handlers update session state
- ✅ Cleanup on task completion

---

#### Task 1.2: Modify Decode Endpoints to Use DSP Manager

**File:** `sstv_core/src/sstv_core/api/routes/decode.py`

**Changes:**

```python
# At top of file, replace operation_manager import:
# OLD:
from sstv_core.api.operation_manager import operation_manager
# NEW:
from sstv_core.api.dsp_manager import dsp_manager

# Remove this line:
RUN_BACKGROUND_OPERATIONS = os.environ.get("SSTVE_SIMULATE_OPERATIONS") == "1"

# In start_decode() function (line 58-59):
# OLD:
if RUN_BACKGROUND_OPERATIONS:
    operation_manager.start_decode(session)

# NEW:
await dsp_manager.start_decode(
    session_id=session.session_id,
    mode=request.mode.value if request.mode else None,
    auto_detect=request.auto_detect,
    timeout_seconds=request.timeout_seconds or 120.0,
    save_image=request.save_image,
    callsign=request.callsign,
    device_id=request.device_id,  # Add this to DecodeStartRequest model
)

# In stop_decode() function (line 173):
# OLD:
await operation_manager.stop_decode(session_id)

# NEW:
await dsp_manager.stop_decode(session_id)
```

**Model Changes (api/models.py):**

```python
# Add to DecodeStartRequest:
class DecodeStartRequest(BaseModel):
    mode: Optional[SSTVMode] = None
    auto_detect: bool = True
    timeout_seconds: Optional[float] = 120.0
    save_image: bool = True
    callsign: Optional[str] = None
    device_id: Optional[str] = None  # NEW: Audio input device ID
```

**Acceptance Criteria:**
- ✅ Decode routes call dsp_manager instead of operation_manager
- ✅ device_id parameter added to request model
- ✅ All decode parameters passed to DSP manager
- ✅ Tests updated to reflect real audio processing

---

#### Task 1.3: Modify Transmit Endpoints to Use DSP Manager

**File:** `sstv_core/src/sstv_core/api/routes/transmit.py`

**Changes:**

```python
# At top of file, replace operation_manager import:
# OLD:
from sstv_core.api.operation_manager import operation_manager
# NEW:
from sstv_core.api.dsp_manager import dsp_manager

# Remove this line:
RUN_BACKGROUND_OPERATIONS = os.environ.get("SSTVE_SIMULATE_OPERATIONS") == "1"

# In start_transmit() function (line 59-60):
# OLD:
if RUN_BACKGROUND_OPERATIONS:
    operation_manager.start_transmit(session)

# NEW:
await dsp_manager.start_transmit(
    session_id=session.session_id,
    image_path=request.image_path,
    mode=request.mode.value,
    device_id=request.device_id,  # Add to TransmitRequest
    vox_enabled=request.vox_enabled,
    serial_port=request.serial_port,  # Add to TransmitRequest
)

# In cancel_transmit() function (line 178):
# OLD:
await operation_manager.stop_transmit(tx_id)

# NEW:
await dsp_manager.stop_transmit(tx_id)
```

**Model Changes (api/models.py):**

```python
# Add to TransmitRequest:
class TransmitRequest(BaseModel):
    image_path: str
    mode: SSTVMode
    callsign: Optional[str] = None
    include_vis: bool = True
    vox_enabled: bool = False
    device_id: Optional[str] = None  # NEW: Audio output device ID
    serial_port: Optional[str] = None  # NEW: Serial port for PTT
```

**Acceptance Criteria:**
- ✅ Transmit routes call dsp_manager instead of operation_manager
- ✅ device_id and serial_port parameters added
- ✅ All transmit parameters passed to DSP manager
- ✅ Tests updated

---

### Phase 2: WebSocket Event Wiring (3-4 hours)

#### Task 2.1: Create WebSocket Routes

**File:** `sstv_core/src/sstv_core/api/routes/websocket.py` (EXISTS BUT EMPTY)

**Implementation:**

```python
"""WebSocket endpoints for real-time SSTV event streaming."""

from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from sstv_core.api.websocket_manager import websocket_manager
from sstv_core.api.session_manager import session_manager


router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/decode/{session_id}")
async def decode_websocket(websocket: WebSocket, session_id: UUID):
    """
    WebSocket endpoint for decode session events.

    Events emitted:
    - vis_detected: VIS code detected with mode and confidence
    - scanline_update: Scanline decoded with progress and quality
    - decode_complete: Decode finished with image path
    - error: Decode error occurred
    """
    # Verify session exists
    session = await session_manager.get_decode_session(session_id)
    if session is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Session not found")
        return

    # Accept connection
    await websocket.accept()

    # Register connection
    connection = await websocket_manager.connect(websocket, session_id)

    try:
        # Send buffered events (catch-up)
        await websocket_manager.send_buffered_events(connection)

        # Send session resume event with current state
        await connection.send_event({
            "event": "session_resume",
            "state": session.state,
            "metadata": session.metadata,
        })

        # Keep connection alive
        while True:
            # Wait for client messages (ping/pong)
            data = await websocket.receive_text()

            # Echo pong if ping received
            if data == "ping":
                await connection.send_event({"event": "pong"})

    except WebSocketDisconnect:
        # Client disconnected
        pass

    finally:
        # Unregister connection
        await websocket_manager.disconnect(connection)


@router.websocket("/transmit/{tx_id}")
async def transmit_websocket(websocket: WebSocket, tx_id: UUID):
    """
    WebSocket endpoint for transmit session events.

    Events emitted:
    - tx_progress: Transmission progress with scanline count
    - tx_complete: Transmission finished
    - error: Transmission error occurred
    """
    # Verify session exists
    session = await session_manager.get_transmit_session(tx_id)
    if session is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Session not found")
        return

    # Accept connection
    await websocket.accept()

    # Register connection
    connection = await websocket_manager.connect(websocket, tx_id)

    try:
        # Send buffered events (catch-up)
        await websocket_manager.send_buffered_events(connection)

        # Send session resume event
        await connection.send_event({
            "event": "session_resume",
            "state": session.state,
            "metadata": session.metadata,
        })

        # Keep connection alive
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await connection.send_event({"event": "pong"})

    except WebSocketDisconnect:
        pass

    finally:
        await websocket_manager.disconnect(connection)
```

**Acceptance Criteria:**
- ✅ /ws/decode/{session_id} endpoint implemented
- ✅ /ws/transmit/{tx_id} endpoint implemented
- ✅ Session validation before accepting connection
- ✅ Buffered events sent on reconnection
- ✅ session_resume event includes current state

---

#### Task 2.2: Register WebSocket Routes in Main App

**File:** `sstv_core/src/sstv_core/api/main.py`

**Changes:**

```python
# Add websocket router import:
from sstv_core.api.routes import decode, transmit, devices, config, images, websocket

# Register websocket routes:
app.include_router(websocket.router, prefix="/api/v1")
```

**Acceptance Criteria:**
- ✅ WebSocket routes registered in FastAPI app
- ✅ Can connect to ws://localhost:8000/api/v1/ws/decode/{id}
- ✅ Can connect to ws://localhost:8000/api/v1/ws/transmit/{id}

---

### Phase 3: Database Integration (2-3 hours)

#### Task 3.1: Wire Image Saver to Database

**Current State:** `image_saver.py` saves images but doesn't create database records.

**File:** `sstv_core/src/sstv_core/decode/image_saver.py`

**Changes Needed:**

```python
# Add database imports at top:
from sqlalchemy.orm import Session
from sstv_core.database.models import SSTVImage
from sstv_core.database.session import get_session  # New helper function

# Modify save_image() method:
def save_image(
    self,
    image: Image.Image,
    filename: str,
    metadata: Optional[Dict[str, Any]] = None,
    db_session: Optional[Session] = None,  # NEW parameter
) -> Path:
    """Save image to disk and database."""

    # Save to disk (existing code)
    filepath = self._save_directory / filename
    image.save(filepath, format="PNG", compress_level=6)

    # Save to database (NEW)
    if db_session is None:
        db_session = next(get_session())

    try:
        db_image = SSTVImage(
            filename=filename,
            filepath=str(filepath),
            timestamp=datetime.utcnow(),
            mode=metadata.get("mode") if metadata else None,
            callsign=metadata.get("callsign") if metadata else None,
            rx_quality_score=metadata.get("vis_confidence") if metadata else None,
            is_received=True,  # Decoded images are received
        )
        db_session.add(db_image)
        db_session.commit()

        logger.info("Image saved to database: ID=%d", db_image.id)

        return filepath, db_image.id  # Return both filepath and DB ID

    except Exception as e:
        logger.error("Failed to save image to database: %s", e)
        db_session.rollback()
        return filepath, None  # Return filepath even if DB save fails
```

**File:** `sstv_core/src/sstv_core/decode/rx_manager.py`

**Changes:**

```python
# In receive() method, Phase 5 (line 299-332), modify:
if save_image:
    # ... existing code to get image ...

    # Save with database integration
    saved_path, image_id = self._image_saver.save_image(
        image,
        filename=filename,
        metadata={
            "mode": detected_mode,
            "callsign": callsign,
            "timestamp": datetime.utcnow().isoformat(),
            "vis_confidence": vis_confidence,
        },
    )

    # Return image_id in progress callback
    self._emit_progress(
        detected_mode, vis_confidence, 100, total_lines, total_lines,
        elapsed, 0, "Decode complete!",
        image_id=image_id,  # NEW
    )
```

**Acceptance Criteria:**
- ✅ image_saver creates database records
- ✅ SSTVImage table populated on decode
- ✅ image_id returned in decode_complete event
- ✅ Database save failures don't crash decode

---

#### Task 3.2: Add Image ID to WebSocket Events

**File:** `sstv_core/src/sstv_core/api/dsp_manager.py`

**Changes:**

```python
# In _handle_decode_complete(), modify decode_complete event:
await websocket_manager.broadcast(session_id, {
    "event": "decode_complete",
    "image_id": metadata.get("image_id"),  # NEW: Include DB ID
    "filepath": str(result),
    "timestamp": elapsed_time,
})
```

**Acceptance Criteria:**
- ✅ decode_complete event includes image_id
- ✅ UI can fetch image metadata via GET /images/{id}

---

### Phase 4: Error Handling & Edge Cases (3-4 hours)

#### Task 4.1: Handle Audio Device Failures

**Scenarios to Handle:**
1. Device disconnected during decode/transmit
2. Device not found at session start
3. Device permissions denied (Linux/macOS)
4. Device already in use by another application

**File:** `sstv_core/src/sstv_core/audio/stream_manager.py`

**Changes Needed:**

```python
# Wrap sounddevice calls in try/except:
def start_input(self, device_index: Optional[int] = None):
    try:
        # ... existing code ...
    except sounddevice.PortAudioError as e:
        if "Invalid device" in str(e):
            raise RuntimeError(f"Audio input device {device_index} not found")
        elif "Device unavailable" in str(e):
            raise RuntimeError(f"Audio device {device_index} is in use")
        else:
            raise RuntimeError(f"Audio device error: {e}")
```

**File:** `sstv_core/src/sstv_core/api/dsp_manager.py`

**Error Handling:**

```python
# In start_decode(), wrap in try/except:
try:
    await dsp_manager.start_decode(...)
except RuntimeError as e:
    # Emit error event immediately
    await websocket_manager.broadcast(session_id, {
        "event": "error",
        "error_code": "DEVICE_ERROR",
        "message": str(e),
    })

    # Update session state
    await session_manager.update_decode_state(
        session_id,
        DecodeState.FAILED,
        {"error": str(e)},
    )

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"error": "DEVICE_ERROR", "message": str(e)},
    )
```

**Acceptance Criteria:**
- ✅ Graceful handling of missing devices
- ✅ Clear error messages for permissions issues
- ✅ HTTP 503 returned for device failures
- ✅ WebSocket error events emitted

---

#### Task 4.2: Handle VIS Detection Timeout

**Current:** rx_manager returns None if VIS times out.

**Desired:** Emit `vis_timeout` event, trigger mode detection suggestion.

**File:** `sstv_core/src/sstv_core/decode/rx_manager.py`

**Changes:**

```python
# In receive() method, Phase 2 (line 209-216):
if not detected_mode:
    logger.warning("No VIS code detected within timeout")
    self._state = RXState.ERROR
    self._emit_progress(
        None, 0, 0, 0, 0, time.time() - start_time, 0,
        "No SSTV signal detected",
        event_type="vis_timeout",  # NEW: Signal timeout event
    )
    return None
```

**File:** `sstv_core/src/sstv_core/api/dsp_manager.py`

**Handle Timeout Event:**

```python
# In _handle_rx_progress():
if hasattr(progress, 'event_type') and progress.event_type == "vis_timeout":
    await websocket_manager.broadcast(session_id, {
        "event": "vis_timeout",
        "message": "No VIS code detected. Try manual mode selection.",
        "suggested_action": "Use POST /decode/detect_mode for auto-detection",
    })
```

**Acceptance Criteria:**
- ✅ vis_timeout event emitted after 30s
- ✅ Suggested action provided to user
- ✅ Session remains open for retry

---

#### Task 4.3: Handle PTT Failures

**Scenarios:**
1. Serial port not found
2. PTT device disconnected during TX
3. PTT timing failures

**File:** `sstv_core/src/sstv_core/audio/ptt_controller.py`

**Add Error Handling:**

```python
async def key_radio(self) -> None:
    """Key radio PTT with error handling."""
    try:
        # ... existing code ...
    except serial.SerialException as e:
        raise RuntimeError(f"PTT error: {e}. Check serial port connection.")
```

**File:** `sstv_core/src/sstv_core/encode/tx_manager.py`

**Graceful Degradation:**

```python
# In transmit() method, Phase 3 (line 154-156):
try:
    await self._ptt.key_radio()
except RuntimeError as e:
    logger.error("PTT failed: %s. Continuing without PTT.", e)
    # Emit warning but continue transmission (for VOX users)
    self._emit_progress(10, 0, 256, time.time() - start_time, total_duration,
                       f"PTT warning: {e}. Transmitting with VOX.")
```

**Acceptance Criteria:**
- ✅ PTT errors don't crash transmission
- ✅ Warning emitted if PTT fails
- ✅ Transmission continues (VOX fallback)

---

### Phase 5: Testing & Validation (4-6 hours)

#### Task 5.1: Integration Tests for Decode Pipeline

**File:** `sstv_core/tests/integration/test_decode_integration.py` (NEW)

**Test Cases:**

```python
import pytest
import asyncio
from pathlib import Path

@pytest.mark.asyncio
async def test_decode_scottie_s1_end_to_end(test_audio_file):
    """Test complete decode pipeline with real audio file."""

    # 1. Start decode session via API
    response = await client.post("/api/v1/decode/start", json={
        "mode": "SCOTTIE_S1",
        "auto_detect": False,
        "save_image": True,
        "device_id": None,  # Use test audio file instead
    })
    assert response.status_code == 201
    session_id = response.json()["session_id"]

    # 2. Connect to WebSocket
    async with client.websocket_connect(f"/api/v1/ws/decode/{session_id}") as ws:

        # 3. Wait for events
        events = []
        timeout = asyncio.create_task(asyncio.sleep(10))

        while not timeout.done():
            msg = await ws.receive_json()
            events.append(msg)

            if msg["event"] == "decode_complete":
                break

        # 4. Verify event sequence
        assert any(e["event"] == "scanline_update" for e in events)
        assert any(e["event"] == "decode_complete" for e in events)

        # 5. Verify image saved
        complete_event = next(e for e in events if e["event"] == "decode_complete")
        assert Path(complete_event["filepath"]).exists()

        # 6. Verify database record
        image_id = complete_event["image_id"]
        db_response = await client.get(f"/api/v1/images/{image_id}")
        assert db_response.status_code == 200
        assert db_response.json()["mode"] == "SCOTTIE_S1"


@pytest.mark.asyncio
async def test_decode_vis_timeout():
    """Test VIS detection timeout handling."""
    # Use silent audio file (no SSTV signal)
    ...


@pytest.mark.asyncio
async def test_decode_concurrent_sessions_blocked():
    """Test half-duplex constraint."""
    # Start first session
    # Attempt second session
    # Expect 409 Conflict
    ...
```

**Acceptance Criteria:**
- ✅ End-to-end decode test passes
- ✅ VIS timeout test passes
- ✅ Half-duplex constraint test passes
- ✅ Tests run in CI without audio hardware

---

#### Task 5.2: Integration Tests for Transmit Pipeline

**File:** `sstv_core/tests/integration/test_transmit_integration.py` (NEW)

**Test Cases:**

```python
@pytest.mark.asyncio
async def test_transmit_scottie_s1_end_to_end(test_image):
    """Test complete transmit pipeline."""

    # 1. Start transmit session
    response = await client.post("/api/v1/transmit", json={
        "image_path": str(test_image),
        "mode": "SCOTTIE_S1",
        "vox_enabled": True,
        "device_id": None,  # Use test output
    })
    assert response.status_code == 201
    tx_id = response.json()["tx_id"]

    # 2. Connect WebSocket
    async with client.websocket_connect(f"/api/v1/ws/transmit/{tx_id}") as ws:

        # 3. Collect events
        events = []
        timeout = asyncio.create_task(asyncio.sleep(20))

        while not timeout.done():
            msg = await ws.receive_json()
            events.append(msg)

            if msg["event"] == "tx_complete":
                break

        # 4. Verify event sequence
        assert any(e["event"] == "tx_progress" for e in events)
        assert any(e["event"] == "tx_complete" for e in events)

        # 5. Verify audio generated (mock output captured)
        # ...


@pytest.mark.asyncio
async def test_transmit_ptt_failure_handling():
    """Test PTT failure doesn't crash transmission."""
    # Mock PTT controller to raise error
    # Expect transmission to continue with warning
    ...
```

**Acceptance Criteria:**
- ✅ End-to-end transmit test passes
- ✅ PTT failure handling test passes
- ✅ Audio output validated

---

#### Task 5.3: Manual Testing Checklist

**Prerequisites:**
- Audio input device (microphone or radio interface)
- Audio output device (speakers or radio interface)
- Reference SSTV audio files (Scottie S1, Martin M1, Robot 36)

**Test Scenarios:**

1. **Decode with VIS Detection**
   - [ ] Start decode session with auto_detect=true
   - [ ] Play reference Scottie S1 audio
   - [ ] Verify VIS detected event
   - [ ] Verify scanline updates (0-255)
   - [ ] Verify decode complete event
   - [ ] Verify image saved to disk
   - [ ] Verify database record created

2. **Decode with Manual Mode**
   - [ ] Start decode with mode="MARTIN_M1", auto_detect=false
   - [ ] Play Martin M1 audio
   - [ ] Verify decode completes
   - [ ] Verify image matches reference

3. **Decode VIS Timeout**
   - [ ] Start decode with timeout_seconds=10
   - [ ] Play no audio (silence)
   - [ ] Verify vis_timeout event after 10s
   - [ ] Verify session remains open

4. **Transmit with Serial PTT**
   - [ ] Configure serial port in request
   - [ ] Start transmit
   - [ ] Verify PTT keyed (measure RTS signal)
   - [ ] Verify audio transmitted
   - [ ] Verify PTT unkeyed

5. **Transmit with VOX**
   - [ ] Start transmit with vox_enabled=true
   - [ ] Verify preamble silence injected
   - [ ] Verify transmission completes

6. **Half-Duplex Enforcement**
   - [ ] Start decode session
   - [ ] Attempt to start transmit session
   - [ ] Verify 409 Conflict error

7. **WebSocket Reconnection**
   - [ ] Start decode session
   - [ ] Connect WebSocket
   - [ ] Disconnect WebSocket mid-decode
   - [ ] Reconnect WebSocket
   - [ ] Verify session_resume event
   - [ ] Verify buffered events received

**Acceptance Criteria:**
- ✅ All 7 scenarios pass
- ✅ No crashes or exceptions
- ✅ Error messages are clear and helpful

---

## Environment Variables

**New Variables:**

```bash
# Disable simulation mode (use real DSP)
SSTVE_SIMULATE_OPERATIONS=0  # Set to 0 or unset

# Audio device settings (optional, for CLI mode)
SSTVE_DEFAULT_INPUT_DEVICE=0
SSTVE_DEFAULT_OUTPUT_DEVICE=0

# Image save directory
SSTVE_IMAGE_DIRECTORY=/home/user/sstv_images

# Database connection
SSTVE_DATABASE_URL=sqlite:///./sstv.db
```

---

## Rollback Plan

If wiring causes issues, revert to simulation mode:

1. Set `SSTVE_SIMULATE_OPERATIONS=1`
2. Revert decode.py and transmit.py imports to use `operation_manager`
3. API will function with synthetic events (no audio processing)

This allows frontend development to continue while DSP issues are debugged.

---

## Migration Path

### Step 1: Install Package in Editable Mode

```bash
cd sstv_core
pip install -e .
```

**Why:** Tests currently can't import modules. This fixes imports.

### Step 2: Implement Phase 1 (DSP Manager)

- Create dsp_manager.py
- Unit tests for DSPManager class
- Verify wiring without audio hardware (mocks)

### Step 3: Implement Phase 2 (WebSocket Routes)

- Create websocket.py routes
- Test WebSocket connection/disconnection
- Test event buffering

### Step 4: Implement Phase 3 (Database Integration)

- Modify image_saver.py
- Test database record creation
- Verify image_id in events

### Step 5: Implement Phase 4 (Error Handling)

- Add device error handling
- Add PTT error handling
- Test failure scenarios

### Step 6: Implement Phase 5 (Testing)

- Write integration tests
- Run manual testing checklist
- Document any issues

### Step 7: Update Documentation

- Update API docs with device_id parameters
- Update WebSocket event specifications
- Update deployment guide with audio device setup

---

## Success Metrics

**Definition of Done:**

1. ✅ User calls `/decode/start` → Real audio stream starts
2. ✅ VIS detection happens on real audio input
3. ✅ Scanlines decoded from real signal
4. ✅ WebSocket events emitted during decode
5. ✅ Image saved to disk and database
6. ✅ User calls `/transmit` → Real audio output plays
7. ✅ PTT control engages serial or VOX
8. ✅ Audio transmitted to radio
9. ✅ Integration tests pass
10. ✅ Manual testing checklist complete

**Timeline:**

- Phase 1: 4-6 hours (1 day)
- Phase 2: 3-4 hours (0.5 day)
- Phase 3: 2-3 hours (0.5 day)
- Phase 4: 3-4 hours (0.5 day)
- Phase 5: 4-6 hours (1 day)

**Total: 16-23 hours (3-4 working days)**

---

## Next Steps After Wiring

Once API-to-DSP wiring is complete, the next priorities are:

1. **Implement 4 make-or-break features** (bandpass filter, correlation VIS, Hough slant, audio_levels events) - **3-4 weeks**
2. **Add filesystem watcher** (Phase 4) - 1 week
3. **Add smart features** (Phase 5: Smart Reply, mode detection) - 2 weeks
4. **Comprehensive testing** (Phase 6) - 1 week

---

## Questions & Clarifications

**Q: What happens to operation_manager.py after wiring?**
A: Keep it for testing. It can be toggled via `SSTVE_SIMULATE_OPERATIONS=1` for frontend development without audio hardware.

**Q: Do we need audio device mocking for CI tests?**
A: Yes. Use `unittest.mock` to patch `sounddevice` calls. See existing test files for examples.

**Q: How do we test without real radio hardware?**
A: Use reference audio files as input (WAV files containing SSTV signals). Use file I/O instead of sounddevice for tests.

**Q: Can multiple clients connect to same WebSocket session?**
A: Yes. WebSocketManager supports multiple connections per session (e.g., desktop + mobile).

---

## References

- **BACKEND_TASKS.md** - Original task breakdown
- **docs/app-spec.md** - API specification (WebSocket events, REST endpoints)
- **rx_manager.py** - Decode pipeline implementation
- **tx_manager.py** - Transmit pipeline implementation
- **websocket_manager.py** - Event broadcasting infrastructure
- **session_manager.py** - Session lifecycle management
