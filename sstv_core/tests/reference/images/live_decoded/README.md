# Live decodes, 2026-08-17

Ten transmissions decoded straight off a live SpyServer stream on 14.230 MHz,
09:19–09:51 local. Filenames carry the time each one started.

These are the cleanest decodes this project has produced: **WA1QZK BOSTON**,
**N3CHX**, and **W9DRK 595** are plainly readable, along with "THANKS FOR QSO
OM / 73 FROM RON BOSTON / YOUR LOGGED ON QRZ". Compare them with
`../offair_decoded/`, cut from a 10.5 h recording on 2026-08-16, to see the
difference between a strong signal and a marginal one.

## What these are not

**There is no test gating them, and there cannot be.** They were decoded from a
live stream that was never recorded, so there is no source audio to re-decode.
The corpus in `../offair_decoded/` is the one with a regression gate
(`tests/decode/regression/test_offair_corpus.py`), because its twelve WAV files
still exist in `../../audio/offair/`.

They are kept as evidence of what a healthy receive chain produces — useful
when a later change makes decodes worse and the question is what "good" looked
like.

## Provenance note

Decoded before the SpyServer digital-gain defect was understood: the client
pinned `IQ_DIGITAL_GAIN` to 0, so `--gain` moved only the analog stage. That
these came out this clean anyway says the band was genuinely strong that
morning.
