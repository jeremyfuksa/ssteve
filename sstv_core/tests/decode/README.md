# Decode tests

Grouped by what a failure here would tell you, not by module.

## `modes/`

One mode's timing and VIS handling. A failure means that mode specifically is
wrong — check its config constants against the spec table before anything else.

## `regression/`

Behaviours that broke once and must not break again. Each file names the issue
it came from, and several are gates rather than unit tests:

- `test_offair_corpus.py` — twelve real 20m transmissions cut from a 10.5 h
  SpyServer capture. Includes `test_decode_matches_the_accepted_render`, which
  pins each decode to the exact picture in `../../reference/images/offair_decoded/`.
  Statistical floors cannot do this job: uniform noise scores 96% lit, and a 9%
  Martin M1 timing error moved scanline correlation by 0.002 while destroying the
  picture. Refresh renders deliberately with `scripts/refresh_offair_renders.py
  --review`, and look at them before committing.
- `test_roundtrip.py` — encode, decode, compare. The gradient gate is the canary
  for encoder/sync regressions; never skip it.
- `test_decode_wedge.py` (#94), `test_sync_survives_bandpass.py` (#100),
  `test_realtime_starvation.py`, `test_unsupported_mode_degradation.py`.

## `pipeline/`

The plumbing around the decoders — line slicing, image start alignment, sample
rate agreement, level reporting, AFC/squelch, RSV. A failure here usually means
the decoders are fine and something feeding them is not.

## `fskid/`

Callsign ID, unit tests and real off-air MMSSTV transmissions. The off-air file
is the trustworthy oracle: the MMSSTV spec is wrong about bit order (it is
LSB-first on air), so only the XOR checksum proves a decode.

## Fixtures

Audio and images live in `tests/reference/`, addressed as
`Path(__file__).resolve().parents[2] / "reference"`. Moving a test between these
subdirectories keeps that depth; moving one up or down a level breaks it.
