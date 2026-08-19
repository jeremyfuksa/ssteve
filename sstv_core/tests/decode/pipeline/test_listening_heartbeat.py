"""RXManager reports input level while it waits for VIS.

Before this, the listening phase emitted exactly two progress events in a
run of any length: one before start_input() -- so its levels were the
initial zeros, whatever the signal -- and one at the timeout. Nothing
downstream could distinguish a quiet band from a deaf receiver while there
was still time to raise the gain (issue #90).
"""

from __future__ import annotations

import asyncio

import numpy as np
import pytest

from sstv_core.audio.ring_buffer import AudioRingBuffer
from sstv_core.audio.stream_manager import AudioLevels
from sstv_core.decode.rx_manager import RXManager, RXState


class _LevelSource:
    """A source that never carries SSTV, at a level the test chooses."""

    sample_rate = 48000

    def __init__(self, rms: float = 0.005) -> None:
        self._rms = rms
        self._buffer: AudioRingBuffer | None = None

    def start_input(self, device_index=None, callback=None, buffer_size=480000):
        self._buffer = AudioRingBuffer(max_samples=480000, sample_rate=48000)

    def stop_input(self) -> None:
        pass

    def get_input_buffer(self):
        # Fresh noise each poll, so the VIS detector has real work and the
        # loop behaves like a live listen rather than an empty one.
        self._buffer.add((np.random.randn(4800) * self._rms).astype(np.float32))
        return self._buffer

    def get_input_levels(self) -> AudioLevels:
        return AudioLevels(rms=self._rms, peak=self._rms * 4)


def listen(rms: float, timeout_sec: float) -> list:
    """Run one listen to timeout, returning the progress events seen."""
    src = _LevelSource(rms=rms)
    rx = RXManager(stream_manager=src, save_directory=None)
    events: list = []
    rx.set_progress_callback(events.append)
    result = asyncio.run(rx.receive(timeout_sec=timeout_sec, save_image=False))
    assert result is None, "this source carries no SSTV, so it must time out"
    return events


def test_listening_progress_is_emitted_more_than_once():
    """The defect: a 120-second listen used to report nothing in between."""
    listening = [e for e in listen(0.005, 6.0) if e.state is RXState.LISTENING]
    assert len(listening) > 1, "the listening phase reported only its opening event"


def test_the_heartbeat_carries_a_measured_level():
    """An event without levels would be no more useful than silence."""
    listening = [e for e in listen(0.005, 6.0) if e.state is RXState.LISTENING]
    # The first event fires before start_input, so its levels are the
    # source's initial reading; the heartbeats after it are the ones that
    # have to carry a real measurement.
    assert any(
        e.audio_levels is not None and e.audio_levels.rms == pytest.approx(0.005)
        for e in listening[1:]
    )


def test_the_heartbeat_is_throttled_not_per_poll():
    """The loop turns every 100 ms; a report per turn is unreadable."""
    listening = [e for e in listen(0.005, 6.0) if e.state is RXState.LISTENING]
    # ~6 seconds at a 5-second heartbeat: the opening event plus one or two.
    assert len(listening) <= 4, f"{len(listening)} events in 6s is too chatty"


def test_a_silent_source_still_gets_a_heartbeat():
    """The case that matters most.

    A deaf receiver may deliver no samples at all, and the level report
    sits ahead of the len(samples) guard precisely so those runs are still
    explained rather than silent.
    """

    class _Empty(_LevelSource):
        def get_input_buffer(self):
            return self._buffer  # never fed

    src = _Empty(rms=0.0)
    rx = RXManager(stream_manager=src, save_directory=None)
    events: list = []
    rx.set_progress_callback(events.append)
    asyncio.run(rx.receive(timeout_sec=6.0, save_image=False))

    listening = [e for e in events if e.state is RXState.LISTENING]
    assert len(listening) > 1, "a source delivering nothing reported nothing"
