"""Spectrum frames must actually reach a caller during a listen (#53).

The producer's own tests would all pass with this wiring deleted -- the
same gap that let three broken FSKID versions ship on 2026-08-19 and let
a stall predicate look correct while nothing called it. These drive
RXManager's real callback path.

Spectrum gets its own callback rather than a field on RXProgress: the
waterfall runs at 10-20 Hz and the listening heartbeat is every 5 s, so
sharing one channel would either flood the progress log or starve the
display.
"""

from __future__ import annotations

import numpy as np
import pytest

from sstv_core.decode.rx_manager import RXManager
from sstv_core.dsp.spectrum import SpectrumFrame

RATE = 48_000


def _tone(hz: float, samples: int, amplitude: float = 0.5) -> np.ndarray:
    t = np.arange(samples) / RATE
    return (amplitude * np.sin(2 * np.pi * hz * t)).astype(np.float32)


def _manager() -> RXManager:
    """An RXManager with no real audio hardware behind it.

    Nothing here starts a stream: every test drives emit_spectrum
    directly, which is the seam the listening loop calls.
    """

    class _NoStream:
        def get_input_levels(self) -> None:
            return None

    return RXManager(stream_manager=_NoStream())


class TestSpectrumCallback:
    def test_a_manager_starts_with_no_spectrum_callback(self) -> None:
        """Nothing is computed until someone asks: the FFT is pure cost
        for a headless decode with no waterfall attached."""
        assert _manager().get_spectrum_callback() is None

    def test_setting_a_callback_is_what_enables_the_producer(self) -> None:
        manager = _manager()
        manager.set_spectrum_callback(lambda frame: None)
        assert manager.get_spectrum_callback() is not None

    def test_frames_reach_the_callback(self) -> None:
        manager = _manager()
        seen: list[SpectrumFrame] = []
        manager.set_spectrum_callback(seen.append)

        manager.emit_spectrum(_tone(1500.0, 4096), RATE)

        assert seen, "a spectrum callback was set and never called"
        assert isinstance(seen[0], SpectrumFrame)

    def test_the_frame_describes_the_audio_it_was_given(self) -> None:
        """A callback that fires with a frame of nothing is worse than no
        callback -- it looks like the waterfall is working."""
        manager = _manager()
        seen: list[SpectrumFrame] = []
        manager.set_spectrum_callback(seen.append)

        manager.emit_spectrum(_tone(1500.0, 4096), RATE)

        assert seen[0].peak_hz == pytest.approx(1500.0, abs=seen[0].bin_hz * 2)

    def test_no_callback_means_no_work(self) -> None:
        """emit_spectrum must be safe and cheap on the headless path."""
        _manager().emit_spectrum(_tone(1500.0, 4096), RATE)

    def test_a_failing_callback_does_not_break_the_decode(self) -> None:
        """The waterfall is a display. A frontend that throws while
        rendering must not take the decode down with it."""
        manager = _manager()

        def explode(frame: SpectrumFrame) -> None:
            raise RuntimeError("frontend blew up")

        manager.set_spectrum_callback(explode)
        manager.emit_spectrum(_tone(1500.0, 4096), RATE)

    def test_short_buffers_emit_nothing(self) -> None:
        manager = _manager()
        seen: list[SpectrumFrame] = []
        manager.set_spectrum_callback(seen.append)

        manager.emit_spectrum(_tone(1500.0, 64), RATE)

        assert not seen, "a frame built from 64 samples is a picture of padding"

    def test_the_producer_is_reused_across_calls(self) -> None:
        """Rebuilding it per block would recompute the Hanning window and
        the band mask 15 times a second for no reason."""
        manager = _manager()
        manager.set_spectrum_callback(lambda frame: None)

        manager.emit_spectrum(_tone(1500.0, 4096), RATE)
        first = manager._spectrum_producer
        manager.emit_spectrum(_tone(1500.0, 4096), RATE)

        assert manager._spectrum_producer is first
