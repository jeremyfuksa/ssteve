"""Receiving from SpyServer over the API (#134).

Until this, SpyServer receive existed only in the CLI: POST /decode/start
could open a sound card and nothing else, while the config API stored a
SpyServer host that no API path read.

Most of these run against a fresh DSPManager rather than the route, because
the autouse conftest fixture replaces the singleton's start_decode with a
mock. The one that matters most -- a stream that dies mid-listen -- runs the
real RXManager against a real SpyServerSource, with only the network client
faked, so the wiring under test is the wiring that ships.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from sstv_core.api import dsp_manager as dsp_module
from sstv_core.api.dsp_manager import DecodeSourceError, DSPManager
from sstv_core.api.models import DecodeState
from sstv_core.api.session_manager import session_manager
from sstv_core.sdr.bands import BAND_PRESETS
from sstv_core.sdr.spyserver.client import SpyServerError, StreamStalledError

STORED = {
    "host": "airspy.local",
    "port": 5555,
    "frequency_hz": 7_171_000,
    "gain": 6,
    "stall_timeout_sec": 5.0,
}


@pytest.fixture
def dsp(monkeypatch) -> DSPManager:
    manager = DSPManager()
    manager._device_manager_instance = SimpleNamespace(get_device_index=lambda _id: None)

    async def stored():
        return dict(STORED)

    monkeypatch.setattr(manager, "_read_spyserver_config", stored)
    return manager


@pytest.fixture
def broadcasts(monkeypatch) -> list[dict]:
    sent: list[dict] = []

    async def record(session_id, payload):
        sent.append(payload)

    monkeypatch.setattr(dsp_module.websocket_manager, "broadcast", record)
    return sent


async def _wait_for_state(session_id, state: DecodeState, seconds: float = 5.0):
    deadline = asyncio.get_running_loop().time() + seconds
    while asyncio.get_running_loop().time() < deadline:
        data = await session_manager.get_decode_session(session_id)
        if data and data.state == state.value:
            return data
        await asyncio.sleep(0.05)
    return await session_manager.get_decode_session(session_id)


class TestBandTable:
    def test_cli_and_api_share_one_table(self):
        from sstv_core.cli.main import BAND_PRESETS as CLI_BAND_PRESETS

        assert CLI_BAND_PRESETS is BAND_PRESETS


class TestTargetResolution:
    """Band, frequency, or stored default -- and a refusal in our voice."""

    @pytest.mark.asyncio
    async def test_band_tunes_its_calling_frequency(self, dsp):
        target = await dsp._resolve_spyserver_target(band="20m", frequency_hz=None)
        assert target["frequency_hz"] == 14_230_000
        assert target["host"] == "airspy.local"
        assert target["gain"] == 6

    @pytest.mark.asyncio
    async def test_band_is_case_insensitive(self, dsp):
        target = await dsp._resolve_spyserver_target(band="40M", frequency_hz=None)
        assert target["frequency_hz"] == 7_171_000

    @pytest.mark.asyncio
    async def test_exact_frequency_wins(self, dsp):
        target = await dsp._resolve_spyserver_target(band=None, frequency_hz=14_233_000)
        assert target["frequency_hz"] == 14_233_000

    @pytest.mark.asyncio
    async def test_neither_uses_the_stored_frequency(self, dsp):
        target = await dsp._resolve_spyserver_target(band=None, frequency_hz=None)
        assert target["frequency_hz"] == STORED["frequency_hz"]

    @pytest.mark.asyncio
    async def test_band_and_frequency_together_is_ambiguous(self, dsp):
        with pytest.raises(DecodeSourceError) as exc:
            await dsp._resolve_spyserver_target(band="20m", frequency_hz=14_233_000)
        assert exc.value.suggested_action

    @pytest.mark.asyncio
    async def test_fm_band_explains_itself(self, dsp):
        with pytest.raises(DecodeSourceError, match="FM") as exc:
            await dsp._resolve_spyserver_target(band="2m", frequency_hz=None)
        assert "20m" in exc.value.suggested_action

    @pytest.mark.asyncio
    async def test_unknown_band_lists_the_real_ones(self, dsp):
        with pytest.raises(DecodeSourceError, match="6m") as exc:
            await dsp._resolve_spyserver_target(band="6m", frequency_hz=None)
        assert "40m" in exc.value.suggested_action

    @pytest.mark.asyncio
    async def test_no_saved_host_says_where_to_put_one(self, dsp, monkeypatch):
        async def no_host():
            return {**STORED, "host": ""}

        monkeypatch.setattr(dsp, "_read_spyserver_config", no_host)
        with pytest.raises(DecodeSourceError) as exc:
            await dsp._resolve_spyserver_target(band="20m", frequency_hz=None)
        assert "spyserver_host" in exc.value.suggested_action

    @pytest.mark.asyncio
    async def test_no_database_falls_back_to_documented_defaults(self):
        # Defaults have no host, so the refusal is the documented outcome.
        manager = DSPManager()
        with pytest.raises(DecodeSourceError):
            await manager._resolve_spyserver_target(band="20m", frequency_hz=None)


class TestSourceSelection:
    @pytest.mark.asyncio
    async def test_spyserver_source_is_built_from_config_and_handed_to_rx(
        self, dsp, monkeypatch, broadcasts
    ):
        built: dict[str, Any] = {}

        class FakeSource:
            sample_rate = 48_000
            stream_failure = None

            def __init__(self, **kwargs):
                built.update(kwargs)

        captured: dict[str, Any] = {}

        class CapturingRX:
            def __init__(self, *args, **kwargs):
                captured.update(kwargs)

            def set_progress_callback(self, cb):
                pass

            async def receive(self, **kwargs):
                return None

            async def cancel(self):
                pass

            def get_unsupported_mode(self):
                return None

        monkeypatch.setattr(dsp_module, "SpyServerSource", FakeSource)
        monkeypatch.setattr(dsp_module, "RXManager", CapturingRX)

        session = await session_manager.create_decode_session(metadata={})
        try:
            await dsp.start_decode(
                session_id=session.session_id,
                mode=None,
                auto_detect=True,
                timeout_seconds=5.0,
                save_image=False,
                callsign=None,
                device_id=None,
                source="spyserver",
                band="20m",
            )
            assert built["host"] == "airspy.local"
            assert built["port"] == 5555
            assert built["frequency_hz"] == 14_230_000
            assert built["gain"] == 6
            assert isinstance(captured["stream_manager"], FakeSource)
            # The -40 dB default squelch cost real captures most of their
            # VIS detections; SpyServer starts open, like the CLI.
            assert captured["auto_squelch"] is False
            await _wait_for_state(session.session_id, DecodeState.STOPPED)
        finally:
            session_manager.reset()

    @pytest.mark.asyncio
    async def test_bad_target_fails_before_any_session_state(self, dsp):
        with pytest.raises(DecodeSourceError):
            await dsp.start_decode(
                session_id=__import__("uuid").uuid4(),
                mode=None,
                auto_detect=True,
                timeout_seconds=5.0,
                save_image=False,
                callsign=None,
                device_id=None,
                source="spyserver",
                band="2m",
            )
        assert not dsp._rx_managers

    @pytest.mark.asyncio
    async def test_audio_source_rejects_spyserver_tuning(self, dsp):
        with pytest.raises(DecodeSourceError, match="SpyServer"):
            await dsp.start_decode(
                session_id=__import__("uuid").uuid4(),
                mode=None,
                auto_detect=True,
                timeout_seconds=5.0,
                save_image=False,
                callsign=None,
                device_id=None,
                source="audio",
                band="20m",
            )


class TestConnectFailure:
    @pytest.mark.asyncio
    async def test_source_error_reaches_operator_with_its_own_advice(
        self, dsp, monkeypatch, broadcasts
    ):
        """A down server must not get the sound-card advice."""

        class Source:
            sample_rate = 48_000
            stream_failure = None

            def __init__(self, **kwargs):
                pass

        class UnreachableRX:
            def __init__(self, *args, **kwargs):
                pass

            def set_progress_callback(self, cb):
                pass

            async def receive(self, **kwargs):
                raise SpyServerError(
                    "I couldn't reach the SpyServer at airspy.local:5555.",
                    suggested_action="Check the host and port, and that the server is running.",
                )

            async def cancel(self):
                pass

        monkeypatch.setattr(dsp_module, "SpyServerSource", Source)
        monkeypatch.setattr(dsp_module, "RXManager", UnreachableRX)

        session = await session_manager.create_decode_session(metadata={})
        try:
            await dsp.start_decode(
                session_id=session.session_id,
                mode=None,
                auto_detect=True,
                timeout_seconds=5.0,
                save_image=False,
                callsign=None,
                device_id=None,
                source="spyserver",
            )
            data = await _wait_for_state(session.session_id, DecodeState.FAILED)
            assert data is not None and data.state == DecodeState.FAILED.value
            events = [b for b in broadcasts if b.get("event_type") == "error"]
            assert events, f"no error event; got {broadcasts}"
            assert events[0]["error_code"] == "SPYSERVER_UNAVAILABLE"
            assert "airspy.local" in events[0]["message"]
            assert "server is running" in events[0]["suggested_action"]
            assert events[0]["recoverable"] is True
        finally:
            session_manager.reset()


class StallingClient:
    """A server that accepts, streams briefly, then goes silent.

    Stands in for SpyServerClient only. Everything above it -- the
    source, the demodulator, the ring buffer, RXManager's listen loop --
    is real, which is the point: the frozen-session bug lived in the
    wiring between them, not in any one piece.
    """

    def __init__(self) -> None:
        self._error: SpyServerError | None = None
        self.closed = False

    @property
    def sample_rate(self) -> int:
        return 48_000

    @property
    def dropped_frames(self) -> int:
        return 0

    @property
    def stream_error(self) -> SpyServerError | None:
        return self._error

    @property
    def device_info(self) -> object | None:
        return None

    def connect(self) -> None:
        pass

    def tune(self, frequency_hz: int) -> None:
        pass

    def start_streaming(self, on_iq, gain: int = 0) -> None:
        # A little band noise, then the stall the client would latch.
        on_iq((np.random.default_rng(0).standard_normal(4800) * 1e-3).astype(np.complex64))
        self._error = StreamStalledError()

    def stop_streaming(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class TestStreamDiesMidListen:
    """The API version of #124: a dead stream ends the session, and says so.

    The CLI once listened to a frozen buffer for 3.5 hours because it read
    the failure only after the decode returned -- at the timeout. Over the
    API the same gap would show a quiet band on the canvas until then.
    """

    @pytest.mark.asyncio
    async def test_stall_ends_the_session_long_before_the_timeout(
        self, dsp, monkeypatch, broadcasts
    ):
        from sstv_core.decode.rx_manager import RXManager
        from sstv_core.sdr.source import SpyServerSource

        client = StallingClient()
        monkeypatch.setattr(
            dsp_module,
            "SpyServerSource",
            lambda **kwargs: SpyServerSource(**kwargs, client=client),
        )
        monkeypatch.setattr(RXManager, "LISTENING_HEARTBEAT_SEC", 0.2)

        session = await session_manager.create_decode_session(metadata={})
        try:
            started = asyncio.get_running_loop().time()
            await dsp.start_decode(
                session_id=session.session_id,
                mode=None,
                auto_detect=True,
                timeout_seconds=300.0,
                save_image=False,
                callsign=None,
                device_id=None,
                source="spyserver",
                band="20m",
            )
            data = await _wait_for_state(
                session.session_id, DecodeState.FAILED, seconds=10.0
            )
            elapsed = asyncio.get_running_loop().time() - started

            assert data is not None and data.state == DecodeState.FAILED.value, (
                "a stalled stream must fail the session, not leave it listening"
            )
            assert elapsed < 10.0, f"took {elapsed:.1f}s against a 300s timeout"
            events = [b for b in broadcasts if b.get("event_type") == "error"]
            assert [e["error_code"] for e in events] == ["STREAM_STALLED"], (
                f"expected one stall report; got {events}"
            )
            assert "not a weak signal" in events[0]["message"]
            assert events[0]["suggested_action"]
            assert client.closed, "the connection was left open"
        finally:
            session_manager.reset()

    @pytest.mark.asyncio
    async def test_dropped_link_is_not_reported_as_a_stall(
        self, dsp, monkeypatch, broadcasts
    ):
        from sstv_core.decode.rx_manager import RXManager
        from sstv_core.sdr.source import SpyServerSource

        class DroppingClient(StallingClient):
            def start_streaming(self, on_iq, gain: int = 0) -> None:
                self._error = SpyServerError(
                    "The SpyServer closed the connection.",
                    suggested_action="Reconnect; if it keeps happening, try another server.",
                )

        client = DroppingClient()
        monkeypatch.setattr(
            dsp_module,
            "SpyServerSource",
            lambda **kwargs: SpyServerSource(**kwargs, client=client),
        )
        monkeypatch.setattr(RXManager, "LISTENING_HEARTBEAT_SEC", 0.2)

        session = await session_manager.create_decode_session(metadata={})
        try:
            await dsp.start_decode(
                session_id=session.session_id,
                mode=None,
                auto_detect=True,
                timeout_seconds=300.0,
                save_image=False,
                callsign=None,
                device_id=None,
                source="spyserver",
            )
            await _wait_for_state(session.session_id, DecodeState.FAILED, seconds=10.0)
            codes = [b["error_code"] for b in broadcasts if b.get("event_type") == "error"]
            assert codes == ["STREAM_LOST"]
        finally:
            session_manager.reset()


class TestRoute:
    def test_route_forwards_source_and_tuning(self, mock_dsp_manager):
        from fastapi.testclient import TestClient

        from sstv_core.api.main import app

        response = TestClient(app).post(
            "/api/v1/decode/start",
            json={"source": "spyserver", "band": "20m"},
        )
        assert response.status_code == 201, response.text
        kwargs = mock_dsp_manager.start_decode.await_args.kwargs
        assert kwargs["source"] == "spyserver"
        assert kwargs["band"] == "20m"
        assert kwargs["frequency_hz"] is None
        session_manager.reset()

    def test_route_carries_the_source_advice_not_the_device_advice(
        self, mock_dsp_manager
    ):
        from fastapi.testclient import TestClient

        from sstv_core.api.main import app

        mock_dsp_manager.start_decode.side_effect = DecodeSourceError(
            "I can't listen on 2m yet -- it's FM, and I only demodulate SSB.",
            suggested_action="Use an HF band for now: 10m, 15m, 20m, 40m, 80m.",
        )
        response = TestClient(app).post(
            "/api/v1/decode/start",
            json={"source": "spyserver", "band": "2m"},
        )
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "FM" in detail["message"]
        assert "HF band" in detail["suggested_action"]
        assert "devices/audio" not in detail["suggested_action"]
        session_manager.reset()

    def test_existing_callers_default_to_the_sound_card(self, mock_dsp_manager):
        from fastapi.testclient import TestClient

        from sstv_core.api.main import app

        response = TestClient(app).post("/api/v1/decode/start", json={})
        assert response.status_code == 201, response.text
        assert mock_dsp_manager.start_decode.await_args.kwargs["source"] == "audio"
        session_manager.reset()
