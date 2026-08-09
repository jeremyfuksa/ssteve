"""Tests against the REAL DSPManager.

The autouse conftest fixture mocks the singleton's start/stop methods for
route tests; these tests construct fresh DSPManager instances so the actual
seam logic -- device-ID resolution, config-driven PTT, failure reporting --
is exercised. This is exactly the layer the 2026-08-07 audit found had zero
real coverage.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from sstv_core.api.dsp_manager import DSPManager
from sstv_core.audio.ptt_controller import PTTMethod


@pytest.fixture
def dsp() -> DSPManager:
    manager = DSPManager()
    # Deterministic device map regardless of the mocked sounddevice module.
    manager._device_manager_instance = SimpleNamespace(
        get_device_index=lambda device_id: {"ca_USB_Audio": 3, "hw:1,0": 2}.get(
            device_id
        ),
    )
    return manager


class TestDeviceResolution:
    def test_public_string_id_resolves_to_index(self, dsp):
        assert dsp._resolve_device_index("ca_USB_Audio") == 3
        assert dsp._resolve_device_index("hw:1,0") == 2

    def test_numeric_string_still_accepted(self, dsp):
        assert dsp._resolve_device_index("7") == 7

    def test_none_means_default_device(self, dsp):
        assert dsp._resolve_device_index(None) is None
        assert dsp._resolve_device_index("") is None

    def test_unknown_id_raises_instead_of_silently_using_default(self, dsp):
        with pytest.raises(ValueError, match="ca_Not_A_Device"):
            dsp._resolve_device_index("ca_Not_A_Device")


class TestPTTFromConfig:
    """start_transmit must honor saved PTT config, not class defaults."""

    CONFIG = {
        "ptt_method": "serial",
        "ptt_serial_port": "/dev/tty.usbserial-1",
        "ptt_serial_signal": "DTR",
        "ptt_pre_delay_ms": 800,
        "ptt_post_delay_ms": 300,
        "vox_preamble_ms": 700,
    }

    def test_config_method_and_signal_used_when_request_is_silent(self, dsp):
        ptt = dsp._build_ptt_controller(self.CONFIG, serial_port=None, vox_enabled=False)
        assert ptt.method == PTTMethod.SERIAL
        assert ptt._serial_port == "/dev/tty.usbserial-1"
        assert ptt._serial_signal == "DTR"
        assert ptt._pre_delay_ms == 800
        assert ptt._post_delay_ms == 300

    def test_request_serial_port_overrides_method_but_keeps_config_signal(self, dsp):
        ptt = dsp._build_ptt_controller(
            self.CONFIG, serial_port="/dev/ttyUSB9", vox_enabled=False
        )
        assert ptt.method == PTTMethod.SERIAL
        assert ptt._serial_port == "/dev/ttyUSB9"
        assert ptt._serial_signal == "DTR"

    def test_vox_request_keeps_config_preamble(self, dsp):
        ptt = dsp._build_ptt_controller(self.CONFIG, serial_port=None, vox_enabled=True)
        assert ptt.method == PTTMethod.VOX
        assert ptt._vox_preamble_ms == 700

    @pytest.mark.asyncio
    async def test_no_database_yields_documented_defaults(self, dsp):
        config = await dsp._read_ptt_config()
        assert config["ptt_method"] == "vox"
        assert config["ptt_serial_signal"] == "RTS"
        assert config["ptt_pre_delay_ms"] == 500
        assert config["ptt_post_delay_ms"] == 200


class TestDecodeFailureReporting:
    """A decode error must surface as FAILED with an error event -- not as a
    clean 'stopped' with error: null (the audit's finding 8)."""

    @pytest.mark.asyncio
    async def test_rx_error_reports_failed_state_and_error_event(self, monkeypatch):
        from sstv_core.api import dsp_manager as dsp_module
        from sstv_core.api.models import DecodeState
        from sstv_core.api.session_manager import session_manager

        class ExplodingRX:
            def __init__(self, *args, **kwargs):
                pass

            def set_progress_callback(self, cb):
                pass

            async def receive(self, **kwargs):
                raise RuntimeError("PortAudio exploded")

            async def cancel(self):
                pass

        monkeypatch.setattr(dsp_module, "RXManager", ExplodingRX)

        broadcasts: list[dict] = []

        async def record_broadcast(session_id, payload):
            broadcasts.append(payload)

        monkeypatch.setattr(
            dsp_module.websocket_manager, "broadcast", record_broadcast
        )

        manager = DSPManager()
        manager._device_manager_instance = SimpleNamespace(get_device_index=lambda _id: None)

        session = await session_manager.create_decode_session(metadata={})
        try:
            await manager.start_decode(
                session_id=session.session_id,
                mode=None,
                auto_detect=True,
                timeout_seconds=5.0,
                save_image=False,
                callsign=None,
                device_id=None,
            )
            # Let the failing task and its done-callback run.
            for _ in range(10):
                await asyncio.sleep(0.05)
                data = await session_manager.get_decode_session(session.session_id)
                if data and data.state == DecodeState.FAILED.value:
                    break

            data = await session_manager.get_decode_session(session.session_id)
            assert data is not None
            assert data.state == DecodeState.FAILED.value
            assert "PortAudio exploded" in (data.metadata.get("error") or "")
            error_events = [b for b in broadcasts if b.get("event_type") == "error"]
            assert error_events, f"no error event broadcast; got {broadcasts}"
        finally:
            session_manager.reset()


class TestUnsupportedDecodeMode:
    def test_route_rejects_mode_without_decoder(self):
        from fastapi.testclient import TestClient

        from sstv_core.api.main import app

        client = TestClient(app)
        response = client.post(
            "/api/v1/decode/start",
            json={"mode": "PD90", "auto_detect": False},
        )
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["error"] == "UNSUPPORTED_MODE"
        assert "ScottieS1" in detail["suggested_action"]


class TestShutdown:
    """Shutdown must stop live operations, not orphan them.

    Found 2026-08-08: the API lifespan stopped the watcher and the cleanup
    task, then disposed the DB engine -- but never touched dsp_manager's
    task dicts. On SIGTERM mid-transmit the task was orphaned with no
    cancel() and, if PTT was keyed, nothing unkeyed the radio.
    """

    @pytest.mark.asyncio
    async def test_shutdown_with_no_active_sessions_is_a_noop(self, dsp):
        await dsp.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_cancels_transmit_and_decode_tasks(self, dsp):
        from uuid import uuid4

        async def forever():
            await asyncio.Event().wait()

        tx_id, rx_id = uuid4(), uuid4()
        tx_task = asyncio.create_task(forever())
        rx_task = asyncio.create_task(forever())
        dsp._transmit_tasks[tx_id] = tx_task
        dsp._decode_tasks[rx_id] = rx_task

        cancelled: list[str] = []
        dsp._tx_managers[tx_id] = SimpleNamespace(
            cancel=_recording_async(cancelled, "tx")
        )
        dsp._rx_managers[rx_id] = SimpleNamespace(
            cancel=_recording_async(cancelled, "rx")
        )

        await dsp.shutdown()

        assert tx_task.cancelled() or tx_task.done()
        assert rx_task.cancelled() or rx_task.done()
        assert cancelled == ["tx", "rx"], (
            f"transmit must be stopped before decode (RF hazard first); got {cancelled}"
        )
        assert not dsp._transmit_tasks and not dsp._decode_tasks

    @pytest.mark.asyncio
    async def test_one_failing_session_does_not_strand_the_others(self, dsp):
        from uuid import uuid4

        async def forever():
            await asyncio.Event().wait()

        bad_id, good_id = uuid4(), uuid4()
        bad_task = asyncio.create_task(forever())
        good_task = asyncio.create_task(forever())
        dsp._transmit_tasks[bad_id] = bad_task
        dsp._transmit_tasks[good_id] = good_task

        async def explode():
            raise RuntimeError("serial port vanished")

        stopped: list[str] = []
        dsp._tx_managers[bad_id] = SimpleNamespace(cancel=explode)
        dsp._tx_managers[good_id] = SimpleNamespace(
            cancel=_recording_async(stopped, "good")
        )

        await dsp.shutdown()

        assert stopped == ["good"], "a failing session stranded the remaining ones"
        good_task.cancel()
        bad_task.cancel()


def _recording_async(sink: list[str], label: str):
    async def _cancel():
        sink.append(label)

    return _cancel


class TestLifespanWiring:
    """The lifespan must actually invoke dsp_manager.shutdown().

    The TestShutdown cases above prove the method behaves; this proves it is
    reached. Without it, deleting the call from main.py would break nothing.
    """

    def test_app_shutdown_stops_dsp_operations(self, monkeypatch):
        from fastapi.testclient import TestClient

        from sstv_core.api import dsp_manager as dsp_module
        from sstv_core.api.main import app

        called: list[str] = []

        async def record_shutdown():
            called.append("shutdown")

        monkeypatch.setattr(
            dsp_module.dsp_manager, "shutdown", record_shutdown, raising=True
        )

        with TestClient(app):
            assert called == [], "shutdown ran during startup"

        assert called == ["shutdown"], "lifespan exit never stopped DSP operations"
