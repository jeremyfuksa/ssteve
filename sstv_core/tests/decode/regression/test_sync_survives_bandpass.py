"""The decode bandpass must not eat the sync pulse (issue #100).

Live decodes stopped around 138/256 lines on a signal that spectral
measurement showed was strong for another 50 seconds. It was not
abandonment: the decoder never saw the sync pulses.

`BandpassPresets.standard()` was 1200-2300 Hz and the SSTV sync tone is
1200 Hz -- exactly the lower edge, where a 4th-order Butterworth is already
-3 dB and falling steeply. Measured on the XE2UD transmission from the
2026-08-16 capture, filtering before sync detection cut raw pulse detections
from 2945 to 189, a 94% loss:

    unfiltered              raw=2945  kept=427  clean 82%
    bandpassed (1200 Hz)    raw= 189  kept=141  clean 48%

141 accepted pulses is 138 decoded lines, which is exactly what #100
reported. Sweeping the lower edge on the same audio:

    none    kept=427  clean 82%
    1200    kept=103  clean 54%
    1100    kept=353  clean 76%
    1000    kept=430  clean 87%   <- chosen
     900    kept=447  clean 78%
     800    kept=458  clean 67%

1000 Hz passes the sync tone with margin and still rejects out-of-band
noise; it scores better than no filter at all, which is the point of having
one. Below 900 the filter starts admitting noise that produces spurious
pulses, so lower is not simply better.

These tests are unit-level on purpose. The end-to-end consequence is covered
by `test_realtime_starvation.py`; what must not regress here is the specific
relationship between the passband edge and the sync frequency.
"""

from __future__ import annotations

import numpy as np
import pytest

from sstv_core.audio.bandpass_filter import BandpassPresets, SSTVBandpassFilter
from sstv_core.decode.scottie_decoder import ScottieS1Config
from sstv_core.decode.sync_detector import SyncPulseDetector

RATE = 48000
SYNC_FREQ = 1200.0


def _tone(freq: float, ms: float, rate: int = RATE) -> np.ndarray:
    n = int(rate * ms / 1000.0)
    t = np.arange(n) / rate
    return (np.sin(2 * np.pi * freq * t) * 0.8).astype(np.float32)


@pytest.mark.parametrize(
    "preset",
    [
        BandpassPresets.standard(),
        BandpassPresets.weak_signal(),
    ],
)
def test_preset_passband_includes_the_sync_tone(preset):
    """A passband that starts at or above 1200 Hz cannot pass sync.

    The sync pulse is the only timing reference a decoder has. Filtering it
    out does not degrade the picture gracefully -- it removes the decoder's
    ability to find line boundaries at all.
    """
    assert preset.low_freq < SYNC_FREQ, (
        f"passband starts at {preset.low_freq} Hz, but the sync tone is "
        f"{SYNC_FREQ} Hz -- sync sits on or outside the edge"
    )


def test_sync_tone_survives_the_standard_filter():
    """Amplitude of a pure 1200 Hz tone must survive the decode filter.

    Measured on the filter directly rather than through the detector, so a
    failure points at the passband rather than at detection thresholds.
    """
    tone = _tone(SYNC_FREQ, 500.0)
    filtered = SSTVBandpassFilter(BandpassPresets.standard()).filter(tone)

    # Compare RMS over the settled portion; the first few ms are filter
    # transient regardless of passband.
    settle = RATE // 10
    before = float(np.sqrt(np.mean(tone[settle:] ** 2)))
    after = float(np.sqrt(np.mean(filtered[settle:] ** 2)))
    retained = after / before

    assert retained > 0.7, (
        f"the standard filter retains only {retained:.1%} of a {SYNC_FREQ} Hz "
        "sync tone; the decoder cannot find line starts it cannot hear"
    )


def test_filtering_does_not_destroy_sync_detection():
    """End-to-end on synthetic signal: filtered detection ~ unfiltered.

    Builds a Scottie S1 sync train -- 9 ms at 1200 Hz once per 428.22 ms line,
    with mid-band picture content between -- and checks the filter does not
    cost most of the pulses. The real capture showed a 94% loss; anything in
    that neighbourhood fails here.
    """
    cfg = ScottieS1Config(sample_rate=RATE)
    line_ms = 1000.0 * cfg.total_line_samples / RATE

    rng = np.random.default_rng(20260817)
    parts = []
    for _ in range(40):
        parts.append(_tone(SYNC_FREQ, cfg.sync_duration_ms))
        # Picture content: mid-band tones, the thing the filter is for.
        remaining = line_ms - cfg.sync_duration_ms
        parts.append(_tone(float(rng.uniform(1500, 2300)), remaining))
    audio = np.concatenate(parts)

    def count(sig: np.ndarray) -> int:
        det = SyncPulseDetector(sample_rate=RATE)
        det.detect_in_buffer(sig)
        return len(det.get_sync_positions(line_duration_ms=line_ms))

    unfiltered = count(audio)
    filtered = count(SSTVBandpassFilter(BandpassPresets.standard()).filter(audio))

    assert unfiltered >= 30, (
        f"only {unfiltered} pulses found in a clean 40-line sync train; "
        "the fixture is wrong, not the filter"
    )
    assert filtered >= unfiltered * 0.8, (
        f"filtering cut sync detections from {unfiltered} to {filtered} "
        "-- the passband is eating the sync tone (#100)"
    )


def test_passband_still_rejects_out_of_band_noise():
    """The filter must keep doing its job.

    Guards the obvious over-correction: widening the passband until it passes
    everything would fix sync detection and lose the noise rejection the
    filter exists for.
    """
    preset = BandpassPresets.standard()
    filt = SSTVBandpassFilter(preset)
    settle = RATE // 10

    for freq in (300.0, 500.0, 3500.0):
        tone = _tone(freq, 500.0)
        out = filt.filter(tone)
        before = float(np.sqrt(np.mean(tone[settle:] ** 2)))
        after = float(np.sqrt(np.mean(out[settle:] ** 2)))
        assert after / before < 0.25, (
            f"{freq} Hz passes at {after / before:.1%} -- the passband is too "
            "wide to reject out-of-band noise"
        )
