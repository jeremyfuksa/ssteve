"""Runtime shape of the qso/smart_reply errors normalized by #74.

test_error_shape_contract.py proves the source has no bare strings; these
drive the endpoints and assert what a client actually receives. Both files
had zero route-level error coverage before 2026-08-09, which is why
converting them broke nothing and proved nothing.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from sstv_core.api.main import app
from sstv_core.api.routes import qso as qso_routes
from sstv_core.api.routes import smart_reply as smart_reply_routes

client = TestClient(app)

# POST /smart_reply/transmit/{id} requires a body; without one FastAPI
# returns 422 before the route's own 404 for an expired preview.
_TRANSMIT_BODY = {"mode": "ScottieS1", "device_id": "default", "ptt_method": "none"}


@contextmanager
def _db(module, session):
    """Override a route module's get_db for the duration of a request."""
    app.dependency_overrides[module.get_db] = lambda: session
    try:
        yield
    finally:
        app.dependency_overrides.pop(module.get_db, None)


def _assert_structured(detail, expected_error: str) -> None:
    assert isinstance(detail, dict), f"detail is {type(detail)}, not the structured object"
    assert detail["error"] == expected_error, detail
    assert detail["message"], "message is empty"
    assert "SSTVMode." not in detail["message"], detail["message"]


class TestQSOErrors:
    def test_missing_qso_returns_structured_404(self):
        session = MagicMock()
        session.get.return_value = None

        with _db(qso_routes, session):
            response = client.get("/api/v1/qso/424242")

        assert response.status_code == 404
        detail = response.json()["detail"]
        _assert_structured(detail, "QSO_NOT_FOUND")
        assert detail["suggested_action"], "operator given no way forward"

    def test_delete_missing_qso_returns_structured_404(self):
        session = MagicMock()
        session.get.return_value = None

        with _db(qso_routes, session):
            response = client.delete("/api/v1/qso/424242")

        assert response.status_code == 404
        _assert_structured(response.json()["detail"], "QSO_NOT_FOUND")

    def test_adif_export_failure_returns_structured_500(self):
        session = MagicMock()
        session.query.side_effect = RuntimeError("db went away")

        with _db(qso_routes, session):
            response = client.get("/api/v1/qso/export")

        assert response.status_code == 500
        detail = response.json()["detail"]
        _assert_structured(detail, "ADIF_EXPORT_FAILED")
        assert "db went away" in detail["message"], "underlying cause was swallowed"


class TestSmartReplyErrors:
    def test_unknown_image_returns_structured_404(self):
        session = MagicMock()
        session.get.return_value = None
        session.query.return_value.filter.return_value.first.return_value = None

        with _db(smart_reply_routes, session):
            response = client.post(
                "/api/v1/smart_reply/generate",
                json={
                    "image_id": "00000000-0000-0000-0000-0000000000ff",
                    "template_name": "standard",
                },
            )

        # 404 for the missing image; 422 would mean the body shape drifted.
        assert response.status_code == 404, response.json()
        detail = response.json()["detail"]
        _assert_structured(detail, "IMAGE_NOT_FOUND")
        assert detail["suggested_action"]

    def test_unknown_preview_returns_structured_404(self):
        """Previews are short-lived; transmitting an expired one must explain."""
        session = MagicMock()
        session.get.return_value = None
        with _db(smart_reply_routes, session):
            response = client.post(
                "/api/v1/smart_reply/transmit/00000000-0000-0000-0000-0000000000ff",
                json=_TRANSMIT_BODY,
            )
        assert response.status_code == 404, response.json()
        detail = response.json()["detail"]
        _assert_structured(detail, "PREVIEW_NOT_FOUND")
        assert detail["suggested_action"]


class TestImportErrorsStayStructured:
    """import_routes had coverage already; keep it pinned to the new shape."""

    def test_missing_directory(self):
        session = MagicMock()
        with _db(__import__(
            "sstv_core.api.routes.import_routes", fromlist=["x"]
        ), session):
            response = client.post(
                "/api/v1/import/mmsstv",
                json={"directory_path": "/nonexistent/library"},
            )
        assert response.status_code == 404
        detail = response.json()["detail"]
        _assert_structured(detail, "DIRECTORY_NOT_FOUND")
        assert "/nonexistent/library" in detail["message"]


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/v1/qso/424242"),
        ("delete", "/api/v1/qso/424242"),
        ("post", "/api/v1/smart_reply/transmit/00000000-0000-0000-0000-0000000000ff"),
    ],
)
def test_error_bodies_are_never_bare_strings(method, path):
    """The single property the frontend's error component depends on."""
    session = MagicMock()
    session.get.return_value = None
    body = _TRANSMIT_BODY if "smart_reply" in path else None
    with _db(qso_routes, session), _db(smart_reply_routes, session):
        response = getattr(client, method)(path, json=body) if body else getattr(client, method)(path)
    assert response.status_code >= 400
    assert isinstance(response.json()["detail"], dict), response.json()
