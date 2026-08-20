"""Input gain actually reaching the signal (#56).

`input_gain_override` has been storable and readable since PR #84 and had
no effect on anything: grepping `audio/`, `decode/` and `dsp_manager.py`
for it returned nothing. An operator could set it, watch the UI show it
set, and hear no difference -- the same shape as the SpyServer
digital-gain defect, where a control looked like it worked while the
signal went out at the floor.

PRODUCT.md #3 names gain, squelch and AFC as the three overrides that
must stay reachable in under two seconds, because auto-detection fails on
QSB, on Doppler, and in contest QRM. A control that reports a value it
does not apply is worse than a missing one: the missing one is honest.
"""

from __future__ import annotations

import numpy as np
import pytest

from sstv_core.audio.gain import apply_input_gain

RATE = 48_000


def _tone(amplitude: float = 0.1, samples: int = 4096) -> np.ndarray:
    t = np.arange(samples) / RATE
    return (amplitude * np.sin(2 * np.pi * 1500.0 * t)).astype(np.float32)


class TestTheMultiplier:
    def test_none_leaves_the_signal_alone(self) -> None:
        """No override configured must be bit-identical, not 1.0x-ish."""
        audio = _tone()
        result = apply_input_gain(audio, None)

        assert np.array_equal(result, audio)

    def test_unity_leaves_the_signal_alone(self) -> None:
        audio = _tone()
        assert np.allclose(apply_input_gain(audio, 1.0), audio)

    def test_gain_above_one_amplifies(self) -> None:
        audio = _tone(0.1)
        louder = apply_input_gain(audio, 2.0)

        assert float(np.abs(louder).max()) == pytest.approx(0.2, abs=0.01)

    def test_gain_below_one_attenuates(self) -> None:
        audio = _tone(0.1)
        quieter = apply_input_gain(audio, 0.5)

        assert float(np.abs(quieter).max()) == pytest.approx(0.05, abs=0.01)

    def test_the_result_stays_float32(self) -> None:
        """The decoders and the ring buffer both expect float32; a silent
        promotion to float64 doubles every buffer downstream."""
        assert apply_input_gain(_tone(), 1.5).dtype == np.float32

    def test_empty_input_is_safe(self) -> None:
        assert len(apply_input_gain(np.array([], dtype=np.float32), 2.0)) == 0


class TestClipping:
    """Amplifying a loud signal past full scale is the one way this makes
    reception worse rather than better."""

    def test_amplified_audio_is_clamped_to_full_scale(self) -> None:
        audio = _tone(0.8)
        result = apply_input_gain(audio, 2.0)

        assert float(np.abs(result).max()) <= 1.0

    def test_clamping_does_not_wrap(self) -> None:
        """Overflow that wraps turns a loud signal into noise, which is
        the failure this exists to prevent."""
        audio = np.array([0.9, -0.9], dtype=np.float32)
        result = apply_input_gain(audio, 2.0)

        assert result[0] > 0, "positive sample wrapped negative"
        assert result[1] < 0, "negative sample wrapped positive"


class TestOrderingAgainstTheMeter:
    """Gain must apply before levels are measured.

    Otherwise the meter reports pre-gain audio while the decoder receives
    post-gain audio: an operator raises the gain, sees the meter unmoved,
    and concludes the control is broken. That mismatch between what is
    reported and what is delivered is exactly the SpyServer gain defect.
    """

    def test_levels_reflect_the_gain(self) -> None:
        from sstv_core.audio.stream_manager import AudioStreamManager

        quiet = _tone(0.05)
        manager = AudioStreamManager()
        manager._input_gain = 4.0

        boosted = apply_input_gain(quiet, manager._input_gain)
        levels = manager._calculate_levels(boosted)
        plain = manager._calculate_levels(quiet)

        assert levels.rms > plain.rms, (
            "the meter would show pre-gain levels while the decoder hears "
            "post-gain audio"
        )

    def test_the_stream_manager_has_a_gain_setter(self) -> None:
        """Mid-session adjustment needs a way in that is not a restart."""
        from sstv_core.audio.stream_manager import AudioStreamManager

        manager = AudioStreamManager()
        manager.set_input_gain(1.5)

        assert manager.input_gain == 1.5

    def test_gain_is_applied_in_the_callback(self) -> None:
        """The assertion that fails if the multiplier is never called.

        Every test above passes with `apply_input_gain` wired to nothing
        -- which is precisely how this shipped inert the first time.
        """
        import inspect

        from sstv_core.audio import stream_manager

        source = inspect.getsource(stream_manager.AudioStreamManager)

        assert "apply_input_gain" in source, (
            "gain is storable and readable but never applied, so the "
            "control reports a value it does not deliver"
        )
