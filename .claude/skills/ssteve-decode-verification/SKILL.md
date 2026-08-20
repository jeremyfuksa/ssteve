---
name: ssteve-decode-verification
description: >
  Use this skill when changing anything in the SSTeVe decode path, or when
  writing or judging a test that claims to protect decode quality. Triggers
  on: edits under `sstv_core/src/sstv_core/decode/`, changes to mode timing
  constants, VIS detection, sync detection, the bandpass, or the demodulator;
  and on "did this break decoding", "regression test for the decoder", "check
  the images still decode", or adding an assertion about a decoded image.
  Encodes how to verify a decode change actually works, and why statistical
  image metrics cannot do that job — on 2026-08-18 a gate that would have
  passed uniform random noise was nearly shipped as decode-quality protection.
---

# Verifying a decode change

## Statistical image metrics do not work here

The corpus gate was `lit > 0.40` — the fraction of non-black pixels. **Uniform
random noise scores 96% lit.** A real decode with every scanline shuffled
scores 65%. Both passed.

Three replacements were tried against a decoder with a 9% Martin M1 timing
error — one that visibly destroys the picture, smearing the subject away and
banding the right edge magenta:

| metric | baseline | broken decoder |
|---|---|---|
| adjacent-scanline correlation | 0.7638 | 0.7614 |
| horizontal neighbour correlation | 0.8110 | 0.8098 |
| lit fraction | 65.0% | 65.1% |
| channel (R/G/B) correlation | — | **rose** on 3 of 6 files |

None of them saw it. Texture statistics cannot: the noise texture is
unchanged, the timing shift just resamples the same noise at wrong offsets.

**Do not add a statistical floor and call decode quality protected.**

## What works: pin the render

Decoding a fixed file is deterministic — same audio in, same pixels out. So
the gate is the picture itself.

`tests/decode/regression/test_offair_corpus.py::test_decode_matches_the_accepted_render`
compares each decode against `tests/reference/images/offair_decoded/`. Against
that same broken decoder it failed 4 of 12, naming exactly the four Martin M1
files, and correctly passed the two M2 and six Scottie files the injected bug
never touched. That precision is the proof it measures the real thing.

To regenerate after a genuine improvement:

```bash
cd sstv_core
uv run python scripts/refresh_offair_renders.py --review   # writes candidates alongside
uv run python scripts/refresh_offair_renders.py            # overwrites
```

**Look at the new pictures before committing them.** Refreshing carelessly
destroys the gate. Never refresh to make a red suite go green.

## Always verify a new gate by breaking the decoder

A test that passes on first write has proven nothing. Inject a real regression
and watch it fail:

```bash
# 9% Martin M1 scan-timing error — visibly destroys the picture
sed -i '' 's/color_scan_duration_ms: float = 146.43/color_scan_duration_ms: float = 160.0/' \
  src/sstv_core/decode/martin_decoder.py
uv run pytest tests/decode/regression/test_offair_corpus.py -q
git checkout src/sstv_core/decode/martin_decoder.py    # always restore
```

If the gate stays green, the gate is theater. Rewrite it.

## Run the whole suite, and look at a picture

Decode tests alone are not sufficient. On 2026-08-18 a decode change passed
every decode test while breaking `test_sdr_roundtrip` and a CLI roundtrip —
the splitter emitted a final slice shorter than `filtfilt`'s padlen.

End-to-end check on real audio:

```bash
uv run python -m sstv_core.cli.main decode \
  --file tests/reference/audio/offair/cap1_014839s_martin_m2.wav --output /tmp/d.png
```

Then actually open the image. `cap1_014839s` (KG5JJ / VA2PGB) and
`cap1_024123s` (KG5JJ DE VA2PGB) have the most legible callsign text, so they
are the fastest visual confirmation that a decode is still real.

## The corpora, and what each can gate

- `tests/reference/audio/offair/` — real 20m transmissions with their source
  WAVs. **This is the one with a regression gate**, because the audio still
  exists to re-decode. Two of them (`cap2_*`, added 2026-08-20) carry a
  verified FSKID callsign — the only off-air IDs in the repo, and what stops
  the `--scan` filename naming from silently breaking on real fading audio.

### Adding a fixture is a two-file change

Writing the WAV and appending to `manifest.json` is only half of it. The
manifest is what enrolls a fixture in `test_decode_matches_the_accepted
_render`, so a manifest entry with no matching PNG in
`tests/reference/images/offair_decoded/` fails the fast job immediately:

    AssertionError: no accepted render for cap2_010885s_martin_m2_kd2tt.wav

Generate the render with `uv run python scripts/refresh_offair_renders.py`
and **look at each new picture before committing it** — an uninspected render
is not an accepted render, it is just today's output promoted to a standard.
Check geometry first (slant, smearing, subject centred); noise is the air and
is fine to pin.

Then re-run the whole fast job, not just the file you were working in. On
2026-08-20 the manifest was edited *after* a green `-m "not slow"` run, and
the stale result was reported as passing until CI said otherwise.
- `tests/reference/images/live_decoded/` — ten cleaner decodes from a live
  stream on 2026-08-17. No source audio was ever recorded, so **no test can
  gate them**. They are evidence of what good looks like, nothing more.

## When a detector "sometimes works"

Suspect the caller's buffering before the DSP. `CorrelationVISDetector` was
chunk-size dependent: at 11025 Hz, chunk 9600 and 24000 missed all twelve
off-air transmissions while 4096 got all twelve, because `process_samples`
only evaluated on chunk boundaries and a large chunk stepped past the window
where the header was still in the rolling buffer.

The suite hid it by hardcoding `chunk = 4096` — the one lucky value. Any test
of a streaming detector should sweep chunk sizes, not pin one.
