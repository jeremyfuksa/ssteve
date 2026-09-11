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


@pytest.mark.slow
@pytest.mark.integration
async def test_the_waterfall_keeps_running_while_a_picture_decodes() -> None:
    """Frames flow through the decode, not only the listen before it.

    The single-window design makes the waterfall "always visible" and its
    job "visual proof that reception is happening". Until 2026-09-11 only
    the listen loop fed it, so it froze the moment a decode began -- the
    one stretch when reception most certainly is happening. Measured over
    the API on a 124 s Martin M1 replay: 22 frames, all before VIS.

    The mode is forced so the whole replay is decode phase, and so the
    test does not depend on VIS detection (see #137).
    """
    from sstv_core.encode.robot_encoder import Robot36Encoder
    from tests.decode.regression.test_realtime_starvation import (
        RealtimeSource,
        _gradient,
    )

    encoder = Robot36Encoder()
    audio = encoder.encode_image(
        _gradient(encoder.config.width, encoder.config.height), include_vis=True
    )
    source = RealtimeSource(audio, speed=4.0)
    manager = RXManager(stream_manager=source, sample_rate=RATE)

    state = {"now": None}
    decode_frames: list[SpectrumFrame] = []
    manager.set_progress_callback(lambda p: state.update(now=p.state.value))
    manager.set_spectrum_callback(
        lambda f: decode_frames.append(f) if state["now"] == "decoding" else None
    )

    await manager.receive(mode="Robot36", timeout_sec=30.0, save_image=False)

    # ~9 s of wall clock for 36 s of audio at 4x. The throttle counts audio
    # time (10-20 frames per second of signal), so a working waterfall
    # yields hundreds; one frame per turn would still be dozens.
    assert len(decode_frames) > 50, (
        f"{len(decode_frames)} waterfall frames during the decode -- the "
        "waterfall froze while the picture came in"
    )
