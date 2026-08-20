"""The propagation endpoint, including the failure it must not hide.

An empty propagation panel reads as "nothing to report". The 503 test is
the one that keeps the frontend able to tell "sources down" apart from
"conditions fine" -- the distinction that, when lost, turns a quiet band
into a hardware verdict.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sstv_core.api.main import app
from sstv_core.propagation import SpaceWeatherUnavailableError


@pytest.fixture
def client():
    return TestClient(app)


def test_reports_an_open_band(client, monkeypatch):
    from sstv_core.propagation import space_weather

    monkeypatch.setattr(
        space_weather,
        "fetch_hamqsl",
        lambda timeout=15.0: {
            "k_index": "2",
            "solar_flux": "125",
            "a_index": "8",
            "sunspots": "60",
            "updated": "19 Aug 2026 2200 GMT",
            "bands": {"30m-20m": {"day": "Good", "night": "Fair"}},
        },
    )
    monkeypatch.setattr(space_weather, "fetch_swpc", lambda timeout=15.0: {})

    response = client.get("/api/v1/propagation", params={"band": "20m"})

    assert response.status_code == 200
    body = response.json()
    assert body["state"] in {"OPEN", "CLOSED"}
    assert body["band"] == "20m"
    assert body["k_index"] == "2"
    assert body["wwv_frequencies_hz"] == [5000000, 10000000, 15000000]


def test_unreachable_sources_are_a_503_not_an_empty_report(client, monkeypatch):
    """Silence from the sources must not render as silence from the sun."""
    from sstv_core.api.routes import propagation as route

    def _boom(band="20m", timeout=15.0):
        raise SpaceWeatherUnavailableError("I couldn't reach either space weather source.")

    monkeypatch.setattr(route, "fetch_report", _boom)

    response = client.get("/api/v1/propagation")

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["error"] == "space_weather_unavailable"
    assert "suggested_action" in detail
    assert "inconclusive" in detail["suggested_action"]


def test_storm_state_is_reported(client, monkeypatch):
    from sstv_core.propagation import space_weather

    monkeypatch.setattr(
        space_weather,
        "fetch_hamqsl",
        lambda timeout=15.0: {
            "k_index": "6",
            "solar_flux": "140",
            "bands": {"30m-20m": {"day": "Good", "night": "Good"}},
        },
    )
    monkeypatch.setattr(space_weather, "fetch_swpc", lambda timeout=15.0: {})

    response = client.get("/api/v1/propagation", params={"band": "20m"})

    assert response.status_code == 200
    assert response.json()["state"] == "STORM"
