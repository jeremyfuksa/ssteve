"""Every WebSocket payload the DSP bridge emits must validate against its
models.py event model.

The 2026-08-07 audit found three incompatible event contracts coexisting:
the spec keyed events on "type", models.py on "event_type", and the actual
emitter on "event" with different field names. A client built against
either document parsed nothing. These tests pin the emitters to models.py.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from sstv_core.api import dsp_manager as dsp_module
from sstv_core.api.dsp_manager import DSPManager
from sstv_core.api.models import (
    AudioLevelsEvent,
    DecodeCompleteEvent,
    ErrorEvent,
    ScanlineUpdateEvent,
    TransmitProgressEvent,
    VISDetectedEvent,
)
from sstv_core.decode.rx_manager import RXProgress, RXState
from sstv_core.encode.tx_manager import TXProgress, TXState

MODEL_FOR_EVENT = {
    "vis_detected": VISDetectedEvent,
    "scanline_update": ScanlineUpdateEvent,
    "audio_levels": AudioLevelsEvent,
    "decode_complete": DecodeCompleteEvent,
    "tx_progress": TransmitProgressEvent,
    "error": ErrorEvent,
}


def _utc_offset_present(serialized: str) -> bool:
    """True when an ISO 8601 string carries an explicit UTC offset."""
    from datetime import datetime as _dt

    try:
        parsed = _dt.fromisoformat(serialized)
    except (TypeError, ValueError):
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


@pytest.fixture
def captured(monkeypatch):
    broadcasts: list[dict] = []

    async def record(session_id, payload):
        broadcasts.append(payload)

    monkeypatch.setattr(dsp_module.websocket_manager, "broadcast", record)
    return broadcasts


def _rx_progress(state: RXState, **overrides) -> RXProgress:
    values = {
        "state": state,
        "mode": "MartinM1",
        "mode_confidence": 0.92,
        "percent_complete": 42.0,
        "current_line": 100,
        "total_lines": 256,
        "elapsed_sec": 12.3,
        "signal_quality": 0.8,
        "message": "test",
        "audio_levels": None,
    }
    values.update(overrides)
    return RXProgress(**values)


def _validate_all(broadcasts: list[dict]) -> None:
    assert broadcasts, "nothing was broadcast"
    for payload in broadcasts:
        event_type = payload.get("event_type")
        assert event_type in MODEL_FOR_EVENT, (
            f"payload not keyed on event_type / unknown type: {payload}"
        )
        MODEL_FOR_EVENT[event_type].model_validate(payload)


@pytest.mark.asyncio
async def test_vis_and_scanline_events_match_models(captured):
    manager = DSPManager()
    session_id = uuid4()

    await manager._handle_rx_progress(session_id, _rx_progress(RXState.VIS_DETECTED))
    await manager._handle_rx_progress(
        session_id, _rx_progress(RXState.DECODING, current_line=100)
    )
    levels = SimpleNamespace(rms=0.1, peak=0.4, is_clipping=False)
    await manager._handle_rx_progress(
        session_id, _rx_progress(RXState.DECODING, audio_levels=levels)
    )

    _validate_all(captured)
    types = {p["event_type"] for p in captured}
    assert {"vis_detected", "scanline_update", "audio_levels"} <= types


@pytest.mark.asyncio
async def test_tx_progress_event_matches_model(captured):
    manager = DSPManager()
    progress = TXProgress(
        state=TXState.TRANSMITTING,
        percent_complete=50.0,
        current_line=128,
        total_lines=256,
        elapsed_sec=57.0,
        remaining_sec=57.0,
        message="test",
    )
    await manager._handle_tx_progress(uuid4(), progress)
    _validate_all(captured)
    assert captured[0]["event_type"] == "tx_progress"


@pytest.mark.asyncio
async def test_decode_complete_carries_real_duration_and_mode(captured, tmp_path):
    from sstv_core.api.session_manager import session_manager

    manager = DSPManager()
    import time as _time

    session = await session_manager.create_decode_session(metadata={"mode": "MartinM1"})
    manager._session_started[session.session_id] = _time.time() - 90.0

    image_path = tmp_path / "decoded.png"
    image_path.write_bytes(b"png")

    task: asyncio.Future = asyncio.get_event_loop().create_future()
    task.set_result(image_path)
    try:
        await manager._handle_decode_complete(session.session_id, task)
    finally:
        session_manager.reset()

    completes = [p for p in captured if p.get("event_type") == "decode_complete"]
    assert completes, f"no decode_complete: {captured}"
    payload = completes[0]
    DecodeCompleteEvent.model_validate(payload)
    assert payload["mode"] == "MartinM1"
    assert 85.0 < payload["duration_seconds"] < 95.0
    assert payload["timestamp"] not in (0, "0", None)
    # Not merely non-null: the offset must survive serialization. A naive
    # "2026-08-09T14:23:11" passes the check above and is then read in the
    # browser's local zone -- an hours-wide error in when a contact happened.
    assert _utc_offset_present(payload["timestamp"]), payload["timestamp"]


@pytest.mark.asyncio
async def test_broadcast_not_serialized_behind_slow_client():
    """One stalled client must not block delivery to other sessions."""
    from sstv_core.api.websocket_manager import WebSocketManager

    manager = WebSocketManager()

    class SlowConnection:
        async def send_event(self, event):
            await asyncio.sleep(1.0)
            return True

    class FastConnection:
        def __init__(self):
            self.received = []

        async def send_event(self, event):
            self.received.append(event)
            return True

    slow_session, fast_session = uuid4(), uuid4()
    fast = FastConnection()
    manager._connections[slow_session] = {SlowConnection()}
    manager._connections[fast_session] = {fast}

    slow_task = asyncio.create_task(manager.broadcast(slow_session, {"event_type": "x"}))
    await asyncio.sleep(0.05)  # slow send is now in flight
    # The fast broadcast must complete while the slow one is still sending.
    await asyncio.wait_for(
        manager.broadcast(fast_session, {"event_type": "y"}), timeout=0.5
    )
    assert fast.received
    await slow_task


class TestTimestampSerialization:
    """Every event's timestamp must reach the client with a UTC offset.

    The "+00:00 on WS/event timestamps" claim was enforced by code but
    asserted by nothing before 2026-08-09: the only check tested non-null,
    which a naive datetime passes. `mode="json"` is what turns the tz-aware
    default into an offset-bearing string, and that string is all a client
    ever sees -- so that is what these assert.
    """

    @pytest.mark.parametrize(
        "event_type,model", sorted(MODEL_FOR_EVENT.items())
    )
    def test_event_timestamp_serializes_with_offset(self, event_type, model):
        required = {
            "vis_detected": {"mode": "MartinM1", "confidence": 0.9},
            "scanline_update": {
                "scanline_number": 5,
                "total_scanlines": 256,
                "progress_percent": 2.0,
            },
            "audio_levels": {
                "left_db": -20.0,
                "right_db": -20.0,
                "peak_db": -10.0,
                "is_clipping": False,
            },
            "decode_complete": {"filepath": "/tmp/x.png", "duration_seconds": 90.0},
            "tx_progress": {
                "progress_percent": 2.0,
                "current_scanline": 5,
                "time_remaining_seconds": 89.0,
            },
            "error": {"error_code": "E", "message": "m"},
        }[event_type]

        payload = model(**required).model_dump(mode="json")
        serialized = payload["timestamp"]
        assert isinstance(serialized, str), (
            f"{event_type} timestamp is {type(serialized)}, not a JSON string"
        )
        assert _utc_offset_present(serialized), (
            f"{event_type} timestamp has no UTC offset: {serialized!r}"
        )
        assert serialized.endswith("+00:00") or serialized.endswith("Z"), serialized

    def test_a_naive_timestamp_would_be_caught(self):
        """Guard the guard: the helper must reject an offset-less string."""
        assert not _utc_offset_present("2026-08-09T14:23:11")
        assert _utc_offset_present("2026-08-09T14:23:11+00:00")
