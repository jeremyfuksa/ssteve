"""RXManager must not silently disagree with its stream manager's rate."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from sstv_core.audio.ring_buffer import AudioRingBuffer
from sstv_core.decode.rx_manager import RXManager


class FakeStream:
    """Four-method stream-manager duck type at a chosen sample rate."""

    def __init__(self, sample_rate: int) -> None:
        self.sample_rate = sample_rate
        self._buffer = AudioRingBuffer(max_samples=sample_rate)

    def start_input(self, device_index=None) -> None:
        pass

    def stop_input(self) -> None:
        pass

    def get_input_buffer(self) -> AudioRingBuffer:
        return self._buffer

    def get_input_levels(self):
        return SimpleNamespace(rms=0.0, peak=0.0, is_clipping=False)


def test_conflicting_sample_rate_is_rejected():
    with pytest.raises(ValueError, match="sample rate"):
        RXManager(stream_manager=FakeStream(22050), sample_rate=48000)


def test_rate_is_adopted_from_stream_manager_when_unspecified():
    rx = RXManager(stream_manager=FakeStream(22050))
    assert rx._sample_rate == 22050


def test_matching_rate_is_accepted():
    rx = RXManager(stream_manager=FakeStream(48000), sample_rate=48000)
    assert rx._sample_rate == 48000


def test_stream_manager_without_sample_rate_falls_back_to_argument():
    """A duck type need not expose sample_rate; the explicit arg still wins."""

    class RatelessStream(FakeStream):
        def __init__(self) -> None:
            super().__init__(48000)
            del self.sample_rate

    rx = RXManager(stream_manager=RatelessStream(), sample_rate=48000)
    assert rx._sample_rate == 48000
