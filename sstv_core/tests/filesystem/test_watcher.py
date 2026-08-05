"""Unit tests for the image library filesystem watcher."""

import asyncio
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from watchdog.events import (
    DirCreatedEvent,
    DirModifiedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
)

from sstv_core.filesystem.watcher import DebouncedEventHandler, ImageLibraryWatcher

# Short debounce so tests stay fast; waits are ~4x this.
DEBOUNCE = 0.05
WAIT = 0.2


class CallbackRecorder:
    """Records handler callback invocations with a threading.Event per call."""

    def __init__(self):
        self.created: list[Path] = []
        self.modified: list[Path] = []
        self.deleted: list[Path] = []
        self.moved: list[tuple[Path, Path]] = []
        self.fired = threading.Event()

    def on_created(self, path: Path) -> None:
        self.created.append(path)
        self.fired.set()

    def on_modified(self, path: Path) -> None:
        self.modified.append(path)
        self.fired.set()

    def on_deleted(self, path: Path) -> None:
        self.deleted.append(path)
        self.fired.set()

    def on_moved(self, src: Path, dest: Path) -> None:
        self.moved.append((src, dest))
        self.fired.set()


@pytest.fixture
def recorder():
    return CallbackRecorder()


@pytest.fixture
def handler(recorder):
    return DebouncedEventHandler(
        on_created_callback=recorder.on_created,
        on_modified_callback=recorder.on_modified,
        on_deleted_callback=recorder.on_deleted,
        on_moved_callback=recorder.on_moved,
        debounce_delay=DEBOUNCE,
    )


@pytest.fixture
def session_factory():
    """Fake session factory: calling it returns a context manager yielding a mock session."""
    factory = MagicMock()
    factory.return_value.__enter__.return_value = MagicMock(name="session")
    return factory


def make_watcher(tmp_path, session_factory, websocket_manager=None):
    return ImageLibraryWatcher(
        watch_path=tmp_path,
        session_factory=session_factory,
        websocket_manager=websocket_manager,
        debounce_delay=DEBOUNCE,
    )


# ============================================================================
# DebouncedEventHandler: filtering
# ============================================================================


@pytest.mark.parametrize("filename", ["a.jpg", "b.jpeg", "c.png", "d.bmp", "E.JPG"])
def test_handler_accepts_image_extensions(handler, recorder, filename):
    handler.on_created(FileCreatedEvent(f"/tmp/{filename}"))
    assert recorder.fired.wait(WAIT)
    assert recorder.created == [Path(f"/tmp/{filename}")]


@pytest.mark.parametrize("filename", ["notes.txt", "audio.wav", "image.gif", "noext"])
def test_handler_ignores_non_image_files(handler, recorder, filename):
    handler.on_created(FileCreatedEvent(f"/tmp/{filename}"))
    handler.on_modified(FileModifiedEvent(f"/tmp/{filename}"))
    handler.on_deleted(FileDeletedEvent(f"/tmp/{filename}"))
    assert not recorder.fired.wait(WAIT)
    assert recorder.created == []
    assert recorder.modified == []
    assert recorder.deleted == []


def test_handler_ignores_directory_events(handler, recorder):
    handler.on_created(DirCreatedEvent("/tmp/newdir.jpg"))
    handler.on_modified(DirModifiedEvent("/tmp/newdir.jpg"))
    assert not recorder.fired.wait(WAIT)
    assert recorder.created == []
    assert recorder.modified == []


# ============================================================================
# DebouncedEventHandler: debouncing and dispatch
# ============================================================================


def test_rapid_events_collapse_to_one_callback(handler, recorder):
    """Rapid repeated events for the same path fire only the last callback once."""
    for _ in range(5):
        handler.on_modified(FileModifiedEvent("/tmp/burst.jpg"))
        time.sleep(0.005)
    assert recorder.fired.wait(WAIT)
    time.sleep(WAIT)  # Ensure no stragglers land after the first fire
    assert recorder.modified == [Path("/tmp/burst.jpg")]


def test_later_event_supersedes_pending_event(handler, recorder):
    """A deleted event within the debounce window replaces a pending created event."""
    handler.on_created(FileCreatedEvent("/tmp/short.jpg"))
    handler.on_deleted(FileDeletedEvent("/tmp/short.jpg"))
    assert recorder.fired.wait(WAIT)
    time.sleep(WAIT)
    assert recorder.created == []
    assert recorder.deleted == [Path("/tmp/short.jpg")]


def test_dispatch_created(handler, recorder):
    handler.on_created(FileCreatedEvent("/tmp/new.png"))
    assert recorder.fired.wait(WAIT)
    assert recorder.created == [Path("/tmp/new.png")]


def test_dispatch_modified(handler, recorder):
    handler.on_modified(FileModifiedEvent("/tmp/edit.png"))
    assert recorder.fired.wait(WAIT)
    assert recorder.modified == [Path("/tmp/edit.png")]


def test_dispatch_deleted(handler, recorder):
    handler.on_deleted(FileDeletedEvent("/tmp/gone.png"))
    assert recorder.fired.wait(WAIT)
    assert recorder.deleted == [Path("/tmp/gone.png")]


def test_dispatch_moved_image_to_image(handler, recorder):
    handler.on_moved(FileMovedEvent("/tmp/old.jpg", "/tmp/new.jpg"))
    assert recorder.fired.wait(WAIT)
    assert recorder.moved == [(Path("/tmp/old.jpg"), Path("/tmp/new.jpg"))]


def test_moved_image_to_non_image_is_delete(handler, recorder):
    handler.on_moved(FileMovedEvent("/tmp/pic.jpg", "/tmp/pic.bak"))
    assert recorder.fired.wait(WAIT)
    assert recorder.deleted == [Path("/tmp/pic.jpg")]
    assert recorder.moved == []


def test_moved_non_image_to_image_is_create(handler, recorder):
    handler.on_moved(FileMovedEvent("/tmp/pic.tmp", "/tmp/pic.jpg"))
    assert recorder.fired.wait(WAIT)
    assert recorder.created == [Path("/tmp/pic.jpg")]
    assert recorder.moved == []


def test_moved_non_image_to_non_image_ignored(handler, recorder):
    handler.on_moved(FileMovedEvent("/tmp/a.txt", "/tmp/b.txt"))
    assert not recorder.fired.wait(WAIT)


# ============================================================================
# ImageLibraryWatcher: lifecycle
# ============================================================================


def test_start_missing_path_raises(tmp_path, session_factory):
    watcher = make_watcher(tmp_path / "does-not-exist", session_factory)
    with pytest.raises(FileNotFoundError):
        watcher.start()
    assert not watcher.is_running()


def test_start_non_directory_raises(tmp_path, session_factory):
    filepath = tmp_path / "file.jpg"
    filepath.write_bytes(b"")
    watcher = make_watcher(filepath, session_factory)
    with pytest.raises(NotADirectoryError):
        watcher.start()
    assert not watcher.is_running()


def test_lifecycle_with_real_observer(tmp_path, session_factory):
    """start/stop with a real watchdog Observer; double start raises; stop is idempotent."""
    watcher = make_watcher(tmp_path, session_factory)
    assert not watcher.is_running()

    watcher.start()
    try:
        assert watcher.is_running()
        with pytest.raises(RuntimeError):
            watcher.start()
    finally:
        watcher.stop()

    assert not watcher.is_running()
    watcher.stop()  # Idempotent — no error
    assert not watcher.is_running()


def test_stop_before_start_is_noop(tmp_path, session_factory):
    watcher = make_watcher(tmp_path, session_factory)
    watcher.stop()
    assert not watcher.is_running()


# ============================================================================
# Handler -> importer wiring
# ============================================================================


def test_handle_created_imports_image(tmp_path, session_factory):
    watcher = make_watcher(tmp_path, session_factory)
    filepath = tmp_path / "new.jpg"

    image = MagicMock(id=7)
    image.to_dict.return_value = {"id": 7}
    with patch("sstv_core.filesystem.importer.ImageImporter") as importer_cls:
        importer_cls.return_value.import_image.return_value = image
        watcher._handle_created(filepath)

    session = session_factory.return_value.__enter__.return_value
    importer_cls.assert_called_once_with(session)
    importer_cls.return_value.import_image.assert_called_once_with(filepath)


def test_handle_deleted_removes_image(tmp_path, session_factory):
    watcher = make_watcher(tmp_path, session_factory)
    filepath = tmp_path / "gone.jpg"

    with patch("sstv_core.filesystem.importer.ImageImporter") as importer_cls:
        importer_cls.return_value.remove_image.return_value = True
        watcher._handle_deleted(filepath)

    importer_cls.return_value.remove_image.assert_called_once_with(filepath)


def test_handle_created_swallows_importer_error(tmp_path, session_factory, caplog):
    watcher = make_watcher(tmp_path, session_factory)

    with patch("sstv_core.filesystem.importer.ImageImporter") as importer_cls:
        importer_cls.return_value.import_image.side_effect = RuntimeError("db exploded")
        with caplog.at_level("ERROR", logger="sstv_core.filesystem.watcher"):
            watcher._handle_created(tmp_path / "bad.jpg")  # Must not raise

    assert any("Failed to import image" in r.message for r in caplog.records)


def test_handle_deleted_swallows_importer_error(tmp_path, session_factory, caplog):
    watcher = make_watcher(tmp_path, session_factory)

    with patch("sstv_core.filesystem.importer.ImageImporter") as importer_cls:
        importer_cls.return_value.remove_image.side_effect = RuntimeError("db exploded")
        with caplog.at_level("ERROR", logger="sstv_core.filesystem.watcher"):
            watcher._handle_deleted(tmp_path / "bad.jpg")  # Must not raise

    assert any("Failed to remove image" in r.message for r in caplog.records)


# ============================================================================
# _broadcast: cross-thread WebSocket delivery (regression)
# ============================================================================


class RecordingWebSocketManager:
    """Fake websocket manager whose broadcast coroutine records calls."""

    def __init__(self):
        self.events: list[dict] = []
        self.delivered = threading.Event()

    async def broadcast_library_event(self, event: dict) -> None:
        self.events.append(event)
        self.delivered.set()


@pytest.fixture
def background_loop():
    """A real asyncio event loop running in a background thread."""
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    yield loop
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=2.0)
    loop.close()


def test_broadcast_delivers_across_threads(tmp_path, session_factory, background_loop):
    """REGRESSION: _broadcast from a non-loop thread must run the coroutine on the loop."""
    ws = RecordingWebSocketManager()
    watcher = make_watcher(tmp_path, session_factory, websocket_manager=ws)
    watcher._loop = background_loop

    event = {"event": "library_updated", "action": "created", "filepath": "/tmp/x.jpg"}
    worker = threading.Thread(target=watcher._broadcast, args=(event,))
    worker.start()
    worker.join(timeout=2.0)
    assert not worker.is_alive()

    assert ws.delivered.wait(2.0), "broadcast coroutine never executed on the event loop"
    assert ws.events == [event]


def test_broadcast_without_websocket_manager_is_noop(tmp_path, session_factory):
    watcher = make_watcher(tmp_path, session_factory, websocket_manager=None)
    watcher._loop = None
    watcher._broadcast({"event": "library_updated"})  # Must not raise


def test_broadcast_with_no_loop_logs_and_drops(tmp_path, session_factory, caplog):
    ws = RecordingWebSocketManager()
    watcher = make_watcher(tmp_path, session_factory, websocket_manager=ws)
    watcher._loop = None

    with caplog.at_level("WARNING", logger="sstv_core.filesystem.watcher"):
        watcher._broadcast({"event": "image_deleted"})  # Must not raise

    assert ws.events == []
    assert any("No event loop available" in r.message for r in caplog.records)


def test_broadcast_with_closed_loop_logs_and_drops(tmp_path, session_factory, caplog):
    ws = RecordingWebSocketManager()
    watcher = make_watcher(tmp_path, session_factory, websocket_manager=ws)
    loop = asyncio.new_event_loop()
    loop.close()
    watcher._loop = loop

    with caplog.at_level("WARNING", logger="sstv_core.filesystem.watcher"):
        watcher._broadcast({"event": "image_deleted"})  # Must not raise

    assert ws.events == []
    assert any("No event loop available" in r.message for r in caplog.records)


# ============================================================================
# start(): event loop capture
# ============================================================================


async def test_start_captures_running_loop(tmp_path, session_factory):
    watcher = make_watcher(tmp_path, session_factory, websocket_manager=MagicMock())
    watcher.start()
    try:
        assert watcher._loop is asyncio.get_running_loop()
    finally:
        watcher.stop()


def test_start_without_loop_leaves_none_and_warns(tmp_path, session_factory, caplog):
    watcher = make_watcher(tmp_path, session_factory, websocket_manager=MagicMock())
    with caplog.at_level("WARNING", logger="sstv_core.filesystem.watcher"):
        watcher.start()
    try:
        assert watcher._loop is None
        assert any("outside an event loop" in r.message for r in caplog.records)
    finally:
        watcher.stop()
