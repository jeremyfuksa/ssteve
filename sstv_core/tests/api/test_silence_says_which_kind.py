"""A listen that hears nothing must say which kind of nothing.

The band is silent 97.4% of the time, so "no picture" is this product's most
common outcome and its least informative one. Two situations produce it:

- the band was quiet, and the receiver was fine;
- the receiver was deaf, and the band was never heard at all.

They call for opposite responses, and only the measured level separates
them. The CLI has said which since #90. Over the API the session simply
stopped with no message, so the desktop shell had nothing to show -- the
same lesson unlearned one layer up.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from sstv_core.api import dsp_manager as dsp_module
from sstv_core.api.dsp_manager import DSPManager
from sstv_core.api.models import DecodeState
from sstv_core.api.session_manager import session_manager
from sstv_core.audio.levels import DEAF_RMS, describe_level, nothing_heard


class TestTheWords:
    def test_a_deaf_reading_blames_the_receiver(self):
        message, detail, action = nothing_heard(0.000231)

        assert "barely heard anything" in message
        assert "0.000231" in detail, "the measurement is the evidence; quote it"
        assert "gain" in action

    def test_a_healthy_reading_blames_neither(self):
        message, detail, action = nothing_heard(0.02)

        assert "level was fine" in detail
        assert "gain" not in action, "raising the gain is bad advice at this level"
        assert "frequency" in action or "band" in action

    def test_the_boundary_is_where_it_was_measured(self):
        assert describe_level(DEAF_RMS - 0.0001) == "silent"
        assert describe_level(DEAF_RMS + 0.0001) == "faint"

    def test_the_cli_uses_the_same_thresholds(self):
        """One copy of a measured threshold. Two would drift."""
        from sstv_core.cli.main import DEAF_RMS as cli_threshold

        assert cli_threshold is DEAF_RMS


class TestOverTheAPI:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("loudest", "expected"),
        [(0.000231, "barely heard anything"), (0.02, "level was fine")],
        ids=["deaf-receiver", "quiet-band"],
    )
    async def test_a_fruitless_listen_is_explained(self, monkeypatch, loudest, expected):
        broadcasts: list[dict] = []

        class QuietRX:
            def __init__(self, *args, **kwargs):
                pass

            def set_progress_callback(self, cb):
                pass

            async def receive(self, **kwargs):
                return None  # timed out with no picture

            async def cancel(self):
                pass

            def get_unsupported_mode(self):
                return None

            def get_loudest_listening_rms(self):
                return loudest

        async def record(session_id, payload):
            broadcasts.append(payload)

        monkeypatch.setattr(dsp_module, "RXManager", QuietRX)
        monkeypatch.setattr(dsp_module.websocket_manager, "broadcast", record)

        manager = DSPManager()
        manager._device_manager_instance = SimpleNamespace(get_device_index=lambda _id: None)
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
            for _ in range(40):
                await asyncio.sleep(0.05)
                data = await session_manager.get_decode_session(session.session_id)
                if data and data.state == DecodeState.STOPPED.value:
                    break

            data = await session_manager.get_decode_session(session.session_id)
            assert data is not None
            # Stopped, not failed: hearing nothing is the normal state of a
            # quiet band, and calling it a failure would cry wolf all day.
            assert data.state == DecodeState.STOPPED.value
            assert data.metadata.get("loudest_rms") == loudest

            told = [b for b in broadcasts if b.get("error_code") == "NOTHING_HEARD"]
            assert told, f"the operator was told nothing; got {broadcasts}"
            assert expected in told[0]["message"]
            assert told[0]["recoverable"] is True
            assert told[0]["suggested_action"]
        finally:
            session_manager.reset()
