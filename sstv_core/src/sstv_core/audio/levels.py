"""What an input level means, in words.

A bare RMS figure tells an operator nothing: is 0.0002 fine? These
thresholds are the difference between "the band is quiet" and "this
receiver is deaf" — two situations that produce identical output (no
picture) and call for opposite responses. Getting them confused cost the
first live session its first decode (issue #90), and diagnosing the antenna
twice when the receiver was fine (2026-08-14, 2026-08-16).

Measured on an Airspy HF+ against WWV 10 MHz:

    gain 0   rms 0.000231   peak/mean   4.5   noise, no carrier in it
    gain 6   rms 0.004929   peak/mean 154.6   a clean carrier
    gain 8   rms 0.006439   peak/mean 118.9   front end starting to compress

Lived in `cli/main.py` until the API needed the same judgement: a decode
that times out over the API has exactly the same two explanations, and the
desktop shell was being told neither.
"""

from __future__ import annotations

#: RMS below which the receiver is effectively deaf rather than merely on a
#: quiet band. An order of magnitude above the measured deaf reading and an
#: order below the working noise floor, so neither measurement lands near
#: the boundary.
DEAF_RMS = 0.0005

#: RMS at or above which the input level is not the problem. The working
#: noise floor at a usable gain measured ~0.005; at or above that, "raise
#: the gain" would be bad advice.
HEALTHY_RMS = 0.005


def describe_level(rms: float) -> str:
    """Describe an RMS figure in one word: silent, faint, or healthy."""
    if rms < DEAF_RMS:
        return "silent"
    if rms < HEALTHY_RMS:
        return "faint"
    return "healthy"


def nothing_heard(loudest_rms: float) -> tuple[str, str, str]:
    """Explain a listen that produced no picture.

    Returns (message, detail, suggested_action). The measurement is what
    separates the two cases, so it is quoted rather than summarised: an
    operator who can see 0.000231 can tell the next person.
    """
    if loudest_rms < DEAF_RMS:
        return (
            "I didn't hear an SSTV transmission -- and I barely heard anything at all.",
            f"Input stayed at {loudest_rms:.6f} RMS, which reads as a deaf "
            "receiver rather than a quiet band.",
            "Raise the receiver gain and try again. If it is already at maximum, "
            "check the antenna and that the band is open.",
        )
    return (
        "I didn't hear an SSTV transmission before the timeout.",
        f"The input level was fine -- {loudest_rms:.6f} RMS at its loudest -- "
        "so I was hearing the band, just no SSTV on it.",
        "Check the frequency and the band, or listen for longer.",
    )
