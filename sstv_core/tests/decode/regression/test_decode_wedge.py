"""A decode that locks VIS but never finishes has to give up (issue #94).

Found on the first real over-the-air reception. A weak Martin M1 on 20m
detected VIS correctly, entered `receiving`, and then sat at line 0/256 for
350+ seconds -- no progress, no error, no timeout -- while the audio tee
showed the radio still delivering at realtime. It also held the SpyServer's
single client slot for the whole time, so nothing else could receive.

The cause is that every other guard in the decoding loop is reachable only
from the `len(samples) == 0` branch: both the end-of-signal flush and the
5-second TimeoutError assume the audio eventually stops. On a live network
source it does not. A permanently-fed buffer therefore keeps the loop alive
indefinitely, and nothing bounds the decode phase in wall-clock terms.

`--timeout` does not help: it bounds VIS detection only (rx_manager ~line
357), and by this point VIS has already been found.
"""

from __future__ import annotations

import asyncio
import threading
import time

import numpy as np
import pytest

from sstv_core.audio.ring_buffer import AudioRingBuffer
from sstv_core.audio.stream_manager import AudioLevels
from sstv_core.decode.rx_manager import RXManager
from sstv_core.encode.vis_generator import SSTVMode, VISGenerator

#: Seconds, not milliseconds. Runs in the slow CI job so the rest of the
#: suite can report quickly -- see pytest.ini.
pytestmark = pytest.mark.slow

SAMPLE_RATE = 48000


class _NeverSyncs:
    """A real VIS header, then audio that never yields a scanline.

    Plain noise, deliberately: the point is a buffer that never empties, so
    the loop can never reach the `len(samples) == 0` branch where all the
    existing escapes live. A real source fills from its own I/O thread and
    RXManager takes the buffer reference exactly once, so the refill has to
    happen off to the side rather than in get_input_buffer().
    """

    sample_rate = SAMPLE_RATE

    def __init__(self, mode: SSTVMode = SSTVMode.MARTIN_M1) -> None:
        self._buffer: AudioRingBuffer | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._mode = mode

    def start_input(self, device_index=None, callback=None, buffer_size=480000):
        self._buffer = AudioRingBuffer(max_samples=480000, sample_rate=SAMPLE_RATE)
        vis = VISGenerator(sample_rate=SAMPLE_RATE).generate(self._mode)
        self._buffer.add(np.asarray(vis, dtype=np.float32))
        self._running = True
        self._thread = threading.Thread(target=self._fill_forever, daemon=True)
        self._thread.start()

    def _fill_forever(self) -> None:
        assert self._buffer is not None
        rng = np.random.default_rng(1234)
        while self._running:
            # Small blocks, well under the ring buffer's capacity, so the
            # decode loop always finds samples but never a sync pulse.
            self._buffer.add((rng.standard_normal(2400) * 0.01).astype(np.float32))
            time.sleep(0.02)

    def stop_input(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def get_input_buffer(self):
        assert self._buffer is not None
        return self._buffer

    def get_input_levels(self) -> AudioLevels:
        return AudioLevels(rms=0.01, peak=0.04)


def _run(rx: RXManager, timeout_sec: float = 5.0, hard_limit: float = 400.0):
    """Run one receive, failing loudly if it hangs rather than hanging."""

    async def go():
        return await asyncio.wait_for(
            rx.receive(timeout_sec=timeout_sec, save_image=False), timeout=hard_limit
        )

    return asyncio.run(go())


class TestDecodeBudget:
    def test_the_budget_scales_with_the_mode_not_a_fixed_constant(self):
        """A constant would either starve a slow mode or coddle a fast one.

        Martin M1 is ~114s nominal; at 3x that is ~342s, comfortably past
        any healthy decode and far short of the observed 350s+ hang being
        unbounded.
        """
        assert RXManager.DECODE_BUDGET_FACTOR >= 2.0, (
            "a factor near 1 would abort decodes that are merely slow"
        )
        assert RXManager.MIN_DECODE_BUDGET_SEC >= 36.0, (
            "the floor must exceed the shortest mode's own nominal time"
        )

    def test_a_decode_that_never_syncs_gives_up_instead_of_hanging(self):
        """The regression itself.

        Shortened budget so the test is quick; the mechanism under test is
        the wall-clock ceiling, not its production value. Without the
        guard this runs until the hard limit and fails.
        """
        src = _NeverSyncs()
        rx = RXManager(stream_manager=src, save_directory=None)
        rx.DECODE_BUDGET_FACTOR = 0.05  # type: ignore[misc]
        rx.MIN_DECODE_BUDGET_SEC = 8.0  # type: ignore[misc]

        started = time.monotonic()
        result = _run(rx, timeout_sec=5.0, hard_limit=120.0)
        elapsed = time.monotonic() - started

        assert result is None, "noise must not produce an image"
        # VIS detection plus the 8s budget plus slack -- and far below the
        # unbounded hang this exists to prevent.
        assert elapsed < 60.0, f"decode took {elapsed:.0f}s to give up"

    def test_giving_up_is_not_reported_as_a_crash(self):
        """The operator gets a finished session, not a traceback.

        A raise here would surface as "The SpyServer decode failed" and
        blame the radio for a decoder that simply ran out of budget.
        """
        src = _NeverSyncs()
        rx = RXManager(stream_manager=src, save_directory=None)
        rx.DECODE_BUDGET_FACTOR = 0.05  # type: ignore[misc]
        rx.MIN_DECODE_BUDGET_SEC = 8.0  # type: ignore[misc]

        # No exception escaping is the assertion.
        assert _run(rx, timeout_sec=5.0, hard_limit=120.0) is None
