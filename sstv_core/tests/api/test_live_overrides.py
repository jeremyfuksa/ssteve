"""Adjusting gain, squelch and AFC without losing the signal (#56).

`dsp_manager` read decode config once at session start, `RXManager`
stored squelch and AFC with no setters, and there was no
`PATCH /decode/{id}`. Changing `/config` mid-decode did nothing until the
next session, so an operator had to stop, patch, restart -- and lose the
transmission they were trying to rescue.

PRODUCT.md #3 is explicit about why these three stay reachable: input
gain auto-detect fails on QSB, auto-only AFC is dangerous for satellite
Doppler work, and auto squelch fails in contest QRM. Every one of those
is a mid-transmission problem, which is exactly when a restart is the
one thing an operator cannot afford.
"""

from __future__ import annotations

import pytest


def _manager():
    from sstv_core.decode.rx_manager import RXManager

    class _NoStream:
        def get_input_levels(self) -> None:
            return None

    return RXManager(stream_manager=_NoStream())


class TestSetters:
    def test_squelch_can_be_changed_live(self) -> None:
        manager = _manager()
        manager.set_squelch(auto=False, threshold_db=-45.0)

        assert manager._auto_squelch is False
        assert manager._squelch_threshold_db == -45.0

    def test_afc_can_be_changed_live(self) -> None:
        """The satellite case: Doppler makes auto-only AFC dangerous."""
        manager = _manager()
        manager.set_afc(auto=False, range_hz=200.0)

        assert manager._auto_afc is False
        assert manager._afc_range_hz == 200.0

    def test_a_partial_change_leaves_the_rest_alone(self) -> None:
        """An operator adjusting the threshold must not silently flip
        auto off as a side effect."""
        manager = _manager()
        before = manager._auto_squelch

        manager.set_squelch(threshold_db=-50.0)

        assert manager._auto_squelch is before
        assert manager._squelch_threshold_db == -50.0

    def test_gain_reaches_the_source(self) -> None:
        """RXManager holds the source; the slider has to get through it."""
        seen: list[float | None] = []

        class _Stream:
            def get_input_levels(self) -> None:
                return None

            def set_input_gain(self, gain: float | None) -> None:
                seen.append(gain)

        from sstv_core.decode.rx_manager import RXManager

        RXManager(stream_manager=_Stream()).set_input_gain(1.5)

        assert seen == [1.5]

    def test_a_source_without_gain_support_does_not_crash(self) -> None:
        """A file-backed or test source has no gain stage. Adjusting it
        should be a no-op, not an exception mid-decode."""
        _manager().set_input_gain(1.5)


class TestThePatchEndpoint:
    @staticmethod
    def _client():
        from fastapi.testclient import TestClient

        from sstv_core.api.main import app

        return TestClient(app)

    def test_the_route_exists(self) -> None:
        """PATCH on an unknown session is 404, not 405.

        405 would mean no PATCH route at all -- which is how this looked
        before, and why the operator had to restart.
        """
        from uuid import uuid4

        response = self._client().patch(
            f"/api/v1/decode/{uuid4()}", json={"input_gain": 1.2}
        )

        assert response.status_code != 405, (
            "no PATCH route, so nothing can be adjusted without a restart"
        )
        assert response.status_code == 404

    def test_an_unknown_session_explains_itself(self) -> None:
        from uuid import uuid4

        response = self._client().patch(
            f"/api/v1/decode/{uuid4()}", json={"input_gain": 1.2}
        )
        detail = response.json()["detail"]

        assert "error" in detail, "clients need a code, not prose to match on"
        assert "message" in detail

    @pytest.mark.parametrize("gain", [-0.5, 3.0])
    def test_an_out_of_range_gain_is_refused(self, gain: float) -> None:
        """0.0-2.0 matches `input_gain_override`'s config bounds. A typo
        that reaches the multiplier is a blown-out buffer."""
        from uuid import uuid4

        response = self._client().patch(
            f"/api/v1/decode/{uuid4()}", json={"input_gain": gain}
        )

        assert response.status_code == 422

    def test_an_empty_patch_is_refused(self) -> None:
        """Nothing to change is a mistake worth naming, not a silent 200."""
        from uuid import uuid4

        response = self._client().patch(f"/api/v1/decode/{uuid4()}", json={})

        assert response.status_code in (400, 404, 422)
