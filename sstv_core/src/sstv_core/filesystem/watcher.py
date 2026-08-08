"""File system watcher for SSTeVe image library.

Monitors a directory for SSTV image additions, modifications, and deletions,
automatically importing new images to the database with metadata extraction.

Features:
- Auto-import new images (jpg, png, bmp)
- Update metadata on file edits
- Remove database records on file deletion
- Debounce rapid changes (500ms)
- Handle rename/move operations
- Thread-safe operation
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from watchdog.events import (
    DirCreatedEvent,
    DirDeletedEvent,
    DirModifiedEvent,
    DirMovedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from watchdog.observers.api import BaseObserver

logger = logging.getLogger(__name__)


# Supported image formats
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}


class DebouncedEventHandler(FileSystemEventHandler):
    """Event handler with debouncing for file system changes.

    Debounces rapid file changes (e.g., multiple writes during save)
    by waiting 500ms after the last event before processing.
    """

    def __init__(
        self,
        on_created_callback: Callable[[Path], None],
        on_modified_callback: Callable[[Path], None],
        on_deleted_callback: Callable[[Path], None],
        on_moved_callback: Callable[[Path, Path], None],
        debounce_delay: float = 0.5,
    ):
        """Initialize the event handler.

        Args:
            on_created_callback: Called when a new image file is created
            on_modified_callback: Called when an image file is modified
            on_deleted_callback: Called when an image file is deleted
            on_moved_callback: Called when an image file is moved/renamed
            debounce_delay: Delay in seconds before processing events (default 0.5s)

        """
        super().__init__()
        self._on_created = on_created_callback
        self._on_modified = on_modified_callback
        self._on_deleted = on_deleted_callback
        self._on_moved = on_moved_callback
        self._debounce_delay = debounce_delay

        # Debounce tracking: path -> (event_type, timer)
        self._pending_events: dict[str, tuple[str, threading.Timer]] = {}
        self._lock = threading.Lock()

    def _is_image_file(self, path: str) -> bool:
        """Check if path is an image file we should monitor."""
        return Path(path).suffix.lower() in IMAGE_EXTENSIONS

    def _debounce_event(self, path: str, event_type: str, callback: Callable[[], None]) -> None:
        """Debounce an event by canceling previous timer and starting new one.

        Args:
            path: File path for event
            event_type: Type of event ("created", "modified", "deleted", "moved")
            callback: Function to call after debounce delay

        """
        with self._lock:
            # Cancel existing timer for this path
            if path in self._pending_events:
                old_type, old_timer = self._pending_events[path]
                old_timer.cancel()
                logger.debug(
                    "Canceled pending %s event for %s (superseded by %s)",
                    old_type,
                    path,
                    event_type
                )

            # Create new timer
            timer = threading.Timer(self._debounce_delay, callback)
            self._pending_events[path] = (event_type, timer)
            timer.start()

            logger.debug(
                "Debouncing %s event for %s (%.1fs delay)",
                event_type,
                path,
                self._debounce_delay
            )

    def _process_created(self, path: str) -> None:
        """Process a file creation event (after debounce)."""
        try:
            logger.info("Processing file creation: %s", path)
            self._on_created(Path(path))
        except Exception as e:
            logger.error("Error processing file creation %s: %s", path, e, exc_info=True)
        finally:
            with self._lock:
                self._pending_events.pop(path, None)

    def _process_modified(self, path: str) -> None:
        """Process a file modification event (after debounce)."""
        try:
            logger.info("Processing file modification: %s", path)
            self._on_modified(Path(path))
        except Exception as e:
            logger.error("Error processing file modification %s: %s", path, e, exc_info=True)
        finally:
            with self._lock:
                self._pending_events.pop(path, None)

    def _process_deleted(self, path: str) -> None:
        """Process a file deletion event (after debounce)."""
        try:
            logger.info("Processing file deletion: %s", path)
            self._on_deleted(Path(path))
        except Exception as e:
            logger.error("Error processing file deletion %s: %s", path, e, exc_info=True)
        finally:
            with self._lock:
                self._pending_events.pop(path, None)

    def _process_moved(self, src_path: str, dest_path: str) -> None:
        """Process a file move/rename event (after debounce)."""
        try:
            logger.info("Processing file move: %s -> %s", src_path, dest_path)
            self._on_moved(Path(src_path), Path(dest_path))
        except Exception as e:
            logger.error(
                "Error processing file move %s -> %s: %s", src_path, dest_path, e, exc_info=True
            )
        finally:
            with self._lock:
                self._pending_events.pop(dest_path, None)

    def on_created(self, event: FileCreatedEvent | DirCreatedEvent) -> None:
        """Handle file or directory creation events."""
        src_path = os.fsdecode(event.src_path)
        if isinstance(event, DirCreatedEvent) or not self._is_image_file(src_path):
            return

        self._debounce_event(
            src_path,
            "created",
            lambda: self._process_created(src_path)
        )

    def on_modified(self, event: FileModifiedEvent | DirModifiedEvent) -> None:
        """Handle file or directory modification events."""
        src_path = os.fsdecode(event.src_path)
        if isinstance(event, DirModifiedEvent) or not self._is_image_file(src_path):
            return

        self._debounce_event(
            src_path,
            "modified",
            lambda: self._process_modified(src_path)
        )

    def on_deleted(self, event: FileDeletedEvent | DirDeletedEvent) -> None:
        """Handle file or directory deletion events."""
        src_path = os.fsdecode(event.src_path)
        if isinstance(event, DirDeletedEvent) or not self._is_image_file(src_path):
            return

        self._debounce_event(
            src_path,
            "deleted",
            lambda: self._process_deleted(src_path)
        )

    def on_moved(self, event: FileMovedEvent | DirMovedEvent) -> None:
        """Handle file or directory move/rename events."""
        if isinstance(event, DirMovedEvent):
            return

        src_path = os.fsdecode(event.src_path)
        dest_path = os.fsdecode(event.dest_path)

        # Handle move of image files
        src_is_image = self._is_image_file(src_path)
        dest_is_image = self._is_image_file(dest_path)

        if not src_is_image and not dest_is_image:
            return

        if src_is_image and dest_is_image:
            # Image renamed/moved to another image
            self._debounce_event(
                dest_path,
                "moved",
                lambda: self._process_moved(src_path, dest_path)
            )
        elif src_is_image:
            # Image renamed to non-image (treat as delete)
            self._debounce_event(
                src_path,
                "deleted",
                lambda: self._process_deleted(src_path)
            )
        else:
            # Non-image renamed to image (treat as create)
            self._debounce_event(
                dest_path,
                "created",
                lambda: self._process_created(dest_path)
            )


class ImageLibraryWatcher:
    """Watches an image library directory for changes and auto-imports to database.

    Monitors a directory tree for SSTV images (jpg, png, bmp) and automatically:
    - Imports new images with metadata extraction
    - Updates metadata when files are modified
    - Removes database records when files are deleted
    - Handles rename/move operations

    Thread-safe and uses debouncing to avoid processing rapid file changes.

    Usage:
        from sstv_core.filesystem import ImageLibraryWatcher
        from sstv_core.database.models import init_database

        engine, session_factory = init_database()

        watcher = ImageLibraryWatcher(
            watch_path="/home/user/.ssteve/images",
            session_factory=session_factory
        )

        watcher.start()  # Begin monitoring

        # Later...
        watcher.stop()  # Stop monitoring
    """

    def __init__(
        self,
        watch_path: str | Path,
        session_factory: Callable[[], Session],
        websocket_manager: Any | None = None,
        debounce_delay: float = 0.5,
    ):
        """Initialize the image library watcher.

        Args:
            watch_path: Directory to watch for image changes
            session_factory: SQLAlchemy session factory for database access
            websocket_manager: Optional WebSocket manager for broadcasting events
            debounce_delay: Delay in seconds before processing events (default 0.5s)

        """
        self.watch_path = Path(watch_path)
        self._session_factory = session_factory
        self._websocket_manager = websocket_manager
        self._debounce_delay = debounce_delay

        self._observer: BaseObserver | None = None
        self._event_handler: DebouncedEventHandler | None = None
        self._running = False
        # Event loop for cross-thread WebSocket broadcasts; captured in start().
        self._loop: asyncio.AbstractEventLoop | None = None

        logger.info("Initialized ImageLibraryWatcher for %s", self.watch_path)

    def start(self) -> None:
        """Start watching the directory for changes.

        Raises:
            RuntimeError: If watcher is already running
            FileNotFoundError: If watch path doesn't exist

        """
        if self._running:
            raise RuntimeError("Watcher is already running")

        if not self.watch_path.exists():
            raise FileNotFoundError(f"Watch path does not exist: {self.watch_path}")

        if not self.watch_path.is_dir():
            raise NotADirectoryError(f"Watch path is not a directory: {self.watch_path}")

        # Capture the running loop (start() is called from async app startup).
        # Handler callbacks run on watchdog/timer threads, which have no loop,
        # so broadcasts must be scheduled onto this one.
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None
            if self._websocket_manager:
                logger.warning(
                    "Watcher started outside an event loop; "
                    "WebSocket library events will not be delivered"
                )

        # Create event handler with callbacks
        self._event_handler = DebouncedEventHandler(
            on_created_callback=self._handle_created,
            on_modified_callback=self._handle_modified,
            on_deleted_callback=self._handle_deleted,
            on_moved_callback=self._handle_moved,
            debounce_delay=self._debounce_delay,
        )

        # Create and start observer
        self._observer = Observer()
        self._observer.schedule(
            self._event_handler,
            str(self.watch_path),
            recursive=True  # Watch subdirectories
        )
        self._observer.start()
        self._running = True

        logger.info("Started watching %s for image changes", self.watch_path)

    def stop(self) -> None:
        """Stop watching the directory.

        Waits for observer thread to finish.
        """
        if not self._running:
            return

        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5.0)
            self._observer = None

        self._event_handler = None
        self._running = False

        logger.info("Stopped watching %s", self.watch_path)

    def _broadcast(self, event: dict[str, Any]) -> None:
        """Schedule a WebSocket broadcast from a watchdog/timer thread.

        Handler callbacks run on threads with no event loop, so the coroutine
        must be submitted to the loop captured in start().
        """
        if not self._websocket_manager:
            return
        if self._loop is None or self._loop.is_closed():
            logger.warning("No event loop available; dropping library event %r", event.get("event"))
            return
        asyncio.run_coroutine_threadsafe(
            self._websocket_manager.broadcast_library_event(event=event),
            self._loop,
        )

    def is_running(self) -> bool:
        """Check if watcher is currently running."""
        return self._running

    def _handle_created(self, filepath: Path) -> None:
        """Handle file creation event.

        Imports the new image to the database with metadata extraction.
        """
        from sstv_core.filesystem.importer import ImageImporter

        try:
            with self._session_factory() as session:
                importer = ImageImporter(session)
                image = importer.import_image(filepath)

                if image:
                    logger.info("Imported new image: %s (id=%d)", filepath.name, image.id)

                    self._broadcast(
                        {
                            "event": "library_updated",
                            "action": "created",
                            "filepath": str(filepath),
                            "image_id": image.id,
                            "metadata": image.to_dict(),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )
        except Exception as e:
            logger.error("Failed to import image %s: %s", filepath, e, exc_info=True)

    def _handle_modified(self, filepath: Path) -> None:
        """Handle file modification event.

        Updates the database record with new metadata. A modified event for
        a file with NO record is a brand-new file: saving a file emits
        created immediately followed by modified (FSEvents and inotify
        both), and the debouncer keeps only the latest event per path -- so
        new files routinely arrive here, not in _handle_created. Until
        2026-08-07 this path warned "Cannot update non-existent image" and
        dropped them, which meant the watcher never imported anything.
        """
        from sstv_core.database.models import SSTVImage
        from sstv_core.filesystem.importer import ImageImporter

        try:
            filepath_str = str(filepath.resolve())
            with self._session_factory() as session:
                known = (
                    session.query(SSTVImage)
                    .filter_by(filepath=filepath_str)
                    .first()
                    is not None
                )
            if not known:
                self._handle_created(filepath)
                return

            with self._session_factory() as session:
                importer = ImageImporter(session)
                image = importer.update_image_metadata(filepath)

                if image:
                    logger.info("Updated image metadata: %s (id=%d)", filepath.name, image.id)

                    self._broadcast(
                        {
                            "event": "image_modified",
                            "filepath": str(filepath),
                            "image_id": image.id,
                            "metadata": image.to_dict(),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )
        except Exception as e:
            logger.error("Failed to update image %s: %s", filepath, e, exc_info=True)

    def _handle_deleted(self, filepath: Path) -> None:
        """Handle file deletion event.

        Removes the database record for the deleted file.
        """
        from sstv_core.filesystem.importer import ImageImporter

        try:
            with self._session_factory() as session:
                importer = ImageImporter(session)
                deleted = importer.remove_image(filepath)

                if deleted:
                    logger.info("Removed image from database: %s", filepath)

                    self._broadcast(
                        {
                            "event": "image_deleted",
                            "filepath": str(filepath),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )
        except Exception as e:
            logger.error("Failed to remove image %s: %s", filepath, e, exc_info=True)

    def _handle_moved(self, src_path: Path, dest_path: Path) -> None:
        """Handle file move/rename event.

        Updates the database record with the new filepath.
        """
        from sstv_core.filesystem.importer import ImageImporter

        try:
            with self._session_factory() as session:
                importer = ImageImporter(session)
                image = importer.move_image(src_path, dest_path)

                if image:
                    logger.info(
                        "Moved image: %s -> %s (id=%d)", src_path.name, dest_path.name, image.id
                    )

                    self._broadcast(
                        {
                            "event": "image_moved",
                            "old_filepath": str(src_path),
                            "new_filepath": str(dest_path),
                            "image_id": image.id,
                            "metadata": image.to_dict(),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )
        except Exception as e:
            logger.error("Failed to move image %s -> %s: %s", src_path, dest_path, e, exc_info=True)
