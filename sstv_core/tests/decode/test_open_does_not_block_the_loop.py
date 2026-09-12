"""Opening a source must not freeze everything else (#135).

`RXManager.receive` opened its source on the event loop. For a sound card
that is a PortAudio call; for SpyServer it is a TCP connect plus the
DeviceInfo/ClientSync handshake, each read bounded by the stall timeout.
Measured at 40 ms against airspy.local on a LAN — and for as long as it
lasted, the API served nothing: no HTTP, no WebSocket, no waterfall. A
server that accepts the connection and then goes quiet holds it for
seconds, and public SpyServers are where that happens.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from sstv_core.audio.ring_buffer import AudioRingBuffer
from sstv_core.audio.stream_manager import AudioLevels
from sstv_core.decode.rx_manager import RXManager

SLOW_OPEN_SEC = 0.4


class SlowToOpen:
    """A source that takes its time, the way a real one does."""

    sample_rate = 48_000

    def __init__(self, open_delay: float = SLOW_OPEN_SEC) -> None:
        self._open_delay = open_delay
        self._buffer: AudioRingBuffer | None = None
        self.started_on: str | None = None
        self.events: list[str] = []

    def start_input(self, device_index=None, callback=None, buffer_size=None) -> None:
        self.events.append("start:begin")
        self.started_on = "loop" if _on_the_event_loop() else "thread"
        time.sleep(self._open_delay)  # blocking on purpose: that is the point
        self._buffer = AudioRingBuffer(max_samples=48_000, sample_rate=48_000)
        self.events.append("start:done")

    def stop_input(self) -> None:
        self.events.append("stop")

    def get_input_buffer(self):
        return self._buffer

    def get_input_levels(self) -> AudioLevels:
        return AudioLevels(rms=0.01, peak=0.02)


def _on_the_event_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


@pytest.mark.asyncio
async def test_the_loop_keeps_running_while_the_source_opens() -> None:
    """A heartbeat beside the decode must keep its schedule.

    This is the defect stated directly: the same 400 ms open used to stop
    every other coroutine for 400 ms, which in the product is the API
    going silent.
    """
    source = SlowToOpen()
    manager = RXManager(stream_manager=source, sample_rate=48_000)

    ticks: list[float] = []
    started = time.monotonic()

    async def heartbeat() -> None:
        for _ in range(8):
            await asyncio.sleep(0.05)
            ticks.append(time.monotonic() - started)

    decode = asyncio.create_task(manager.receive(timeout_sec=0.6, save_image=False))
    await asyncio.gather(heartbeat(), decode)

    assert source.started_on == "thread", "the open still runs on the event loop"
    # Every tick inside the open window should have landed. Allowing one
    # missed tick keeps this from failing on a loaded CI runner while still
    # catching a 400 ms freeze, which would drop six of the eight.
    during_open = [t for t in ticks if t <= SLOW_OPEN_SEC]
    assert len(during_open) >= 5, (
        f"only {len(during_open)} of ~8 heartbeats ran while the source opened: {ticks}"
    )


@pytest.mark.asyncio
async def test_a_cancel_mid_open_still_stops_the_source_afterwards() -> None:
    """Teardown waits for the open rather than racing it.

    Stopping a source that is still opening is worse than useless: for a
    sound card the stream the thread is about to create outlives the
    session that was cancelled.
    """
    source = SlowToOpen()
    manager = RXManager(stream_manager=source, sample_rate=48_000)

    decode = asyncio.create_task(manager.receive(timeout_sec=5.0, save_image=False))
    await asyncio.sleep(0.05)  # mid-open
    decode.cancel()
    with pytest.raises(asyncio.CancelledError):
        await decode

    assert source.events == ["start:begin", "start:done", "stop"], (
        f"teardown raced the open: {source.events}"
    )


@pytest.mark.asyncio
async def test_a_source_that_fails_to_open_still_reports_its_error() -> None:
    """The error has to survive the trip through the thread."""

    class Unreachable(SlowToOpen):
        def start_input(self, device_index=None, callback=None, buffer_size=None):
            raise RuntimeError("I couldn't reach the SpyServer at airspy.local:5555.")

    source = Unreachable()
    manager = RXManager(stream_manager=source, sample_rate=48_000)

    with pytest.raises(RuntimeError, match="airspy.local"):
        await manager.receive(timeout_sec=1.0, save_image=False)
