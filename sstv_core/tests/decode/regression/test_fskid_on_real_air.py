"""The callsign comes back from a real transmission, through the product.

FSKID's own tests feed the decoder pre-trimmed bursts, and they passed while
the live path never produced a callsign at all (#168). Two things were wrong,
and only a test that runs the whole path could see either:

- FSKID was attempted only after a complete 256-line frame. Both captures in
  the corpus that carry a verified callsign decode about 194 lines, because
  real transmissions fade. So it never ran on real air.
- The window was aimed three seconds past where the picture stopped
  decoding. The burst is where the *transmission* ends, which on these
  captures is 57-59s into a 75s recording -- by which time a decode that
  stalled at line 194 is still consuming audio.

These are the only two off-air recordings in the repository with a callsign
verified by its own checksum (2026-08-20), which makes them the only honest
oracle available.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from sstv_core.audio.file_source import FileSource
from sstv_core.decode.rx_manager import RXManager

CORPUS = Path(__file__).resolve().parents[2] / "reference" / "audio" / "offair"

VERIFIED = [
    ("cap2_010885s_martin_m2_kd2tt.wav", "MartinM2", "KD2TT"),
    ("cap2_011077s_martin_m2_va2pgb.wav", "MartinM2", "VA2PGB"),
]


@pytest.mark.slow
@pytest.mark.integration
@pytest.mark.parametrize(("capture", "mode", "callsign"), VERIFIED, ids=lambda v: str(v))
def test_the_callsign_comes_back(capture: str, mode: str, callsign: str) -> None:
    source = FileSource(CORPUS / capture)
    manager = RXManager(
        stream_manager=source,
        save_directory=Path(tempfile.mkdtemp()),
        auto_squelch=False,
    )

    asyncio.run(
        manager.receive(
            mode=mode, timeout_sec=source.duration_sec + 10, save_image=True
        )
    )

    result = manager.get_fskid_result()
    assert result is not None, f"no FSKID at all from {capture}"
    assert result.callsign == callsign
    assert result.checksum_valid, (
        "the callsign is only trustworthy when its own checksum validates; "
        "an unverified read is a guess"
    )


class TestTheSearch:
    """The unit underneath, so a failure says which half broke."""

    def test_it_finds_a_burst_wherever_it_sits(self) -> None:
        import soundfile as sf

        audio, rate = sf.read(CORPUS / VERIFIED[1][0], dtype="float32")
        manager = RXManager(stream_manager=object(), sample_rate=rate)

        # The whole recording: the search has to locate the burst itself,
        # which is the part that was missing.
        result = manager._search_for_fskid(audio)

        assert result is not None
        assert result.callsign == "VA2PGB"
        assert result.checksum_valid

    def test_silence_yields_nothing(self) -> None:
        import numpy as np

        manager = RXManager(stream_manager=object(), sample_rate=11025)

        assert manager._search_for_fskid(np.zeros(11025 * 5, dtype=np.float32)) is None

    def test_a_short_buffer_is_harmless(self) -> None:
        import numpy as np

        manager = RXManager(stream_manager=object(), sample_rate=11025)

        assert manager._search_for_fskid(np.zeros(100, dtype=np.float32)) is None
