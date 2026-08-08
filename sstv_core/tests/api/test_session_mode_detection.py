"""Session-based mode detection: the stub is gone; real audio is analyzed.

POST /decode/detect_mode with a session_id previously returned
SESSION_ANALYSIS_NOT_SUPPORTED unconditionally.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from sstv_core.api.main import app

SAMPLE_RATE = 48000


def martin_timing_audio(duration_sec: float = 10.0) -> np.ndarray:
    """Textbook Martin M1 sync timing: 4.862 ms 1200 Hz pulses every
    446.446 ms, mid-grey video between."""
    n = int(duration_sec * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE
    audio = 0.5 * np.sin(2 * np.pi * 1900.0 * t)
    period = int(0.446446 * SAMPLE_RATE)
    sync_len = int(0.004862 * SAMPLE_RATE)
    for start in range(0, n - sync_len, period):
        ts = np.arange(sync_len) / SAMPLE_RATE
        audio[start : start + sync_len] = 0.5 * np.sin(2 * np.pi * 1200.0 * ts)
    return audio.astype(np.float32)


class TestRollingWindow:
    def test_rx_manager_retains_recent_audio(self):
        from sstv_core.decode.rx_manager import RXManager

        rx = RXManager(stream_manager=SimpleNamespace(), sample_rate=SAMPLE_RATE)
        rx._analysis_window = np.zeros(0, dtype=np.float32)
        for _ in range(20):
            rx._extend_analysis_window(np.ones(SAMPLE_RATE, dtype=np.float32))
        window = rx.get_recent_audio()
        # Capped at 15 s
        assert len(window) == SAMPLE_RATE * 15


class TestSessionDetection:
    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_detects_martin_from_session_audio(self, client, monkeypatch):
        from sstv_core.api.routes import decode as decode_route
        from sstv_core.api.session_manager import session_manager

        import asyncio

        session = asyncio.run(session_manager.create_decode_session(metadata={}))
        try:
            monkeypatch.setattr(
                decode_route.dsp_manager,
                "get_session_audio",
                lambda _sid: martin_timing_audio(),
            )
            response = client.post(
                "/api/v1/decode/detect_mode",
                json={"session_id": str(session.session_id)},
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["mode"] == "MartinM1"
            assert body["confidence"] >= 0.85
        finally:
            session_manager.reset()

    def test_not_enough_audio_is_an_honest_400(self, client, monkeypatch):
        from sstv_core.api.routes import decode as decode_route
        from sstv_core.api.session_manager import session_manager

        import asyncio

        session = asyncio.run(session_manager.create_decode_session(metadata={}))
        try:
            monkeypatch.setattr(
                decode_route.dsp_manager, "get_session_audio", lambda _sid: None
            )
            response = client.post(
                "/api/v1/decode/detect_mode",
                json={"session_id": str(session.session_id)},
            )
            assert response.status_code == 400
            assert response.json()["detail"]["error"] == "NOT_ENOUGH_AUDIO"
        finally:
            session_manager.reset()
