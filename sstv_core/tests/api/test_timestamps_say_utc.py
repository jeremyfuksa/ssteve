"""A timestamp on the wire must say which clock it is on.

The database stores UTC as naive datetimes. Served unlabelled, a naive ISO
string means *local time* to every client that parses one, so the desktop
shell showed a picture decoded at 21:14 local as 2:14 AM. The stored value
was right; the wire format did not say what it was.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from sstv_core.api.image_ids import db_image_id_to_uuid
from sstv_core.api.main import app, get_db_session
from sstv_core.api.timestamps import as_utc
from sstv_core.database.models import QSO, SSTVImage

DECODED_AT = datetime(2026, 9, 12, 2, 14, 27)  # UTC, as the column stores it


@pytest.fixture
def seeded(tmp_path):
    image_file = tmp_path / "rx.png"
    Image.new("RGB", (320, 256)).save(image_file)
    generator = get_db_session()
    session = next(generator)
    try:
        row = SSTVImage(
            filename="rx.png",
            filepath=str(image_file),
            mode="MartinM2",
            timestamp=DECODED_AT,
            is_received=True,
        )
        qso = QSO(
            callsign="KD2TT", mode="MartinM2", start_time=DECODED_AT, record_type="qso"
        )
        session.add_all([row, qso])
        session.commit()
        yield db_image_id_to_uuid(row.id), qso.id
        session.delete(session.get(SSTVImage, row.id))
        session.delete(session.get(QSO, qso.id))
        session.commit()
    finally:
        generator.close()


class TestAsUtc:
    def test_a_stored_naive_time_is_labelled_not_shifted(self):
        labelled = as_utc(DECODED_AT)
        assert labelled.tzinfo is timezone.utc
        assert labelled.hour == 2, "the instant moved; only the label should change"

    def test_an_aware_time_survives(self):
        aware = DECODED_AT.replace(tzinfo=timezone.utc)
        assert as_utc(aware) == aware

    def test_none_stays_none(self):
        assert as_utc(None) is None


class TestOverTheWire:
    def test_an_image_says_utc(self, seeded):
        image_id, _ = seeded
        body = TestClient(app).get(f"/api/v1/images/{image_id}").json()

        assert body["timestamp"].endswith(("Z", "+00:00")), body["timestamp"]
        # The instant itself is unchanged: a client reading this gets 02:14 UTC.
        assert datetime.fromisoformat(body["timestamp"]).astimezone(timezone.utc).hour == 2

    def test_a_qso_says_utc(self, seeded):
        _, qso_id = seeded
        # As a context manager: the QSO router's database dependency is wired
        # during app startup, and without lifespan this test only passed when
        # some earlier test had already started the app.
        with TestClient(app) as client:
            body = client.get(f"/api/v1/qso/{qso_id}").json()

        assert body["start_time"].endswith(("Z", "+00:00")), body["start_time"]

    def test_the_list_says_utc_too(self, seeded):
        rows = TestClient(app).get("/api/v1/images?limit=5").json()["images"]

        assert rows, "nothing to check"
        assert all(row["timestamp"].endswith(("Z", "+00:00")) for row in rows)
