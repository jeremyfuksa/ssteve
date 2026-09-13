"""A control reports what the decode is using, not what it was asked for.

`PATCH /decode/{id}` answered with `{"applied": <the request>}` -- the
reply restated the question. A setter that clamped, or a source that could
not take the change, still produced "applied" for a change that had not
happened, and the shell rendered that as success.

An operator moves gain or squelch during QSB or contest QRM because the
picture is already in trouble (PRODUCT.md #3). A control that reports its
own wish back is worse than no control: it removes the one signal that
would send them to look elsewhere.

`applied` is now read back from the running decode. Today every source
ships a gain stage and nothing clamps, so the read-back and the request
agree -- which is the cheapest possible moment to make the reply mean what
it says rather than waiting for the first setter that disagrees.

The fake below clamps on purpose. That is how these tests can tell a
read-back from an echo at all: with a truthful engine the two are
identical, and a test where they are identical proves nothing.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from sstv_core.api import dsp_manager as dsp_module
from sstv_core.api.main import app

client = TestClient(app)


class FakeRX:
    """A decode whose settings can disagree with what it was told.

    No shipped source behaves this way -- that is the point. If the reply
    is an echo, it agrees with the request no matter what the decode did,
    and only a decode that deliberately disagrees can tell the difference.
    """

    def __init__(self, *, takes_gain: bool = True, ceiling: float | None = None):
        self._ceiling = ceiling
        self._auto_squelch = False
        self._squelch_threshold_db = -40.0
        self._auto_afc = False
        self._afc_range_hz = 0.0
        self._gain: float | None = 1.0 if takes_gain else None
        self._takes_gain = takes_gain

    def set_input_gain(self, gain: float | None) -> None:
        if not self._takes_gain:
            return
        if gain is not None and self._ceiling is not None:
            gain = min(gain, self._ceiling)
        self._gain = gain

    def set_squelch(self, auto=None, threshold_db=None) -> None:
        if auto is not None:
            self._auto_squelch = auto
        if threshold_db is not None:
            self._squelch_threshold_db = threshold_db

    def set_afc(self, auto=None, range_hz=None) -> None:
        if auto is not None:
            self._auto_afc = auto
        if range_hz is not None:
            self._afc_range_hz = range_hz

    def settings_in_force(self) -> dict:
        return {
            "input_gain": self._gain,
            "auto_squelch": self._auto_squelch,
            "squelch_threshold_db": self._squelch_threshold_db,
            "auto_afc": self._auto_afc,
            "afc_range_hz": self._afc_range_hz,
        }


@pytest.fixture
def a_decode(monkeypatch):
    """Install a fake decode and hand back a way to choose its behaviour."""

    def install(**kwargs):
        rx = FakeRX(**kwargs)
        monkeypatch.setattr(
            dsp_module.dsp_manager, "get_rx_manager", lambda _id: rx
        )
        return rx

    return install


def test_a_change_that_took_reads_back_as_itself(a_decode):
    a_decode()

    response = client.patch(f"/api/v1/decode/{uuid4()}", json={"input_gain": 1.5})

    assert response.status_code == 200
    assert response.json()["applied"] == {"input_gain": 1.5}


def test_a_clamped_change_reports_the_clamped_value(a_decode):
    a_decode(ceiling=1.2)

    response = client.patch(f"/api/v1/decode/{uuid4()}", json={"input_gain": 2.0})

    body = response.json()
    assert body["applied"] == {"input_gain": 1.2}, (
        "the reply repeated the request instead of reading the decode"
    )


def test_one_control_moving_does_not_report_another(a_decode):
    a_decode()

    body = client.patch(
        f"/api/v1/decode/{uuid4()}", json={"auto_squelch": True}
    ).json()

    assert body["applied"] == {"auto_squelch": True}
    assert "input_gain" not in body["applied"], (
        "a client moving one control must not be told about another"
    )


def test_the_real_rx_manager_reports_its_own_settings():
    """The fake above is only honest if the real one has this shape."""
    from sstv_core.decode.rx_manager import RXManager

    rx = RXManager(stream_manager=SimpleNamespace(input_gain=1.75))

    in_force = rx.settings_in_force()

    assert in_force["input_gain"] == 1.75
    assert set(in_force) == {
        "input_gain",
        "auto_squelch",
        "squelch_threshold_db",
        "auto_afc",
        "afc_range_hz",
    }
