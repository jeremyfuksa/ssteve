"""Decoding a recording over the API (#61).

The shell is being built against a band that is silent 97.4% of the time.
A recording replayed through the live pipeline -- same RXManager, same
events, same waterfall -- is how it gets something to draw on demand.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
import soundfile as sf

from sstv_core.api import dsp_manager as dsp_module
from sstv_core.api.dsp_manager import DecodeSourceError, DSPManager
from sstv_core.api.session_manager import session_manager
from sstv_core.audio.file_source import ENGINE_RATE, FileSource


@pytest.fixture
def tone_wav(tmp_path) -> Path:
    """Two seconds of 1900 Hz at 11025 Hz, the corpus's own rate."""
    rate = 11_025
    t = np.arange(rate * 2) / rate
    path = tmp_path / "tone.wav"
    sf.write(path, (0.5 * np.sin(2 * np.pi * 1900 * t)).astype(np.float32), rate)
    return path


class TestFileSource:
    def test_resamples_to_the_engine_rate_without_changing_the_length(self, tone_wav):
        source = FileSource(tone_wav)
        assert source.sample_rate == ENGINE_RATE
        # A rate error would show up here as a longer or shorter recording
        # -- and as slant in every picture decoded from it.
        assert source.duration_sec == pytest.approx(2.0, abs=0.001)

    def test_replays_at_the_speed_it_was_recorded(self, tone_wav):
        source = FileSource(tone_wav)
        source.start_input()
        try:
            time.sleep(0.5)
            buffered = len(source.get_input_buffer())
        finally:
            source.stop_input()
        # Real time means ~0.5 s of audio after 0.5 s. A free-running
        # feeder would have delivered all two seconds at once, overrunning
        # the VIS detector's window.
        assert 0.3 * ENGINE_RATE < buffered < 0.8 * ENGINE_RATE

    def test_levels_follow_the_audio(self, tone_wav):
        source = FileSource(tone_wav)
        source.start_input()
        try:
            time.sleep(0.2)
            rms = source.get_input_levels().rms
        finally:
            source.stop_input()
        assert rms == pytest.approx(0.5 / np.sqrt(2), rel=0.05)

    def test_stop_ends_the_replay(self, tone_wav):
        source = FileSource(tone_wav)
        source.start_input()
        time.sleep(0.1)
        source.stop_input()
        held = len(source.get_input_buffer())
        time.sleep(0.2)
        assert len(source.get_input_buffer()) == held

    def test_unreadable_file_fails_at_construction(self, tmp_path):
        bogus = tmp_path / "not_audio.wav"
        bogus.write_text("this is not a wav file")
        with pytest.raises(RuntimeError):
            FileSource(bogus)


def _start(dsp: DSPManager, **kwargs: Any):
    base: dict[str, Any] = dict(
        session_id=uuid.uuid4(),
        mode=None,
        auto_detect=True,
        timeout_seconds=300.0,
        save_image=False,
        callsign=None,
        device_id=None,
    )
    base.update(kwargs)
    return dsp.start_decode(**base)


@pytest.fixture
def dsp() -> DSPManager:
    manager = DSPManager()
    manager._device_manager_instance = SimpleNamespace(get_device_index=lambda _id: None)
    return manager


class TestRequestValidation:
    @pytest.mark.asyncio
    async def test_file_source_needs_a_path(self, dsp):
        with pytest.raises(DecodeSourceError, match="recording") as exc:
            await _start(dsp, source="file")
        assert "file_path" in exc.value.suggested_action

    @pytest.mark.asyncio
    async def test_missing_file_is_named(self, dsp, tmp_path):
        with pytest.raises(DecodeSourceError, match="nope.wav"):
            await _start(dsp, source="file", file_path=str(tmp_path / "nope.wav"))
        assert not dsp._rx_managers

    @pytest.mark.asyncio
    async def test_path_without_the_file_source_is_refused(self, dsp, tone_wav):
        with pytest.raises(DecodeSourceError, match="file_path"):
            await _start(dsp, source="audio", file_path=str(tone_wav))

    @pytest.mark.asyncio
    async def test_a_recording_cannot_be_tuned(self, dsp, tone_wav):
        with pytest.raises(DecodeSourceError, match="recording"):
            await _start(dsp, source="file", file_path=str(tone_wav), band="20m")


class TestWiring:
    @pytest.mark.asyncio
    async def test_listen_ends_with_the_recording_and_provenance_is_unknown(
        self, dsp, monkeypatch, tone_wav
    ):
        captured: dict[str, Any] = {}

        class CapturingRX:
            def __init__(self, *args, **kwargs):
                captured["source"] = kwargs["stream_manager"]
                captured["auto_squelch"] = kwargs["auto_squelch"]

            def set_progress_callback(self, cb):
                pass

            async def receive(self, **kwargs):
                captured["timeout_sec"] = kwargs["timeout_sec"]
                return None

            async def cancel(self):
                pass

            def get_unsupported_mode(self):
                return None

        async def broadcast(session_id, payload):
            pass

        monkeypatch.setattr(dsp_module, "RXManager", CapturingRX)
        monkeypatch.setattr(dsp_module.websocket_manager, "broadcast", broadcast)

        session = await session_manager.create_decode_session(metadata={})
        try:
            await _start(
                dsp,
                session_id=session.session_id,
                source="file",
                file_path=str(tone_wav),
            )
            provenance = dsp._provenance[session.session_id]
            await dsp._decode_tasks[session.session_id]
        finally:
            session_manager.reset()

        assert isinstance(captured["source"], FileSource)
        # Squelch is a sound-card setting; raw captures sit below -40 dB.
        assert captured["auto_squelch"] is False
        # A 2 s recording listens for 2 s and a little, not the 300 asked.
        assert captured["timeout_sec"] == pytest.approx(4.0, abs=0.01)
        assert provenance == {
            "source": "file",
            "receiver": None,
            "heard_at": None,
            "frequency_hz": None,
        }


class TestRoute:
    def test_route_forwards_the_path(self, mock_dsp_manager, tone_wav):
        from fastapi.testclient import TestClient

        from sstv_core.api.main import app

        response = TestClient(app).post(
            "/api/v1/decode/start",
            json={"source": "file", "file_path": str(tone_wav)},
        )
        assert response.status_code == 201, response.text
        kwargs = mock_dsp_manager.start_decode.await_args.kwargs
        assert kwargs["source"] == "file"
        assert kwargs["file_path"] == str(tone_wav)
        session_manager.reset()
