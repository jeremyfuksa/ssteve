"""A test tone for proving the audio path (#59).

PRODUCT.md calls audio routing and levels a manufactured difficulty. This
is half of what defuses it: an operator plays a tone and hears whether
sound actually reaches the radio, before putting a signal on the air.
"""

from __future__ import annotations

import numpy as np

#: SSTV centre frequency (ITU). Any tone proves audio flows; this one
#: also lands where the passband should be, so a misrouted or
#: over-filtered path shows up in the same test.
TEST_TONE_HZ = 1900.0

#: A test tone is a check, not a transmission. The radio may be keyed
#: while this plays, so an unbounded duration has real consequences at
#: the far end of the coax.
MIN_DURATION_SEC = 0.1
MAX_DURATION_SEC = 10.0

#: Fade applied to each end. A tone starting at full amplitude clicks,
#: and a click is broadband -- it keys VOX and stresses a PA for no
#: reason.
_FADE_SEC = 0.02

#: Below full scale, because this is played into a transmit chain that
#: may have its own gain ahead of it.
_AMPLITUDE = 0.5


def generate_test_tone(
    duration_sec: float = 1.0,
    sample_rate: int = 48_000,
    frequency_hz: float = TEST_TONE_HZ,
) -> np.ndarray:
    """Build a fading sine at ``frequency_hz``.

    Raises ValueError outside the duration bounds rather than clamping:
    an operator who asked for a minute of carrier has made a mistake
    worth naming, and silently playing one second instead teaches them
    the wrong thing about the control.
    """
    if not MIN_DURATION_SEC <= duration_sec <= MAX_DURATION_SEC:
        raise ValueError(
            f"A test tone runs {MIN_DURATION_SEC}-{MAX_DURATION_SEC} seconds; "
            f"got {duration_sec}."
        )

    count = int(sample_rate * duration_sec)
    times = np.arange(count) / sample_rate
    tone = (_AMPLITUDE * np.sin(2 * np.pi * frequency_hz * times)).astype(np.float32)

    fade = min(int(sample_rate * _FADE_SEC), count // 2)
    if fade > 0:
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        tone[:fade] *= ramp
        tone[-fade:] *= ramp[::-1]
    return tone
