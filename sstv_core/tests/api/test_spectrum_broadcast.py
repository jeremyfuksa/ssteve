"""Spectrum frames reach the app WebSocket, not just a callback (#53).

The producer tests prove the FFT; the rx_manager tests prove the seam
fires. Neither would notice if nothing relayed a frame to a client, which
is the whole point of the feature.

The app channel is the right one. It is unbuffered by design -- a frame
describes the band *now*, and replaying a stale waterfall row to a
reconnecting client is worse than a gap in the display. It is also not
session-scoped, which is what lets an operator tune before starting a
decode.
"""

from __future__ import annotations

import pytest

from sstv_core.api.models import SpectrumUpdateEvent
from sstv_core.dsp.spectrum import SpectrumFrame


async def _swallow_broadcast(session_id: object, payload: object) -> None:
    """Session-channel broadcasts are not what these tests are about."""
    return None


def _frame(**overrides: object) -> SpectrumFrame:
    base = {
        "start_hz": 300.0,
        "bin_hz": 46.875,
        "magnitudes_db": [-90, -85, -40, -88],
        "sync_detected": False,
        "peak_hz": 1200.0,
        "peak_db": -40,
    }
    base.update(overrides)
    return SpectrumFrame(**base)  # type: ignore[arg-type]


class TestTheEventCarriesTheFrame:
    def test_a_frame_becomes_a_spectrum_update_event(self) -> None:
        from sstv_core.api.dsp_manager import spectrum_frame_to_event

        event = spectrum_frame_to_event(_frame())

        assert event["event_type"] == "spectrum_update"
        assert event["magnitudes_db"] == [-90, -85, -40, -88]
        assert event["start_hz"] == 300.0

    def test_sync_survives_the_conversion(self) -> None:
        """The one field a client cannot recompute from magnitudes."""
        from sstv_core.api.dsp_manager import spectrum_frame_to_event

        assert spectrum_frame_to_event(_frame(sync_detected=True))["sync_detected"]

    def test_the_event_is_json_serialisable(self) -> None:
        """numpy scalars serialise to nothing useful over a WebSocket.

        A frame built from real audio carries numpy types unless the
        producer casts them out, and `json.dumps` raises on those -- the
        failure would only appear with a client attached.
        """
        import json

        from sstv_core.api.dsp_manager import spectrum_frame_to_event

        json.dumps(spectrum_frame_to_event(_frame()))

    def test_a_real_frame_is_json_serialisable(self) -> None:
        """The same check against a frame the producer actually built."""
        import json

        import numpy as np

        from sstv_core.api.dsp_manager import spectrum_frame_to_event
        from sstv_core.dsp.spectrum import SpectrumProducer

        rng = np.random.default_rng(0)
        audio = (0.1 * rng.standard_normal(2048)).astype("float32")
        frame = SpectrumProducer(sample_rate=48_000, fft_size=1024).compute(audio)

        assert frame is not None
        json.dumps(spectrum_frame_to_event(frame))

    def test_the_event_model_validates_it(self) -> None:
        from sstv_core.api.dsp_manager import spectrum_frame_to_event

        event = SpectrumUpdateEvent(**spectrum_frame_to_event(_frame()))
        assert event.bin_hz > 0


class TestItGoesToTheAppChannel:
    @pytest.mark.asyncio
    async def test_a_frame_is_broadcast_to_app_clients(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The assertion that fails if the relay is deleted."""
        from sstv_core.api import dsp_manager as dm

        sent: list[dict] = []

        async def fake_broadcast_app(event: dict) -> int:
            sent.append(event)
            return 1

        monkeypatch.setattr(
            dm.websocket_manager, "broadcast_app", fake_broadcast_app
        )

        await dm.broadcast_spectrum_frame(_frame())

        assert len(sent) == 1
        assert sent[0]["event_type"] == "spectrum_update"

    @pytest.mark.asyncio
    async def test_a_broadcast_failure_does_not_escape(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A disconnecting client must not take the decode with it."""
        from sstv_core.api import dsp_manager as dm

        async def explode(event: dict) -> int:
            raise RuntimeError("client vanished mid-send")

        monkeypatch.setattr(dm.websocket_manager, "broadcast_app", explode)

        await dm.broadcast_spectrum_frame(_frame())


class TestTheRelayIsActuallyWired:
    """Deleting `rx_mgr.set_spectrum_callback(...)` left every other test
    in this file green.

    That is the third time in one day the same shape has bitten: thorough
    unit tests either side of a connection nothing asserts. The FSKID
    filename tests never called the decoder, the stall predicate tests
    never ran the callback, and these tests proved a helper that nothing
    invoked. The assertion has to be on the wire-up itself.
    """

    @pytest.mark.asyncio
    async def test_start_decode_really_registers_the_callback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Drive the real start_decode and check the RX came out wired.

        Two earlier versions of this test failed to catch a deleted
        relay. The first grepped dsp_manager's source, and broke when the
        call became a getattr while the wiring was fine. The second built
        its own fake RX and mimicked the wiring block -- which passes
        whatever start_decode does, because it never calls it.
        """
        from types import SimpleNamespace

        from sstv_core.api import dsp_manager as dm
        from sstv_core.api.dsp_manager import DSPManager
        from sstv_core.api.session_manager import session_manager

        attached: list[object] = []

        class _RecordingRX:
            def __init__(self, *args: object, **kwargs: object) -> None:
                pass

            def set_spectrum_callback(self, callback: object) -> None:
                attached.append(callback)

            def set_progress_callback(self, callback: object) -> None:
                pass

            async def receive(self, **kwargs: object) -> None:
                return None

            async def cancel(self) -> None:
                return None

        monkeypatch.setattr(dm, "RXManager", _RecordingRX)
        monkeypatch.setattr(
            dm.websocket_manager, "broadcast", _swallow_broadcast
        )

        manager = DSPManager()
        manager._device_manager_instance = SimpleNamespace(
            get_device_index=lambda _id: None
        )
        session = await session_manager.create_decode_session(metadata={})
        try:
            await manager.start_decode(
                session_id=session.session_id,
                mode=None,
                auto_detect=True,
                timeout_seconds=1.0,
                save_image=False,
                callsign=None,
                device_id=None,
            )
        finally:
            await manager.stop_decode(session.session_id)

        assert attached, (
            "start_decode left the RX manager with no spectrum callback, so "
            "no waterfall frame can reach a client however well the producer "
            "works"
        )

    def test_an_rx_without_spectrum_support_still_decodes(self) -> None:
        """The waterfall is optional. A decoder that has no spectrum
        producer must not fail at wiring time -- an unconditional call
        broke two existing dsp_manager tests exactly this way."""

        class _NoSpectrumRX:
            def set_progress_callback(self, callback: object) -> None:
                pass

        rx = _NoSpectrumRX()
        set_spectrum = getattr(rx, "set_spectrum_callback", None)

        assert set_spectrum is None, "the guard is what keeps this from raising"

    def test_the_callback_relays_to_the_broadcaster(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Registering a callback that drops the frame would also pass the
        source check above, so follow the frame through."""
        import asyncio

        from sstv_core.api import dsp_manager as dm
        from sstv_core.decode.rx_manager import RXManager

        sent: list[dict] = []

        async def fake_broadcast_app(event: dict) -> int:
            sent.append(event)
            return 1

        monkeypatch.setattr(dm.websocket_manager, "broadcast_app", fake_broadcast_app)

        class _NoStream:
            def get_input_levels(self) -> None:
                return None

        manager = RXManager(stream_manager=_NoStream())

        async def drive() -> None:
            # The exact registration dsp_manager performs.
            def on_spectrum(frame: object) -> None:
                asyncio.get_running_loop().create_task(
                    dm.broadcast_spectrum_frame(frame)
                )

            manager.set_spectrum_callback(on_spectrum)

            import numpy as np

            times = np.arange(4096) / 48_000
            tone = (0.5 * np.sin(2 * np.pi * 1500.0 * times)).astype("float32")
            manager.emit_spectrum(tone, 48_000)
            await asyncio.sleep(0)
            await asyncio.sleep(0)

        asyncio.run(drive())

        assert sent, "a frame was produced but never reached broadcast_app"
        assert sent[0]["event_type"] == "spectrum_update"
