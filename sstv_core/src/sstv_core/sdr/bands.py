"""SSTV calling frequencies, shared by the CLI and the API.

One table, because two would drift: an operator who presses "20m" in the
app and types `--band 20m` at the terminal must land on the same frequency.
"""

# SSTV calling frequencies per band (PRODUCT.md "Push-button band access").
# HF only: FM demodulation is out of scope, so the 2m entries -- 145.500
# simplex and the 145.800 ARISS downlink -- are deliberately absent rather
# than tuned and mis-demodulated as SSB. 20m resolves to 14.230; the other
# common 20m frequency, 14.233, is reachable by giving the frequency in Hz.
BAND_PRESETS: dict[str, int] = {
    "80m": 3_845_000,
    "40m": 7_171_000,
    "20m": 14_230_000,
    "15m": 21_340_000,
    "10m": 28_680_000,
}

#: Bands we can name but not demodulate. Called out by name so the error
#: says why, instead of "unknown band" for a frequency an operator can
#: plainly see is a real SSTV calling frequency.
FM_BANDS: frozenset[str] = frozenset({"2m"})
