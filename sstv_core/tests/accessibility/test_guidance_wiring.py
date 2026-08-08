"""Guidance wiring: enabled config plays cues on decode events; disabled
config never does. The generator was orphaned until 2026-08-08."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from sstv_core.accessibility.audio_guidance import GuidanceConfig
from sstv_core.accessibility.guidance_player import GuidancePlayer
from sstv_core.api.dsp_manager import DSPManager
from sstv_core.decode.rx_manager import RXProgress, RXState


def _progress(state: RXState) -> RXProgress:
    return RXProgress(
        state=state, mode="ScottieS1", mode_confidence=0.9,
        percent_complete=10.0, current_line=5, total_lines=256,
        elapsed_sec=1.0, signal_quality=0.8, message="t", audio_levels=None,
    )


class RecordingPlayer:
    def __init__(self):
        self.calls: list[str] = []

    def play_lock_chime(self):
        self.calls.append("lock")

    def play_complete_chime(self):
        self.calls.append("complete")


@pytest.mark.asyncio
async def test_vis_detected_plays_lock_chime(monkeypatch):
    from sstv_core.api import dsp_manager as dsp_module

    async def no_broadcast(*a, **k):
        return 0

    monkeypatch.setattr(dsp_module.websocket_manager, "broadcast", no_broadcast)

    manager = DSPManager()
    session_id = uuid4()
    player = RecordingPlayer()
    manager._guidance_players[session_id] = player

    await manager._handle_rx_progress(session_id, _progress(RXState.VIS_DETECTED))
    assert player.calls == ["lock"]

    await manager._handle_rx_progress(session_id, _progress(RXState.DECODING))
    assert player.calls == ["lock"], "decoding progress must not chime"


@pytest.mark.asyncio
async def test_no_player_means_no_cues(monkeypatch):
    """Disabled guidance = no player registered = silent path, no errors."""
    from sstv_core.api import dsp_manager as dsp_module

    async def no_broadcast(*a, **k):
        return 0

    monkeypatch.setattr(dsp_module.websocket_manager, "broadcast", no_broadcast)

    manager = DSPManager()
    await manager._handle_rx_progress(uuid4(), _progress(RXState.VIS_DETECTED))


class TestPlayer:
    def test_disabled_config_never_touches_audio(self, monkeypatch):
        import sstv_core.accessibility.guidance_player as gp

        played = []
        monkeypatch.setitem(
            __import__("sys").modules,
            "sounddevice",
            SimpleNamespace(play=lambda *a, **k: played.append(a)),
        )
        player = GuidancePlayer(GuidanceConfig(enabled=False))
        player.play_lock_chime()
        player.play_complete_chime()
        assert played == []

    def test_enabled_config_plays_stereo_audio(self, monkeypatch):
        played = []
        monkeypatch.setitem(
            __import__("sys").modules,
            "sounddevice",
            SimpleNamespace(play=lambda data, **k: played.append(data)),
        )
        player = GuidancePlayer(
            GuidanceConfig(enabled=True, lock_chime_enabled=True)
        )
        player.play_lock_chime()
        assert len(played) == 1
        assert played[0].shape[1] == 2  # stereo

    def test_device_failure_never_raises(self, monkeypatch):
        def explode(*a, **k):
            raise RuntimeError("no output device")

        monkeypatch.setitem(
            __import__("sys").modules,
            "sounddevice",
            SimpleNamespace(play=explode),
        )
        player = GuidancePlayer(GuidanceConfig(enabled=True))
        player.play_lock_chime()  # must not raise
