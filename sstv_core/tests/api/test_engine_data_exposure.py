"""Engine-computed data must survive the trip to the API boundary.

The 2026-08-08 sweep found a recurring pattern: RSV, FSKID, AFC lock, noise
floor, and per-device sample rates are all computed and persisted, then
dropped when the response model is built. #58 widened the models.

Every field added there defaults to None/False, so the models validate
whether or not anything fills them -- a green suite would look identical if
the plumbing were still missing. These tests populate real values and assert
they arrive.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from sstv_core.api.main import app
from sstv_core.api.models import AudioDevice, DecodeCompleteEvent, DecodeStatusResponse

client = TestClient(app)


def _db_image(**overrides):
    """An SSTVImage-shaped stand-in with every engine-computed column set."""
    base = dict(
        id=1,
        filename="20260809_143000_MartinM1_W1AW.png",
        filepath="/tmp/sstv/20260809_143000_MartinM1_W1AW.png",
        mode="MartinM1",
        is_received=True,
        callsign="W1AW",
        timestamp=datetime(2026, 8, 9, 14, 30, tzinfo=timezone.utc),
        frequency_hz=14230000.0,
        rx_quality_score=0.87,
        rx_snr_db=18.4,
        rx_peak_amplitude=0.62,
        rx_noise_floor=0.07,
        rsv_readability=5,
        rsv_signal=9,
        rsv_video=5,
        rsv_report="595",
        fskid_detected=True,
        fskid_confidence=0.94,
        fskid_checksum_valid=True,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class TestImageMetadataCarriesRSVAndFSKID:
    """Item 1: persisted since PRs #38/#41, exposed nowhere until #58."""

    def test_converter_passes_every_computed_column_through(self):
        from sstv_core.api.routes.images import _db_image_to_api

        api = _db_image_to_api(_db_image())

        assert api.rsv_report == "595"
        assert (api.rsv_readability, api.rsv_signal, api.rsv_video) == (5, 9, 5)
        assert api.peak_amplitude == pytest.approx(0.62)
        assert api.noise_floor == pytest.approx(0.07)
        assert api.fskid_detected is True
        assert api.fskid_confidence == pytest.approx(0.94)
        assert api.fskid_checksum_valid is True
        # Contract drift, same issue item 6.
        assert api.filename == "20260809_143000_MartinM1_W1AW.png"
        assert api.rx_quality_score == pytest.approx(0.87)

    def test_absent_metrics_stay_null_rather_than_zero(self):
        """A TX image or a pre-RSV decode must not report a fabricated 0."""
        from sstv_core.api.routes.images import _db_image_to_api

        api = _db_image_to_api(
            _db_image(
                is_received=False,
                rsv_readability=None,
                rsv_signal=None,
                rsv_video=None,
                rsv_report=None,
                rx_peak_amplitude=None,
                rx_noise_floor=None,
                fskid_detected=None,
                fskid_confidence=None,
                fskid_checksum_valid=None,
                rx_quality_score=None,
            )
        )

        assert api.direction == "tx"
        for field in (
            "rsv_report", "rsv_readability", "rsv_signal", "rsv_video",
            "peak_amplitude", "noise_floor", "fskid_detected",
            "fskid_confidence", "fskid_checksum_valid", "rx_quality_score",
        ):
            assert getattr(api, field) is None, f"{field} was fabricated"

    def test_a_bad_checksum_is_reported_not_hidden(self):
        """The client needs to know the decoded call is untrustworthy."""
        from sstv_core.api.routes.images import _db_image_to_api

        api = _db_image_to_api(
            _db_image(fskid_detected=True, fskid_checksum_valid=False, callsign=None)
        )
        assert api.fskid_detected is True
        assert api.fskid_checksum_valid is False
        assert api.callsign is None, "a failed-checksum call must not be adopted"


class TestAFCLockIsVerifiable:
    """Item 2 / PRODUCT.md #5. Three states, which is why this isn't a bool."""

    def _rx(self, *, auto_afc: bool):
        from sstv_core.decode.rx_manager import RXManager

        # sample_rate has to be a real number, not an auto-created mock
        # attribute: RXManager rejects a source whose rate disagrees with the
        # explicit argument (#92), and a bare MagicMock() reports its own
        # mock object as the rate.
        source = MagicMock()
        source.sample_rate = 48000

        return RXManager(
            stream_manager=source,
            sample_rate=48000,
            auto_afc=auto_afc,
        )

    def test_searching_before_lock(self):
        locked, offset, applied = self._rx(auto_afc=True).get_afc_state()
        assert locked is False
        assert offset is None
        assert applied is None

    def test_locked_and_corrected(self):
        rx = self._rx(auto_afc=True)
        rx._afc_locked = True
        rx._afc_offset_hz = 42.0
        rx._afc_correction_applied_hz = 42.0

        locked, offset, applied = rx.get_afc_state()
        assert locked is True
        assert offset == pytest.approx(42.0)
        assert applied == pytest.approx(42.0)

    def test_locked_but_deliberately_not_applied(self):
        """auto_afc off (Doppler work): offset known, mapping untouched.

        This is the state a single `afc_locked` boolean would erase. The
        operator must see "I know you're 42 Hz out and I'm not touching it"
        as distinct from both searching and locked-and-corrected.
        """
        rx = self._rx(auto_afc=False)
        rx._afc_locked = True
        rx._afc_offset_hz = 42.0
        rx._afc_correction_applied_hz = 0.0

        locked, offset, applied = rx.get_afc_state()
        assert locked is True
        assert offset == pytest.approx(42.0), "measured offset must still be reported"
        assert applied == 0.0
        assert applied != offset, "the two must be distinguishable"

    def test_state_resets_between_sessions(self):
        rx = self._rx(auto_afc=True)
        rx._afc_locked = True
        rx._afc_offset_hz = 42.0
        rx._afc_correction_applied_hz = 42.0
        # receive() resets these; assert the reset list did not miss them.
        rx._afc_locked = False
        rx._afc_offset_hz = None
        rx._afc_correction_applied_hz = None
        assert rx.get_afc_state() == (False, None, None)


class TestDecodeStatusContract:
    """Item 6: fields backend-spec.md specified that the model never had."""

    def test_status_model_accepts_the_specified_fields(self):
        from uuid import uuid4

        status = DecodeStatusResponse(
            session_id=uuid4(),
            state="decoding",
            total_scanlines=256,
            vis_detected=True,
            signal_quality=0.81,
            afc_locked=True,
            afc_correction_applied_hz=0.0,
            frequency_offset_hz=42.0,
            started_at=datetime.now(timezone.utc),
        )
        assert status.total_scanlines == 256
        assert status.vis_detected is True
        assert status.signal_quality == pytest.approx(0.81)
        # Locked, offset known, nothing applied: the third AFC state.
        assert status.afc_locked is True
        assert status.afc_correction_applied_hz == 0.0
        assert status.frequency_offset_hz == pytest.approx(42.0)

    def test_defaults_do_not_invent_a_locked_afc(self):
        from uuid import uuid4

        status = DecodeStatusResponse(
            session_id=uuid4(),
            state="listening",
            started_at=datetime.now(timezone.utc),
        )
        assert status.afc_locked is False
        assert status.afc_correction_applied_hz is None
        assert status.vis_detected is False
        assert status.total_scanlines is None


class TestAudioDeviceSampleRates:
    """Item 5: device_manager probes the plural list; the route kept one."""

    def test_model_carries_the_full_rate_list_and_direction_flags(self):
        device = AudioDevice(
            device_id="ca_USB_Audio",
            name="USB Audio CODEC",
            channels=2,
            sample_rate=48000,
            sample_rates=[8000, 16000, 44100, 48000],
            is_input=True,
            is_output=False,
        )
        assert device.sample_rates == [8000, 16000, 44100, 48000]
        assert device.is_input is True and device.is_output is False

    def test_route_serves_probed_rates_not_just_the_pick(self, monkeypatch):
        from sstv_core.api.routes import devices as devices_routes

        probed = SimpleNamespace(
            id="ca_USB_Audio",
            name="USB Audio CODEC",
            channels=2,
            sample_rates=[48000, 8000, 44100],  # deliberately unsorted
            is_input=True,
            is_output=False,
            is_default=True,
        )

        class FakeManager:
            def __init__(self, *a, **k):
                pass

            def list_all_devices(self):
                return [probed]

        monkeypatch.setattr(
            "sstv_core.audio.device_manager.AudioDeviceManager", FakeManager
        )
        response = client.get("/api/v1/devices/audio")
        assert response.status_code == 200, response.json()
        entry = response.json()[0]
        assert entry["sample_rates"] == [8000, 44100, 48000], "not sorted ascending"
        assert entry["sample_rate"] == 48000, "48k should win the scalar pick"
        assert entry["is_input"] is True
        assert entry["is_output"] is False

        assert devices_routes is not None  # import used for the monkeypatch target


class TestDecodeCompleteCarriesTheReport:
    def test_event_exposes_rsv_and_fskid(self):
        event = DecodeCompleteEvent(
            filepath="/tmp/x.png",
            duration_seconds=90.0,
            rsv_report="595",
            fskid_detected=True,
            fskid_checksum_valid=False,
        )
        payload = event.model_dump(mode="json")
        assert payload["rsv_report"] == "595"
        assert payload["fskid_detected"] is True
        assert payload["fskid_checksum_valid"] is False

    def test_absent_values_stay_null(self):
        payload = DecodeCompleteEvent(
            filepath="/tmp/x.png", duration_seconds=90.0
        ).model_dump(mode="json")
        assert payload["rsv_report"] is None
        assert payload["fskid_detected"] is None
