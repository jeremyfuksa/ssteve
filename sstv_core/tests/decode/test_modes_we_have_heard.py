"""Every mode we have actually heard on air must decode in the product.

moscow.md, 2026-08-21: "Every mode we have actually heard is broken
somewhere." The corpus is 6 Scottie S2, 4 Martin M1, 4 Martin M2 — and
Robot 36, which has never appeared in a capture, was the only mode that
worked end to end without a caveat.

Two defects, both in lists rather than in DSP:

- Martin M2 decoded in the test suite and nowhere else. `test_offair_corpus`
  maps it to MartinM1Decoder + MartinM2Config and all four fixtures pass
  pixel-exact, but `RXManager._get_decoder` had no branch for it, so the
  product answered "I can't decode that yet" for both of the only two
  off-air captures carrying a verified FSKID callsign (#140).
- The API restated the engine's mode list and drifted from it, refusing a
  forced ScottieS2 — the most-captured mode we have (#153).

**What these tests gate is the wiring, not decode quality.** Quality is
pinned per-mode by the accepted renders in
`tests/decode/regression/test_offair_corpus.py`. A cross-pipeline pixel
comparison would be the wrong instrument here: RXManager finds its own sync
origin and decodes a full frame where the corpus fixture's accepted render
stops early, so the same picture scores badly against it for reasons that
have nothing to do with correctness (measured 2026-09-11: 0.82 correlation
on one M2 capture, 0.29 on another, both plainly the same picture).
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from sstv_core.audio.file_source import FileSource
from sstv_core.decode.martin_decoder import MartinM1Decoder, MartinM2Config
from sstv_core.decode.rx_manager import RXManager

CORPUS = Path(__file__).resolve().parents[1] / "reference" / "audio" / "offair"

#: Modes with at least one off-air capture (manifest.json, 2026-08-20).
HEARD_ON_AIR = ("ScottieS2", "MartinM1", "MartinM2")


class TestTheEngineCanReachEveryModeWeHaveHeard:
    @pytest.mark.parametrize("mode", HEARD_ON_AIR)
    def test_a_decoder_exists(self, mode: str) -> None:
        manager = RXManager(stream_manager=object())
        assert manager._get_decoder(mode) is not None, (
            f"{mode} is in our captures and the product cannot decode it"
        )

    @pytest.mark.parametrize("mode", HEARD_ON_AIR)
    def test_it_is_advertised(self, mode: str) -> None:
        assert mode in RXManager.DECODABLE_MODES

    def test_martin_m2_uses_m2_timing(self) -> None:
        """The bug was a missing branch; M1 timing would decode a slanted mess."""
        decoder = RXManager(stream_manager=object())._get_decoder("MartinM2")
        assert isinstance(decoder, MartinM1Decoder)
        assert decoder.config.color_scan_duration_ms == MartinM2Config().color_scan_duration_ms


class TestTheAPIAdvertisesWhatTheEngineCanDo:
    def test_the_api_list_is_the_engine_list(self) -> None:
        """Derived, not restated. Two hand-maintained lists is the defect."""
        from sstv_core.api.routes.decode import SUPPORTED_DECODE_MODES

        assert set(SUPPORTED_DECODE_MODES) == set(RXManager.DECODABLE_MODES)

    @pytest.mark.parametrize("mode", HEARD_ON_AIR)
    def test_forcing_a_heard_mode_is_accepted(self, mode: str) -> None:
        from fastapi.testclient import TestClient

        from sstv_core.api.main import app
        from sstv_core.api.session_manager import session_manager

        response = TestClient(app).post(
            "/api/v1/decode/start", json={"mode": mode, "auto_detect": False}
        )
        session_manager.reset()
        assert response.status_code == 201, response.text

    def test_a_mode_we_cannot_decode_is_still_refused_by_name(self) -> None:
        from fastapi.testclient import TestClient

        from sstv_core.api.main import app

        response = TestClient(app).post(
            "/api/v1/decode/start", json={"mode": "PD120", "auto_detect": False}
        )
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "PD120" in detail["message"]
        assert "MartinM2" in detail["suggested_action"]


@pytest.mark.slow
@pytest.mark.integration
def test_a_real_martin_m2_capture_decodes_through_the_product() -> None:
    """The end the product actually uses: audio in, a picture out.

    Before the fix this produced no image at all -- VIS identified MartinM2
    and the session stopped with "no decoder available". Replayed at the
    speed it was recorded, through the same RXManager a live SpyServer
    decode uses.
    """
    capture = CORPUS / "cap2_010885s_martin_m2_kd2tt.wav"
    source = FileSource(capture)
    manager = RXManager(
        stream_manager=source,
        save_directory=Path(tempfile.mkdtemp()),
        auto_squelch=False,
    )

    saved = asyncio.run(
        manager.receive(
            mode="MartinM2", timeout_sec=source.duration_sec + 5, save_image=True
        )
    )

    assert saved is not None, "MartinM2 produced no picture"
    metrics = manager.get_decode_metrics()
    lines = len(metrics.scanline_confidences) if metrics else 0
    assert lines >= 150, f"only {lines} scanlines from a complete transmission"

    picture = np.asarray(Image.open(saved).convert("L"), dtype=float)
    # Not a quality measure -- a liveness one. A frame of one flat colour is
    # what a wrong decoder branch produces; the accepted-render gate in
    # test_offair_corpus is what protects the pixels.
    assert picture.std() > 20, "the picture carries no structure"
