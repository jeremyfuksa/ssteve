"""Operator input gain, applied to the signal (#56).

`input_gain_override` was storable and readable from PR #84 onward and
reached nothing: an operator set it, the UI showed it set, and the
decoder heard the same audio as before. A control that reports a value it
does not apply is worse than a missing one -- the missing one is honest,
and this one silently absorbed the fix an operator was trying to make.

PRODUCT.md #3 keeps gain, squelch and AFC in the primary interface for
operational reasons: auto-detection fails on QSB, on satellite Doppler,
and in contest QRM. This is the gain half of that.
"""

from __future__ import annotations

import numpy as np

#: Bounds enforced at the config layer (`input_gain_override`, 0.0-2.0).
#: Repeated here because this function is also called with values from
#: a live PATCH, which has its own validation but should not be the only
#: thing standing between a typo and a blown-out buffer.
MIN_GAIN = 0.0
MAX_GAIN = 2.0


def apply_input_gain(samples: np.ndarray, gain: float | None) -> np.ndarray:
    """Scale ``samples`` by ``gain``, clamped to full scale.

    ``None`` returns the input untouched -- not multiplied by 1.0 --
    because the common case is no override at all and an operator who has
    set nothing should get bit-identical audio.

    Clamped rather than allowed to overflow: amplifying an already-loud
    signal past full scale is the one way this control makes reception
    worse, and a wrap turns a strong signal into noise.
    """
    if gain is None or not len(samples):
        return samples
    bounded = float(np.clip(gain, MIN_GAIN, MAX_GAIN))
    if bounded == 1.0:
        return samples
    # float32 throughout: the ring buffer and every decoder expect it, and
    # a silent promotion to float64 doubles every buffer downstream.
    scaled = np.asarray(samples, dtype=np.float32) * np.float32(bounded)
    clamped: np.ndarray = np.clip(scaled, -1.0, 1.0, dtype=np.float32)
    return clamped
