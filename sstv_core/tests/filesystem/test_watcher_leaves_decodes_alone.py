"""The library watcher must not corrupt what a decode already recorded.

Both defects here were found by looking at the desktop shell's log after its
very first decode (2026-09-11): one picture produced two rows, and the
surviving row's time moved five hours while nobody touched it.

The watcher exists to notice files the app did not create -- an MMSSTV
library, a file dropped in by hand. A row written by a decode is not one of
those, and the filename is a weaker source than the decode that produced it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import pytest
from PIL import Image

from sstv_core.api.thumbnails import generate_thumbnail, thumbnail_path_for
from sstv_core.database.models import SSTVImage, init_database
from sstv_core.decode.image_saver import ImageSaver
from sstv_core.filesystem.importer import ImageImporter
from sstv_core.filesystem.watcher import IMAGE_EXTENSIONS, DebouncedEventHandler


@pytest.fixture
def session_factory(tmp_path):
    _, factory = init_database(db_path=tmp_path / "watch.db")
    return factory


def _picture(path: Path) -> Path:
    Image.new("RGB", (320, 256), (90, 120, 60)).save(path)
    return path


class TestThumbnailsAreNotPictures:
    """#160: one decode put two rows in the log, one of them a ghost."""

    def test_a_thumbnail_is_not_imported(self, tmp_path, session_factory):
        picture = _picture(tmp_path / "sstv_rx_MartinM1_20260911_192624.png")
        thumbnail = generate_thumbnail(picture)
        assert thumbnail is not None and thumbnail.exists(), "no thumbnail to test with"

        with session_factory() as session:
            importer = ImageImporter(session)
            importer.import_image(picture)
            importer.import_image(thumbnail)

        with session_factory() as session:
            rows = session.query(SSTVImage).all()
            assert [Path(row.filepath).name for row in rows] == [picture.name], (
                "the thumbnail was logged as a received picture"
            )

    def test_the_watcher_does_not_even_look_at_thumbnails(self, tmp_path):
        """Cheaper than importing and rejecting: never queue the event."""
        handler = DebouncedEventHandler(
            on_created_callback=lambda _path: None,
            on_modified_callback=lambda _path: None,
            on_deleted_callback=lambda _path: None,
            on_moved_callback=lambda _old, _new: None,
            debounce_delay=0.01,
        )
        picture = tmp_path / "sstv_rx_MartinM1_20260911_192624.png"
        assert handler._is_image_file(str(picture))
        assert not handler._is_image_file(str(thumbnail_path_for(picture)))

    def test_a_users_own_file_is_still_imported(self, tmp_path, session_factory):
        """Only our generated suffix is reserved, not the word 'thumb'."""
        picture = _picture(tmp_path / "thumbnails_of_my_holiday.png")
        with session_factory() as session:
            assert ImageImporter(session).import_image(picture) is not None


class TestTheWatcherLeavesTheTimeAlone:
    """#161: a picture's time shifted by the UTC offset after it was saved."""

    def test_updating_metadata_does_not_move_the_timestamp(self, tmp_path, session_factory):
        picture = _picture(tmp_path / "sstv_rx_MartinM1_20260911_192624.png")
        decoded_at = datetime(2026, 9, 12, 0, 26, 24)  # UTC, as the decoder writes it

        with session_factory() as session:
            session.add(
                SSTVImage(
                    filename=picture.name,
                    filepath=str(picture.resolve()),
                    mode="MartinM1",
                    timestamp=decoded_at,
                    is_received=True,
                    source="spyserver",
                    heard_at="remote",
                )
            )
            session.commit()

        with session_factory() as session:
            ImageImporter(session).update_image_metadata(picture)

        with session_factory() as session:
            row = session.query(SSTVImage).one()
            assert row.timestamp == decoded_at, (
                "the watcher rewrote a decode's time from the filename"
            )
            # Provenance is the decode's to state, and a filename cannot know it.
            assert (row.source, row.heard_at) == ("spyserver", "remote")


class TestTheFilenameAndTheColumnAgree:
    """Amateur radio logs in UTC, and so does SSTVImage.timestamp."""

    def test_saved_filenames_carry_utc(self, tmp_path):
        saver = ImageSaver(base_directory=tmp_path)
        before = datetime.now(timezone.utc).replace(tzinfo=None)
        path = saver.save_image(np.zeros((256, 320, 3), dtype=np.uint8), mode="MartinM1")
        after = datetime.now(timezone.utc).replace(tzinfo=None)

        # sstv_rx_<mode>_<date>_<time>
        stem = Path(path).stem
        date_str, time_str = stem.rsplit("_", 2)[-2:]
        stamped = datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S")
        assert before.replace(microsecond=0) <= stamped <= after, (
            f"{stem} is not a UTC time; a local-time filename parsed back into "
            "the UTC column is what moved a picture by five hours"
        )


def test_image_extensions_still_cover_the_formats_we_save():
    """A guard on the constant the thumbnail rule now reads."""
    assert {".png", ".jpg"} <= IMAGE_EXTENSIONS


class TestTheWatcherFillsGapsAndNeverErases:
    """#168's sting in the tail: FSKID read a callsign and the watcher wiped it.

    The decode adopts a checksum-valid callsign off the air. Our own
    filenames carry no callsign, so re-parsing one and assigning it wrote
    None straight over the radio's answer. Same defect as the timestamp,
    one field over.
    """

    def _decoded_row(self, picture: Path) -> SSTVImage:
        return SSTVImage(
            filename=picture.name,
            filepath=str(picture.resolve()),
            mode="MartinM2",
            callsign="KD2TT",  # read by FSKID, checksum valid
            timestamp=datetime(2026, 9, 12, 3, 54, 17),
            is_received=True,
            source="file",
            fskid_detected=True,
            fskid_checksum_valid=True,
        )

    def test_a_callsign_from_the_air_survives_the_watcher(
        self, tmp_path, session_factory
    ):
        picture = _picture(tmp_path / "sstv_rx_MartinM2_20260912_035417.png")
        with session_factory() as session:
            session.add(self._decoded_row(picture))
            session.commit()

        with session_factory() as session:
            ImageImporter(session).update_image_metadata(picture)

        with session_factory() as session:
            row = session.query(SSTVImage).one()
            assert row.callsign == "KD2TT", "the watcher erased what FSKID heard"
            assert row.mode == "MartinM2"
            assert row.fskid_checksum_valid is True

    def test_a_callsign_in_a_filename_still_fills_an_empty_one(
        self, tmp_path, session_factory
    ):
        """The watcher may still add what nobody knew."""
        picture = _picture(tmp_path / "20260912_035417_MartinM2_VA2PGB.png")
        with session_factory() as session:
            row = self._decoded_row(picture)
            row.callsign = None
            session.add(row)
            session.commit()

        with session_factory() as session:
            ImageImporter(session).update_image_metadata(picture)

        with session_factory() as session:
            assert session.query(SSTVImage).one().callsign == "VA2PGB"

    def test_moving_a_file_does_not_erase_it_either(self, tmp_path, session_factory):
        picture = _picture(tmp_path / "sstv_rx_MartinM2_20260912_035417.png")
        with session_factory() as session:
            session.add(self._decoded_row(picture))
            session.commit()

        moved = tmp_path / "kept" / picture.name
        moved.parent.mkdir()
        picture.rename(moved)
        with session_factory() as session:
            ImageImporter(session).move_image(picture, moved)

        with session_factory() as session:
            row = session.query(SSTVImage).one()
            assert row.callsign == "KD2TT"
            assert row.timestamp == datetime(2026, 9, 12, 3, 54, 17)
