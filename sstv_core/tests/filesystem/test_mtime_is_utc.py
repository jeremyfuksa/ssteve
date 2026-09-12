"""An imported picture's timestamp is UTC, not the importer's wall clock.

Found by dropping a PNG into the watched library with the desktop window
open. The file's mtime was 17:41:32 CDT; the log card said 17:41:32Z.
Real UTC at that moment was 22:41:32, so the picture was recorded as heard
five hours before it was -- and a timestamp is not decoration here. It goes
into the log, and into anything exported from it, as a claim about when a
contact happened.

The cause was two branches of one `try` following two different
conventions, four lines apart: `datetime.fromtimestamp(mtime)` with no tz
returns *local* naive time, while the `except` branch below it already
said "Naive UTC, matching the database timestamp convention".

These tests run under a fixed non-UTC zone on purpose. Under TZ=UTC the
bug does not reproduce at all -- local and UTC agree -- which is exactly
why every existing test and every CI run missed it.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from PIL import Image

from sstv_core.filesystem.importer import parse_image_metadata

#: Five hours behind UTC in September, and never zero at any time of year,
#: so the assertion below cannot pass by coincidence of season.
A_ZONE_THAT_IS_NOT_UTC = "America/Chicago"


@pytest.fixture
def in_a_non_utc_timezone():
    """Run the body as a machine that is not on UTC, then put it back."""
    previous = os.environ.get("TZ")
    os.environ["TZ"] = A_ZONE_THAT_IS_NOT_UTC
    time.tzset()
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous
        time.tzset()


@pytest.fixture
def a_picture(tmp_path: Path) -> Path:
    # A name with no date in it. `_parse_filename` reads a timestamp out of
    # the SSTeVe naming convention, and a file called
    # 2026-09-12_224200_MartinM1.png never reaches the mtime fallback at
    # all -- which would have made this whole test vacuous.
    path = tmp_path / "a-picture-from-somewhere-else.png"
    Image.new("RGB", (320, 256), (20, 30, 40)).save(path)
    return path


def test_the_stored_time_is_the_moment_it_happened(in_a_non_utc_timezone, a_picture):
    # A known instant, so the expected answer is arithmetic rather than
    # whatever the clock happens to say.
    heard = datetime(2026, 9, 12, 22, 41, 32, tzinfo=timezone.utc)
    os.utime(a_picture, (heard.timestamp(), heard.timestamp()))

    metadata = parse_image_metadata(a_picture)

    assert metadata["timestamp"] == heard.replace(tzinfo=None), (
        "the importer recorded its own wall clock, not the time the file was "
        f"written: got {metadata['timestamp']}, expected {heard}"
    )


def test_it_does_not_drift_with_the_machine(a_picture):
    """The same file, read from two zones, is the same moment.

    A timestamp that depends on who imported it is worse than a missing
    one: it looks authoritative.
    """
    heard = datetime(2026, 9, 12, 22, 41, 32, tzinfo=timezone.utc)
    os.utime(a_picture, (heard.timestamp(), heard.timestamp()))

    readings = []
    previous = os.environ.get("TZ")
    try:
        for zone in ("UTC", A_ZONE_THAT_IS_NOT_UTC, "Asia/Tokyo"):
            os.environ["TZ"] = zone
            time.tzset()
            readings.append(parse_image_metadata(a_picture)["timestamp"])
    finally:
        if previous is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous
        time.tzset()

    assert len(set(readings)) == 1, f"three zones, three answers: {readings}"
