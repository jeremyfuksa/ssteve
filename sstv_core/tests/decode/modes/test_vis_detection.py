"""VIS header detection: the mode auto-detect path.

VIS is how an SSTV transmission announces its own mode. Without it an operator
must know what is being sent and select it by hand, which is exactly the
manufactured difficulty PRODUCT.md says SSTeVe exists to remove.

None of these tests could be written against `tests/reference/audio/`: those
recordings were captured mid-transmission and contain no VIS header at all
(verified 2026-08-07 -- the signal begins directly in picture data). That is
why this gap survived a 488-test suite.
"""

from __future__ import annotations

import numpy as np
import pytest

from sstv_core.decode.correlation_vis_detector import (
    CorrelationVISConfig,
    CorrelationVISDetector,
)
from sstv_core.decode.vis_detector import SSTVMode
from sstv_core.encode.vis_generator import VISGenerator

RATE = 48000


class TestVISGenerator:
    """The generator is the working half."""

    @pytest.mark.parametrize(
        "mode", [SSTVMode.SCOTTIE_S1, SSTVMode.MARTIN_M1, SSTVMode.ROBOT_36]
    )
    def test_emits_a_spec_shaped_header(self, mode):
        """Header must open with the 300ms 1900 Hz leader the standard requires."""
        from sstv_core.decode.demodulator import instantaneous_frequency

        header = VISGenerator(sample_rate=RATE).generate(mode).astype(np.float32)

        duration_ms = len(header) / RATE * 1000
        assert 850 < duration_ms < 1000, f"header is {duration_ms:.0f}ms"

        freqs = instantaneous_frequency(header[: int(RATE * 0.25)], RATE)
        assert abs(float(np.median(freqs)) - 1900.0) < 30.0, (
            "header should open with a 1900 Hz leader"
        )


class TestVISDetector:
    @pytest.mark.parametrize(
        "mode", [SSTVMode.SCOTTIE_S1, SSTVMode.MARTIN_M1, SSTVMode.ROBOT_36]
    )
    def test_reads_a_header_this_project_generated(self, mode):
        """Round trip through our own VIS generator and detector.

        Leading and trailing audio on purpose. Detection needs the header to
        be fully inside the rolling buffer with at least one more chunk behind
        it, because the best alignment is only found once the whole header has
        arrived. Audio that stops dead at the final header sample scores 0.82
        against a 0.85 threshold and is missed -- an artifact of the fixture,
        since a real transmission always continues into picture data, but it
        does mean the detector cannot identify a header from a recording
        truncated the instant it ends.
        """
        header = VISGenerator(sample_rate=RATE).generate(mode).astype(np.float32)
        audio = np.concatenate([
            np.zeros(RATE // 2, dtype=np.float32),
            header,
            np.zeros(RATE // 2, dtype=np.float32),
        ])

        detector = CorrelationVISDetector(CorrelationVISConfig(sample_rate=RATE))

        result = None
        for offset in range(0, len(audio), 4096):
            result = detector.process_samples(audio[offset : offset + 4096])
            if result:
                break

        assert result is not None, f"{mode.name}: header not detected"
        assert result.mode == mode
        assert result.parity_valid

    def test_detector_runs_at_the_configured_sample_rate(self):
        """Guards the config plumbing, which is a separate bug from detection.

        rx_manager constructs CorrelationVISDetector() with no config, so it
        runs at the 48000 Hz default whatever the stream's real rate is -- the
        same class of defect fixed in the decoders on 2026-08-07. This asserts
        the config is at least honoured when passed, so a fix to rx_manager has
        something to rely on.
        """
        for rate in (11025, 22050, 48000):
            detector = CorrelationVISDetector(CorrelationVISConfig(sample_rate=rate))
            assert detector._config.sample_rate == rate
