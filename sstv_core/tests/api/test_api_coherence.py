"""API coherence: public image IDs bridge, real smart-reply transmit,
no fabricated data.

The audit found the API exposed images as one-way UUIDs while /qso and
/smart_reply demanded raw integer keys no endpoint returned; smart-reply
transmit fabricated a tx_id that 404'd on status; and several routes
served invented data (320x256 dims, MartinM1 fallbacks, quality scores
labeled dB).
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from sstv_core.api.image_ids import db_image_id_to_uuid
from sstv_core.api.main import app, get_db_session
from sstv_core.database.models import SSTVImage


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def seeded_image(tmp_path):
    """A real image row + file in the app's test database."""
    from PIL import Image

    image_file = tmp_path / "rx.png"
    Image.new("RGB", (320, 256), (10, 20, 30)).save(image_file)

    generator = get_db_session()
    session = next(generator)
    try:
        row = SSTVImage(
            filename="rx.png",
            filepath=str(image_file),
            mode="ScottieS1",
            callsign="K0ABC",
            timestamp=datetime(2026, 8, 7, 12, 0),
            is_received=True,
            rx_snr_db=17.0,
            rx_quality_score=0.9,
            frequency_hz=14230000.0,
        )
        session.add(row)
        session.commit()
        db_id = row.id
        yield db_image_id_to_uuid(db_id), db_id
        session.delete(session.get(SSTVImage, db_id))
        session.commit()
    finally:
        generator.close()


class TestImageIdBridge:
    def test_qso_log_accepts_public_uuid(self, client, seeded_image):
        public_id, _ = seeded_image
        response = client.post(
            "/api/v1/qso/log",
            json={"image_id": str(public_id), "callsign": "K0ABC"},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["callsign"] == "K0ABC"
        assert body["image_ids"] == [str(public_id)]

    def test_qso_log_unknown_uuid_404s(self, client):
        response = client.post(
            "/api/v1/qso/log",
            json={
                "image_id": "00000000-0000-0000-0000-000000000001",
                "callsign": "K0ABC",
            },
        )
        assert response.status_code == 404

    def test_smart_reply_generate_accepts_public_uuid(self, client, seeded_image):
        public_id, _ = seeded_image
        response = client.post(
            "/api/v1/smart_reply/generate",
            json={
                "image_id": str(public_id),
                "template_id": "qsl_card",
                "field_overrides": {"callsign_operator": "W1XYZ"},
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["preview_id"]

    def test_images_route_serves_honest_metadata(self, client, seeded_image):
        public_id, _ = seeded_image
        response = client.get(f"/api/v1/images/{public_id}")
        assert response.status_code == 200
        body = response.json()
        # Real dims from the real file; dB from the dB column.
        assert body["width"] == 320 and body["height"] == 256
        assert body["snr_db"] == 17.0
        assert body["frequency_hz"] == 14230000.0


class TestSmartReplyTransmitIsReal:
    def test_transmit_creates_a_real_session(self, client, seeded_image, mock_dsp_manager):
        public_id, _ = seeded_image
        generated = client.post(
            "/api/v1/smart_reply/generate",
            json={
                "image_id": str(public_id),
                "template_id": "qsl_card",
                "field_overrides": {"callsign_operator": "W1XYZ"},
            },
        )
        assert generated.status_code == 200, generated.text
        preview_id = generated.json()["preview_id"]

        response = client.post(
            f"/api/v1/smart_reply/transmit/{preview_id}",
            json={"mode": "ScottieS1", "device_id": "0", "ptt_method": "vox"},
        )
        assert response.status_code == 200, response.text
        tx_id = response.json()["tx_id"]

        # The fabricated implementation returned an ID that 404'd here.
        status_response = client.get(f"/api/v1/transmit/status/{tx_id}")
        assert status_response.status_code == 200
        assert status_response.json()["mode"] == "ScottieS1"
        # The DSP bridge was actually invoked with the preview image.
        mock_dsp_manager.start_transmit.assert_called_once()

        # Release the half-duplex slot for subsequent tests.
        client.post(f"/api/v1/transmit/cancel/{tx_id}")
