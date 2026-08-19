"""Carrier measurement for the recording calibration ladder.

A recording that starts with WWV is the RF equivalent of colour bars: a
signal of known origin, captured through the same antenna, feedline, SDR
and gain as the band that follows. Months later it still answers the
question a silent capture always raises -- was the receiver working?

Why carrier SNR rather than a level. Measured against the live Airspy HF+
on 2026-08-19 at gain 8, WWV 5 MHz read mean|IQ| 0.01210 and a silent 20m
read 0.01036. Indistinguishable. Their carrier SNR was 13.1 dB and 1.3 dB.
Any threshold on amplitude decides these two the same way, and broadband
noise raises a level exactly like a station does. WWV transmits a steady
carrier at the tuned centre, so the peak-over-floor ratio there is the
honest presence test -- and it is what tells a dead antenna from a quiet
band.
"""

from __future__ import annotations

import numpy as np

#: Peak-to-floor ratio at which we will say a carrier is present. Measured
#: on live WWV: 48.6 dB at 10 MHz, 40.9 at 15, 30.9 at 2.5, 13.1 at a weak
#: 5 MHz, against 3.8 dB at 20 MHz and 1.3 dB on a silent 20m. Every real
#: carrier cleared 13 dB and nothing empty came within 9 dB of it.
CARRIER_SNR_DB = 8.0

#: Half-width of the window counted as "our carrier", in Hz. Wide enough
#: for SpyServer's own centring offset and a little AFC drift, narrow
#: enough that a neighbouring station is not mistaken for WWV.
CARRIER_HALFWIDTH_HZ = 100.0

#: How far either side of the carrier is excluded from the noise floor, as
#: a multiple of the half-width. The carrier's own spectral leakage would
#: otherwise inflate the floor and hide the very peak being measured.
_FLOOR_EXCLUSION = 6

#: FFT length. At 48 kHz this is a 5.9 Hz bin -- fine enough to resolve a
#: carrier, short enough that a one-second capture still averages several.
_FFT_SIZE = 8192


def carrier_snr_db(iq: np.ndarray, sample_rate: int) -> float:
    """Peak-to-noise-floor ratio, in dB, at the centre of ``iq``.

    Returns NaN when the capture is too short to average even one FFT
    block. That is a real answer -- "I could not measure this" -- and the
    caller must not read it as absence.
    """
    blocks = len(iq) // _FFT_SIZE
    if blocks < 1:
        return float("nan")

    window = np.hanning(_FFT_SIZE)
    spectrum = np.zeros(_FFT_SIZE)
    for i in range(blocks):
        segment = iq[i * _FFT_SIZE : (i + 1) * _FFT_SIZE] * window
        spectrum += np.abs(np.fft.fftshift(np.fft.fft(segment))) ** 2
    spectrum /= blocks

    centre = _FFT_SIZE // 2
    bin_hz = sample_rate / _FFT_SIZE
    half = max(1, int(CARRIER_HALFWIDTH_HZ / bin_hz))

    peak = spectrum[centre - half : centre + half + 1].max()

    floor_mask = np.ones(_FFT_SIZE, dtype=bool)
    guard = half * _FLOOR_EXCLUSION
    floor_mask[max(0, centre - guard) : centre + guard + 1] = False
    floor = float(np.median(spectrum[floor_mask]))

    if floor <= 0.0 or peak <= 0.0:
        return float("nan")
    return float(10.0 * np.log10(peak / floor))


def has_carrier(snr_db: float) -> bool:
    """Whether ``snr_db`` clears the threshold. NaN is not a carrier."""
    return bool(snr_db > CARRIER_SNR_DB)
