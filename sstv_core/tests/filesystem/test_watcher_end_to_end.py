"""End-to-end watcher test: a real Observer, a real file, a real database.

The audit proved the watcher's one job -- importing a newly saved image --
did not work: the OS delivers created-then-modified for a new file, the
debouncer keeps only the latest event, and _handle_modified dropped
unknown files with "Cannot update non-existent image" (0 DB rows). The
old unit tests called _handle_created directly and never saw it.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sstv_core.database.models import Base, SSTVImage
from sstv_core.filesystem.watcher import ImageLibraryWatcher


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/library.db")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _wait_for_row(session_factory, filepath: Path, timeout: float = 5.0) -> SSTVImage | None:
    deadline = time.monotonic() + timeout
    resolved = str(filepath.resolve())
    while time.monotonic() < deadline:
        with session_factory() as session:
            row = session.query(SSTVImage).filter_by(filepath=resolved).first()
            if row is not None:
                session.expunge(row)
                return row
        time.sleep(0.1)
    return None


def test_new_image_file_is_imported(tmp_path, session_factory):
    watch_dir = tmp_path / "library"
    watch_dir.mkdir()

    watcher = ImageLibraryWatcher(
        watch_path=watch_dir,
        session_factory=session_factory,
        websocket_manager=None,
        debounce_delay=0.2,
    )
    watcher.start()
    try:
        # Written the way real software writes images: create + write, which
        # the OS reports as created followed by modified.
        image_path = watch_dir / "20260807_143000_ScottieS1_K0ABC.jpg"
        Image.new("RGB", (32, 32), (200, 30, 30)).save(image_path)

        row = _wait_for_row(session_factory, image_path)
        assert row is not None, "watcher never imported the new file"
        assert row.mode == "ScottieS1"
        assert row.callsign == "K0ABC"
    finally:
        watcher.stop()


def test_own_decode_output_filename_imports_with_mode(tmp_path, session_factory):
    """SSTeVe's own saver naming (sstv_rx_MODE_DATE_TIME) must import with
    the mode, not as mode='Unknown'."""
    watch_dir = tmp_path / "library"
    watch_dir.mkdir()

    watcher = ImageLibraryWatcher(
        watch_path=watch_dir,
        session_factory=session_factory,
        websocket_manager=None,
        debounce_delay=0.2,
    )
    watcher.start()
    try:
        image_path = watch_dir / "sstv_rx_MartinM1_20260807_143000.png"
        Image.new("RGB", (32, 32), (30, 200, 30)).save(image_path)

        row = _wait_for_row(session_factory, image_path)
        assert row is not None
        assert row.mode == "MartinM1"
    finally:
        watcher.stop()
