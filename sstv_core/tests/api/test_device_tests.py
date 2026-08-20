"""Proving the audio and PTT chain before transmitting (#59).

PRODUCT.md calls audio routing and levels a manufactured difficulty, and
these two controls are what defuse it: an operator can confirm the radio
keys and that sound reaches it, before ever putting a signal on the air.
`ptt_controller.py` had the keying primitives and no API surface, and
`stream_manager.py` could open an output stream that `routes/devices.py`
never exercised.

Both are onboarding-critical and both must fail *legibly*: the whole
point is diagnosing a chain that does not work yet, so an error that says
only "failed" wastes the one moment the operator is looking for a reason.
"""

from __future__ import annotations

import numpy as np
import pytest

from sstv_core.audio.tone import TEST_TONE_HZ, generate_test_tone

RATE = 48_000


class TestTheTestTone:
    def test_it_is_1900_hz(self) -> None:
        """The SSTV centre frequency (ITU). Any tone proves audio flows,
        but this one also lands where the passband should be, so a
        misrouted or filtered path shows up as well."""
        assert TEST_TONE_HZ == 1900.0

    def test_it_has_the_length_asked_for(self) -> None:
        tone = generate_test_tone(duration_sec=0.5, sample_rate=RATE)

        assert len(tone) == pytest.approx(RATE * 0.5, abs=RATE * 0.01)

    def test_it_is_float32_in_range(self) -> None:
        tone = generate_test_tone(duration_sec=0.2, sample_rate=RATE)

        assert tone.dtype == np.float32
        assert float(np.abs(tone).max()) <= 1.0

    def test_the_frequency_is_actually_1900(self) -> None:
        """Generating the wrong tone would still 'work' audibly, and
        quietly invalidate the passband half of the check."""
        tone = generate_test_tone(duration_sec=1.0, sample_rate=RATE)
        spectrum = np.abs(np.fft.rfft(tone * np.hanning(len(tone))))
        peak_hz = float(np.fft.rfftfreq(len(tone), 1 / RATE)[np.argmax(spectrum)])

        assert peak_hz == pytest.approx(TEST_TONE_HZ, abs=5.0)

    def test_it_fades_in_and_out(self) -> None:
        """A tone that starts at full amplitude clicks, and a click is
        broadband -- it would key VOX and stress a PA for no reason."""
        tone = generate_test_tone(duration_sec=0.3, sample_rate=RATE)

        assert abs(float(tone[0])) < 0.01, "starts with a click"
        assert abs(float(tone[-1])) < 0.01, "ends with a click"

    def test_a_zero_duration_is_refused(self) -> None:
        with pytest.raises(ValueError):
            generate_test_tone(duration_sec=0.0, sample_rate=RATE)

    def test_an_absurd_duration_is_refused(self) -> None:
        """A test tone is a check, not a transmission. Ten seconds of
        carrier into a radio that is keyed is a real-world consequence."""
        with pytest.raises(ValueError):
            generate_test_tone(duration_sec=60.0, sample_rate=RATE)


class TestTheEndpoints:
    @staticmethod
    def _client():
        from fastapi.testclient import TestClient

        from sstv_core.api.main import app

        return TestClient(app)

    def test_test_ptt_route_exists(self) -> None:
        response = self._client().get("/api/v1/devices/test_ptt")

        assert response.status_code == 405, (
            "no test_ptt endpoint, so nothing can prove the radio keys"
        )

    def test_test_tone_route_exists(self) -> None:
        response = self._client().get("/api/v1/devices/test_tone")

        assert response.status_code == 405

    def test_ptt_failure_says_what_to_do(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The error is the product here.

        An operator runs this precisely because the chain does not work,
        so "failed" alone wastes the moment they are looking for a
        reason. The failure is injected rather than provoked with a bad
        port: conftest mocks the serial layer, so a nonexistent port
        opens happily in the suite and this test passed against a 200.
        """
        from sstv_core.audio import ptt_controller as ptt

        async def refuse(self: object) -> None:
            raise ptt.PTTError("Can't open serial port /dev/ttyUSB0")

        monkeypatch.setattr(ptt.PTTController, "key_radio", refuse)

        response = self._client().post(
            "/api/v1/devices/test_ptt",
            json={"method": "serial", "serial_port": "/dev/ttyUSB0"},
        )

        assert response.status_code == 503
        detail = response.json()["detail"]
        assert "error" in detail, "clients need a code, not prose to match on"
        assert "port" in detail["message"].lower()
        assert detail.get("suggested_action"), "an error with no way forward"

    def test_an_unknown_method_is_named(self) -> None:
        response = self._client().post(
            "/api/v1/devices/test_ptt", json={"method": "carrier-pigeon"}
        )

        assert response.status_code == 400
        assert response.json()["detail"]["error"] == "UNKNOWN_PTT_METHOD"

    def test_ptt_with_no_method_configured_is_explained(self) -> None:
        """PTTMethod.NONE is a legitimate setup -- receive-only operators
        have no PTT at all -- so this is an explanation, not a fault."""
        response = self._client().post(
            "/api/v1/devices/test_ptt", json={"method": "none"}
        )

        assert response.status_code in (200, 400)

    @pytest.mark.parametrize("duration", [0.0, 60.0])
    def test_an_out_of_range_tone_duration_is_refused(
        self, duration: float
    ) -> None:
        response = self._client().post(
            "/api/v1/devices/test_tone", json={"duration_sec": duration}
        )

        assert response.status_code == 422
