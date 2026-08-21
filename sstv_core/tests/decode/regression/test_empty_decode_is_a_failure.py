"""A decode that produced no scanlines must not report success.

Observed on air 2026-08-21, 14.230 MHz. The correlation detector read a VIS
as ROBOT_36 at 0.853 -- just over the 0.85 gate, and below the 0.873 of the
weakest *real* header in the off-air corpus. The signal was not SSTV: its
energy sat at 1544 and 2107 Hz inside the video band with little at the
1200 Hz sync (4506 against 1100 by FFT magnitude), which is what SSB voice
looks like to this pipeline.

The DSP then did the right thing with the wrong input. No sync pulses meant
no line starts, so the decode budget expired having completed nothing:

    Decode ran past its time budget at 0/240 lines; giving up rather than
    hanging.

And then the session reported success anyway:

    rx_progress: {'state': 'saving',   'line': 240, 'total': 240, 'percent': 95}
    rx_progress: {'state': 'complete', 'line': 240, 'total': 240, 'percent': 100}

An all-black 320x240 PNG -- every one of its 76800 pixels exactly zero --
was written into the image library as a received image.

The cause is that the save gate asked only whether an image object existed.
`decoder.reset()` allocates a zeroed buffer up front, so `get_image()`
returns a perfectly valid all-black array whether 240 lines decoded or none
did, and `is not None` cannot tell those apart. Line count can.

This matters beyond one lost picture. SSTeVe's product position is that an
operator can walk away, and the failure mode above is the worst shape that
can take: it manufactures a plausible-looking success out of nothing, adds a
black frame to the library, and increments the images-received count. A
false positive that reports failure costs a wasted decode attempt. One that
reports success costs the operator's trust in every image in the library --
and if such a frame were ever accepted as a reference render, it would pin
black as correct in the regression gate.

The VIS threshold is deliberately left alone. 0.85 is pinned by
`test_offair_corpus`, whose marginal file measures 0.873; moving the gate to
exclude one observed false positive would sit 0.002 from a real header and
start rejecting weak-but-genuine transmissions. Refusing to lie about the
outcome is the fix that does not trade away real detections.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import numpy as np
import pytest

from sstv_core.audio.ring_buffer import AudioRingBuffer
from sstv_core.decode.rx_manager import RXManager, RXState
from sstv_core.encode.vis_generator import SSTVMode, VISGenerator

SAMPLE_RATE = 48000


def _fake_stream(buffer: AudioRingBuffer):
    class FakeStream:
        def start_input(self, device_index=None):
            pass

        def stop_input(self):
            pass

        def get_input_buffer(self):
            return buffer

        def get_input_levels(self):
            return SimpleNamespace(rms=0.3, peak=0.5, is_clipping=False)

    return FakeStream()


def _vis_then_nothing_decodable(seconds: float = 40.0) -> np.ndarray:
    """A clean VIS header followed by audio carrying no sync pulses.

    This is the on-air situation reduced to its essentials: the pipeline is
    told a mode with confidence, then handed something it cannot decode. A
    steady 1700 Hz tone sits mid-video-band and never crosses 1200 Hz, so
    `SyncPulseDetector` finds no line starts -- exactly the 0/240 outcome.

    The body has to keep arriving for longer than the decode budget. Let the
    audio simply run out instead and the loop exits down the "audio stopped"
    path at rx_manager.py:766, which already raises and already declines to
    save -- a different branch from the one that failed on air, where samples
    kept coming and the *budget* was what expired.
    """
    vis = VISGenerator(sample_rate=SAMPLE_RATE).generate(SSTVMode.ROBOT_36)
    t = np.arange(int(SAMPLE_RATE * seconds)) / SAMPLE_RATE
    body = 0.5 * np.sin(2 * np.pi * 1700.0 * t)
    return np.concatenate([vis, body.astype(np.float32)])


async def _receive(audio: np.ndarray, tmp_path, monkeypatch):
    buffer = AudioRingBuffer(max_samples=SAMPLE_RATE * 20)
    progress: list = []

    # Robot 36's real budget is 3x its ~36s nominal, floored at 60s -- 108s,
    # far too long for a test. Shrink it so the decode loop reaches the same
    # deadline branch (rx_manager.py:703) in a couple of seconds.
    monkeypatch.setattr(RXManager, "DECODE_BUDGET_FACTOR", 0.05)
    monkeypatch.setattr(RXManager, "MIN_DECODE_BUDGET_SEC", 2.0)

    rx = RXManager(
        stream_manager=_fake_stream(buffer),
        sample_rate=SAMPLE_RATE,
        save_directory=tmp_path,
    )
    rx.set_progress_callback(progress.append)

    async def feeder():
        """Keep audio arriving for the whole decode, looping the body.

        The on-air failure had a live SDR still delivering samples when the
        budget ran out. A feeder that stops early exercises a different
        branch, so this one never runs dry.
        """
        offset = 0
        chunk = SAMPLE_RATE // 4
        body_start = len(audio) // 4
        while True:
            if len(buffer) < SAMPLE_RATE // 2:
                if offset >= len(audio):
                    offset = body_start  # loop the un-decodable body
                buffer.add(audio[offset : offset + chunk])
                offset += chunk
            await asyncio.sleep(0.001)

    feed_task = asyncio.create_task(feeder())
    try:
        result = await asyncio.wait_for(
            rx.receive(timeout_sec=12.0, save_image=True), timeout=120
        )
    finally:
        feed_task.cancel()

    return rx, result, progress, tmp_path


@pytest.mark.slow
@pytest.mark.asyncio
async def test_zero_line_decode_saves_no_image(tmp_path, monkeypatch) -> None:
    """Nothing decoded means nothing lands in the image library."""
    _, result, _, save_dir = await _receive(
        _vis_then_nothing_decodable(), tmp_path, monkeypatch
    )

    written = list(save_dir.glob("**/*.png"))
    assert not written, (
        f"a decode that completed no scanlines wrote {[p.name for p in written]}; "
        f"an all-black frame in the library is indistinguishable from a real "
        f"picture of a dark scene"
    )
    assert result is None, f"expected no result for an empty decode, got {result!r}"


@pytest.mark.slow
@pytest.mark.asyncio
async def test_zero_line_decode_does_not_report_complete(
    tmp_path, monkeypatch
) -> None:
    """The session must not claim 100% for a decode that produced nothing."""
    _, _, progress, _ = await _receive(
        _vis_then_nothing_decodable(), tmp_path, monkeypatch
    )

    states = [getattr(p, "state", None) for p in progress]
    assert RXState.COMPLETE not in states, (
        f"empty decode reported COMPLETE; states were {states}"
    )

    percents = [getattr(p, "percent_complete", 0) for p in progress]
    assert max(percents, default=0) < 100, (
        f"empty decode reported {max(percents)}% complete"
    )
