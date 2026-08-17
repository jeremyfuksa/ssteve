"""The app-level WebSocket: the channel that exists while nothing is running.

Both other WS endpoints are session-scoped, so an idle client could receive
nothing (#57). That structurally blocked idle metering, device hot-plug, and
library pushes to a gallery with no decode open.

Note what was already half-built: broadcast_library_event() existed and the
watcher called it -- but it iterated session-keyed connections, so an idle
gallery (its actual audience) got nothing. The feature was unreachable for
want of a channel, not missing.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from sstv_core.api.app_channel import AppChannel, _to_db
from sstv_core.api.main import app
from sstv_core.api.models import DeviceChangedEvent, LibraryUpdatedEvent
from sstv_core.api.websocket_manager import WebSocketManager


class _FakeSocket:
    """Records what a client would have received."""

    def __init__(self, fail: bool = False):
        self.sent: list[dict] = []
        self.fail = fail

    async def send_json(self, payload):
        if self.fail:
            raise ConnectionResetError("client gone")
        self.sent.append(payload)


class TestAppChannelBroadcast:
    @pytest.mark.asyncio
    async def test_app_clients_receive_events_with_no_session(self):
        manager = WebSocketManager()
        socket = _FakeSocket()
        await manager.connect_app(socket)

        sent = await manager.broadcast_app({"event_type": "device_changed"})

        assert sent == 1
        assert socket.sent == [{"event_type": "device_changed"}]

    @pytest.mark.asyncio
    async def test_dead_client_is_dropped_not_retried_forever(self):
        manager = WebSocketManager()
        dead, alive = _FakeSocket(fail=True), _FakeSocket()
        await manager.connect_app(dead)
        await manager.connect_app(alive)

        assert await manager.broadcast_app({"event_type": "x"}) == 1
        assert await manager.get_app_connection_count() == 1
        # The survivor still gets the next one.
        assert await manager.broadcast_app({"event_type": "y"}) == 1

    @pytest.mark.asyncio
    async def test_library_events_reach_an_idle_gallery(self):
        """The bug behind #57: this previously required an open session."""
        manager = WebSocketManager()
        gallery = _FakeSocket()
        await manager.connect_app(gallery)

        event = LibraryUpdatedEvent(
            action="created",
            filepath="/tmp/x.png",
        ).model_dump(mode="json")
        sent = await manager.broadcast_library_event(event)

        assert sent == 1, "an idle gallery received nothing"
        assert gallery.sent[0]["action"] == "created"

    @pytest.mark.asyncio
    async def test_library_events_still_reach_session_clients(self):
        from uuid import uuid4

        manager = WebSocketManager()
        session_socket = _FakeSocket()
        await manager.connect(session_socket, uuid4())
        app_socket = _FakeSocket()
        await manager.connect_app(app_socket)

        sent = await manager.broadcast_library_event({"event_type": "library_updated"})

        assert sent == 2, "both audiences should be notified"

    @pytest.mark.asyncio
    async def test_app_broadcast_does_not_buffer(self):
        """These events describe the world now; a replayed one would lie."""
        manager = WebSocketManager()
        await manager.broadcast_app({"event_type": "device_changed"})

        late = _FakeSocket()
        conn = await manager.connect_app(late)
        replayed = await manager.send_buffered_events(conn)

        assert replayed == 0
        assert late.sent == []


class TestDeviceWatch:
    @pytest.mark.asyncio
    async def test_first_poll_establishes_a_baseline_silently(self, monkeypatch):
        """Emitting on the first tick would report every device as new."""
        channel = AppChannel()
        monkeypatch.setattr(channel, "_enumerate", lambda: {"a", "b"})

        broadcasts: list[dict] = []
        monkeypatch.setattr(
            "sstv_core.api.app_channel.websocket_manager.broadcast_app",
            lambda e: broadcasts.append(e) or asyncio.sleep(0),
        )
        monkeypatch.setattr("sstv_core.api.app_channel.DEVICE_POLL_SECONDS", 0.01)

        await channel.ensure_device_watch()
        await asyncio.sleep(0.05)
        await channel.stop_device_watch()

        assert broadcasts == [], "baseline tick should be silent"

    @pytest.mark.asyncio
    async def test_a_plugged_in_device_is_announced(self, monkeypatch):
        channel = AppChannel()
        states = [{"a"}, {"a"}, {"a", "digirig"}]

        def enumerate_devices():
            return states.pop(0) if states else {"a", "digirig"}

        monkeypatch.setattr(channel, "_enumerate", enumerate_devices)
        monkeypatch.setattr("sstv_core.api.app_channel.DEVICE_POLL_SECONDS", 0.01)

        broadcasts: list[dict] = []

        async def record(event):
            broadcasts.append(event)

        monkeypatch.setattr(
            "sstv_core.api.app_channel.websocket_manager.broadcast_app", record
        )

        await channel.ensure_device_watch()
        for _ in range(40):
            await asyncio.sleep(0.01)
            if broadcasts:
                break
        await channel.stop_device_watch()

        assert broadcasts, "hot-plug produced no event"
        assert broadcasts[0]["event_type"] == "device_changed"
        assert broadcasts[0]["added"] == ["digirig"]
        assert broadcasts[0]["removed"] == []
        assert broadcasts[0]["total"] == 2

    @pytest.mark.asyncio
    async def test_enumeration_failure_does_not_kill_the_watcher(self, monkeypatch):
        """A transient PortAudio error is the hot-plug case, not a crash."""
        channel = AppChannel()
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("PortAudio hiccup")
            return {"a"}

        monkeypatch.setattr(channel, "_enumerate", flaky)
        monkeypatch.setattr("sstv_core.api.app_channel.DEVICE_POLL_SECONDS", 0.01)

        await channel.ensure_device_watch()
        for _ in range(40):
            await asyncio.sleep(0.01)
            if calls["n"] >= 2:
                break
        still_running = channel._device_task is not None and not channel._device_task.done()
        await channel.stop_device_watch()

        assert calls["n"] >= 2, "watcher stopped after one failure"
        assert still_running

    @pytest.mark.asyncio
    async def test_watch_is_idempotent(self, monkeypatch):
        channel = AppChannel()
        monkeypatch.setattr(channel, "_enumerate", lambda: {"a"})
        monkeypatch.setattr("sstv_core.api.app_channel.DEVICE_POLL_SECONDS", 0.01)

        await channel.ensure_device_watch()
        first = channel._device_task
        await channel.ensure_device_watch()
        assert channel._device_task is first, "second call spawned a duplicate poller"
        await channel.stop_device_watch()


class TestInputMonitoring:
    @pytest.mark.asyncio
    async def test_monitor_refused_while_a_decode_holds_the_input(self, monkeypatch):
        """Half-duplex applies to the microphone, not just decode-vs-transmit."""
        from uuid import uuid4

        from sstv_core.api import dsp_manager as dsp_module

        channel = AppChannel()
        monkeypatch.setitem(dsp_module.dsp_manager._decode_tasks, uuid4(), MagicMock())
        try:
            problem = await channel.start_monitor(None)
        finally:
            dsp_module.dsp_manager._decode_tasks.clear()

        assert problem["error"] == "INPUT_BUSY"
        assert problem["suggested_action"]
        assert not channel.is_monitoring

    @pytest.mark.asyncio
    async def test_monitor_releases_the_device_when_stopped(self, monkeypatch):
        """A monitor left holding the input would block the next decode."""
        channel = AppChannel()
        stream = SimpleNamespace(
            started=False,
            stopped=False,
            start_input=lambda device_index=None: None,
            stop_input=lambda: None,
            get_input_levels=lambda: SimpleNamespace(
                rms=0.1, peak=0.2, is_clipping=False
            ),
        )
        record = {"stopped": False}

        def stop_input():
            record["stopped"] = True

        stream.stop_input = stop_input

        monkeypatch.setattr(
            "sstv_core.audio.stream_manager.AudioStreamManager", lambda: stream
        )
        monkeypatch.setattr(
            "sstv_core.api.app_channel.websocket_manager.broadcast_app",
            lambda e: asyncio.sleep(0),
        )

        assert await channel.start_monitor(None) == {}
        await asyncio.sleep(0.05)
        await channel.stop_monitor(quiet=True)

        assert record["stopped"], "input stream was never released"
        assert not channel.is_monitoring


class TestLevelConversion:
    def test_silence_is_a_number_not_negative_infinity(self):
        assert _to_db(0.0) == -120.0

    def test_full_scale_is_zero_db(self):
        assert _to_db(1.0) == pytest.approx(0.0)

    def test_half_scale_is_about_minus_six_db(self):
        assert _to_db(0.5) == pytest.approx(-6.02, abs=0.01)


class TestEndpointWiring:
    def test_ws_endpoint_accepts_and_answers_ping(self):
        with TestClient(app).websocket_connect("/api/v1/ws") as ws:
            ws.send_text("ping")
            assert ws.receive_json() == {"event": "pong"}

    def test_unknown_command_gets_a_structured_error(self):
        with TestClient(app).websocket_connect("/api/v1/ws") as ws:
            ws.send_text("please decode everything")
            event = ws.receive_json()
            assert event["event_type"] == "error"
            assert event["error_code"] == "UNKNOWN_COMMAND"
            assert event["suggested_action"]


class TestEventModels:
    def test_device_changed_serializes_with_utc_offset(self):
        """Same contract as every other event: an explicit UTC marker.

        Pydantic emits 'Z' here rather than '+00:00'; both are ISO 8601 UTC
        and both parse to an aware datetime, which is the property that
        matters -- a naive timestamp would be read in the browser's local
        zone. See test_ws_event_contract.py.
        """
        from datetime import datetime

        payload = DeviceChangedEvent(added=["x"], total=1).model_dump(mode="json")
        assert payload["event_type"] == "device_changed"
        parsed = datetime.fromisoformat(payload["timestamp"])
        assert parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0

    def test_library_updated_rejects_an_unknown_action(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            LibraryUpdatedEvent(action="teleported", filepath="/tmp/x.png")


class TestWatcherEventContract:
    """The watcher's payloads must match the models, like every other event.

    It emitted "event" (not "event_type") with three different names --
    library_updated / image_modified / image_deleted -- and a raw integer
    image_id no other endpoint exposes. Harmless while nothing could receive
    them; now that the app channel delivers to an idle gallery, a client
    would have had to special-case three unmodelled shapes.
    """

    def _broadcasts(self, tmp_path, action: str):
        """Drive one watcher handler and capture what it broadcast."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from sstv_core.database.models import Base
        from sstv_core.filesystem.watcher import ImageLibraryWatcher

        engine = create_engine(f"sqlite:///{tmp_path}/lib.db")
        Base.metadata.create_all(engine)

        captured: list[dict] = []
        watcher = ImageLibraryWatcher(
            watch_path=tmp_path,
            session_factory=sessionmaker(bind=engine),
            websocket_manager=None,
        )
        watcher._broadcast = captured.append
        return watcher, captured

    def test_created_event_matches_the_model(self, tmp_path):
        from PIL import Image

        from sstv_core.api.models import LibraryUpdatedEvent

        watcher, captured = self._broadcasts(tmp_path, "created")
        image_path = tmp_path / "20260809_143000_MartinM1_W1AW.png"
        Image.new("RGB", (320, 256)).save(image_path)

        watcher._handle_created(image_path)

        assert captured, "import produced no event"
        event = captured[0]
        assert event["event_type"] == "library_updated"
        assert event["action"] == "created"
        # Validates against the model a client would parse with.
        LibraryUpdatedEvent.model_validate(
            {k: event[k] for k in ("event_type", "action", "image_id", "filepath")}
        )

    def test_image_id_is_the_public_uuid_not_a_row_number(self, tmp_path):
        """A raw DB integer can't be matched against /images entries."""
        from uuid import UUID

        from PIL import Image

        watcher, captured = self._broadcasts(tmp_path, "created")
        image_path = tmp_path / "20260809_150000_Robot36_K0ABC.png"
        Image.new("RGB", (320, 240)).save(image_path)

        watcher._handle_created(image_path)

        assert captured
        UUID(captured[0]["image_id"])  # raises if it is still an int
