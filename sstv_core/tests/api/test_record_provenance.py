"""Every record says where it was heard (#69, PRODUCT.md requirement 12).

The failure this file guards against escapes SSTeVe: a remote reception
exported as a contact lands in LoTW, eQSL or Club Log as a QSO that never
happened, in infrastructure other operators depend on. So the ADIF tests
check the file that comes out, not a flag on the way.

airspy.local is the owner's own receiver, reached over SpyServer. That is
why "remote" is decided per server, never by transport.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from sstv_core.api import dsp_manager as dsp_module
from sstv_core.api.dsp_manager import DSPManager, station_key
from sstv_core.api.image_ids import db_image_id_to_uuid
from sstv_core.api.main import app, get_db_session
from sstv_core.api.models import DecodeState
from sstv_core.api.session_manager import session_manager
from sstv_core.database.models import QSO, QSOImage, SSTVImage, init_database
from sstv_core.smart_features.qso_logger import (
    RecordTypeError,
    _format_qso_as_adif,
    export_qsos_to_adif,
    record_type_for,
)


class TestStationKey:
    @pytest.mark.parametrize(
        ("entry", "expected"),
        [
            ("airspy.local:5555", "airspy.local:5555"),
            ("Airspy.Local:5555", "airspy.local:5555"),
            ("airspy.local", "airspy.local:5555"),
            (" airspy.local:5556 ", "airspy.local:5556"),
        ],
    )
    def test_differences_an_operator_would_not_call_a_different_server(
        self, entry, expected
    ):
        assert station_key(entry) == expected

    def test_an_ip_is_not_its_hostname(self):
        # Mismatch reads as remote -- the direction that only withholds.
        assert station_key("192.168.1.30:5555") != station_key("airspy.local:5555")


# ---------------------------------------------------------------------------
# Provenance written at decode time
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path):
    _, session_factory = init_database(db_path=tmp_path / "prov.db")
    return session_factory


async def _decode_one(db, monkeypatch, tmp_path, *, my_stations, **start) -> SSTVImage:
    """Run a decode that produces one picture, and return its row."""
    from PIL import Image

    picture = tmp_path / "decoded.png"
    Image.new("RGB", (320, 256)).save(picture)

    class Source:
        sample_rate = 48_000
        stream_failure = None

        def __init__(self, **kwargs):
            pass

    class OnePictureRX:
        def __init__(self, *args, **kwargs):
            pass

        def set_progress_callback(self, cb):
            pass

        async def receive(self, **kwargs):
            return picture

        async def cancel(self):
            pass

        def get_decode_metrics(self):
            return None

        def get_fskid_result(self):
            return None

    async def broadcast(session_id, payload):
        pass

    async def stored():
        return {
            "host": "airspy.local",
            "port": 5555,
            "frequency_hz": 14_230_000,
            "gain": None,
            "stall_timeout_sec": 5.0,
            "my_stations": my_stations,
        }

    monkeypatch.setattr(dsp_module, "SpyServerSource", Source)
    monkeypatch.setattr(dsp_module, "RXManager", OnePictureRX)
    monkeypatch.setattr(dsp_module.websocket_manager, "broadcast", broadcast)

    manager = DSPManager(db_session_factory=db)
    manager._device_manager_instance = SimpleNamespace(get_device_index=lambda _id: None)
    monkeypatch.setattr(manager, "_read_spyserver_config", stored)

    session = await session_manager.create_decode_session(metadata={"mode": "ScottieS1"})
    try:
        await manager.start_decode(
            session_id=session.session_id,
            mode=None,
            auto_detect=True,
            timeout_seconds=5.0,
            save_image=True,
            callsign=None,
            device_id=None,
            **start,
        )
        for _ in range(40):
            await asyncio.sleep(0.05)
            data = await session_manager.get_decode_session(session.session_id)
            if data and data.state == DecodeState.COMPLETED.value:
                break
    finally:
        session_manager.reset()

    with db() as s:
        row = s.query(SSTVImage).one()
        s.expunge(row)
        return row


class TestProvenanceAtDecode:
    @pytest.mark.asyncio
    async def test_someone_elses_server_is_remote(self, db, monkeypatch, tmp_path):
        row = await _decode_one(
            db, monkeypatch, tmp_path, my_stations=[], source="spyserver", band="20m"
        )
        assert (row.source, row.receiver, row.heard_at) == (
            "spyserver",
            "airspy.local:5555",
            "remote",
        )
        assert row.frequency_hz == 14_230_000

    @pytest.mark.asyncio
    async def test_your_own_server_is_your_station(self, db, monkeypatch, tmp_path):
        row = await _decode_one(
            db,
            monkeypatch,
            tmp_path,
            my_stations=["AIRSPY.local"],  # case and default port normalize
            source="spyserver",
        )
        assert row.heard_at == "my_station"
        assert row.receiver == "airspy.local:5555"

    @pytest.mark.asyncio
    async def test_sound_card_is_your_station(self, db, monkeypatch, tmp_path):
        row = await _decode_one(db, monkeypatch, tmp_path, my_stations=[])
        assert (row.source, row.receiver, row.heard_at) == ("audio", None, "my_station")


# ---------------------------------------------------------------------------
# What a picture may be logged as
# ---------------------------------------------------------------------------


def _image(**provenance) -> SSTVImage:
    return SSTVImage(filename="x.png", filepath="/x.png", mode="ScottieS1", **provenance)


class TestRecordTypeRules:
    def test_remote_defaults_to_remote_reception(self):
        image = _image(source="spyserver", receiver="berlin.example:5555", heard_at="remote")
        assert record_type_for(image, None) == "remote_reception"

    @pytest.mark.parametrize("claim", ["qso", "reception_report"])
    def test_remote_cannot_be_claimed_as_your_own(self, claim):
        image = _image(source="spyserver", receiver="berlin.example:5555", heard_at="remote")
        with pytest.raises(RecordTypeError, match="berlin.example") as exc:
            record_type_for(image, claim)
        assert "spyserver_my_stations" in exc.value.suggested_action

    def test_your_station_defaults_to_a_contact(self):
        assert record_type_for(_image(source="audio", heard_at="my_station"), None) == "qso"

    def test_your_station_can_be_a_reception_report(self):
        image = _image(source="audio", heard_at="my_station")
        assert record_type_for(image, "reception_report") == "reception_report"

    def test_unknown_provenance_keeps_todays_behavior(self):
        assert record_type_for(_image(), None) == "qso"

    def test_a_sample_is_not_a_reception(self):
        with pytest.raises(RecordTypeError, match="sample"):
            record_type_for(_image(source="sample"), None)


# ---------------------------------------------------------------------------
# The ADIF block
# ---------------------------------------------------------------------------


def _seed_log(db) -> None:
    with db() as s:
        for n, (call, record_type, heard_at) in enumerate(
            [
                ("W1AW", "qso", "my_station"),
                ("K0SWL", "reception_report", "my_station"),
                ("DL1REM", "remote_reception", "remote"),
            ]
        ):
            image = _image(heard_at=heard_at)
            image.filepath = f"/log/{n}.png"
            qso = QSO(
                callsign=call,
                mode="ScottieS1",
                start_time=datetime(2026, 9, 11, 12, n),
                record_type=record_type,
            )
            s.add_all([image, qso])
            s.flush()
            s.add(QSOImage(qso_id=qso.id, image_id=image.id))
        s.commit()


class TestADIFBlock:
    def test_export_carries_contacts_only(self, db):
        _seed_log(db)
        with db() as s:
            adif = export_qsos_to_adif(s)
        assert "W1AW" in adif
        assert "K0SWL" not in adif, "a reception report is not a contact"
        assert "DL1REM" not in adif, "a remote reception became a QSO"
        assert adif.count("<EOR>") == 1

    def test_formatter_refuses_a_remote_reception_on_its_own(self, db):
        """The block holds for a caller that skips the export's filter."""
        _seed_log(db)
        with db() as s:
            remote = s.query(QSO).filter_by(callsign="DL1REM").one()
            with pytest.raises(ValueError, match="not a contact"):
                _format_qso_as_adif(remote)

    def test_formatter_refuses_a_contact_carrying_a_remote_picture(self, db):
        _seed_log(db)
        with db() as s:
            qso = s.query(QSO).filter_by(callsign="W1AW").one()
            qso.images[0].heard_at = "remote"
            with pytest.raises(ValueError, match="someone else's"):
                _format_qso_as_adif(qso)


# ---------------------------------------------------------------------------
# Over the API
# ---------------------------------------------------------------------------


@pytest.fixture
def remote_image(tmp_path):
    from PIL import Image

    image_file = tmp_path / "remote.png"
    Image.new("RGB", (320, 256)).save(image_file)
    generator = get_db_session()
    session = next(generator)
    try:
        row = SSTVImage(
            filename="remote.png",
            filepath=str(image_file),
            mode="ScottieS1",
            callsign="DL1REM",
            is_received=True,
            source="spyserver",
            receiver="berlin.example:5555",
            heard_at="remote",
        )
        session.add(row)
        session.commit()
        db_id = row.id
        yield db_image_id_to_uuid(db_id)
        for link in session.query(QSOImage).filter_by(image_id=db_id).all():
            session.delete(session.get(QSO, link.qso_id))
        session.delete(session.get(SSTVImage, db_id))
        session.commit()
    finally:
        generator.close()


class TestOverTheAPI:
    def test_image_row_carries_its_provenance(self, remote_image):
        body = TestClient(app).get(f"/api/v1/images/{remote_image}").json()
        assert body["source"] == "spyserver"
        assert body["receiver"] == "berlin.example:5555"
        assert body["heard_at"] == "remote"

    def test_images_filter_by_source(self, remote_image):
        client = TestClient(app)
        ids = [i["id"] for i in client.get("/api/v1/images?source=spyserver").json()["images"]]
        assert str(remote_image) in ids
        ids = [i["id"] for i in client.get("/api/v1/images?source=audio").json()["images"]]
        assert str(remote_image) not in ids

    def test_claiming_a_remote_picture_as_a_contact_is_refused(self, remote_image):
        response = TestClient(app).post(
            "/api/v1/qso/log",
            json={"image_id": str(remote_image), "record_type": "qso"},
        )
        assert response.status_code == 400, response.text
        detail = response.json()["detail"]
        assert detail["error"] == "RECORD_TYPE_NOT_ALLOWED"
        assert "berlin.example" in detail["message"]

    def test_remote_picture_logs_as_remote_reception_and_never_exports(
        self, remote_image
    ):
        client = TestClient(app)
        response = client.post("/api/v1/qso/log", json={"image_id": str(remote_image)})
        assert response.status_code == 201, response.text
        assert response.json()["record_type"] == "remote_reception"

        listed = client.get("/api/v1/qso/list?record_type=remote_reception").json()
        assert [q["callsign"] for q in listed["qsos"]] == ["DL1REM"]

        adif = client.get("/api/v1/qso/export").text
        assert "DL1REM" not in adif

