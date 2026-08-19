---
name: sstv-rf-diagnosis
description: >
  Use this skill before concluding anything about why a receiver is quiet, in
  the SSTeVe repo or at the bench. Triggers on: "no signal", "nothing
  decoded", "the receiver is deaf", "is the antenna bad", "band sounds dead",
  a capture that produced no images, an overnight run with zero decodes, any
  rms/level reading being interpreted as a hardware verdict, or any sentence
  about to claim the antenna, feedline, or SDR is at fault. Enforces the order
  of evidence: propagation first, a DIFFERENT receiver second, our own path
  last. Load-bearing because a bad antenna was diagnosed twice — 2026-08-14
  and again 2026-08-16 through 08-19 — and both times the control was run
  through the very path that was broken, so it confirmed the fault instead of
  falsifying it.
---

# Diagnosing a quiet SSTV receiver

## The failure this prevents

Twice a quiet receiver has been called a hardware fault when it was not:

- **2026-08-14** — "the receiver is deaf." WWV proved it fine; 20m had simply
  closed after dark.
- **2026-08-16 → 08-19** — three consecutive overnight captures read as noise.
  Reported as "broadband attenuation, antenna degraded, check the feedline,"
  with a table of measurements. The real cause was our own SpyServer client
  pinning `IQ_DIGITAL_GAIN` to 0, so `--gain` moved only the analog stage.
  Checking WWV in SDR++ broke it open in one message.

Both times a WWV control *was* run. Both times it went through the same
suspect path, so it agreed with the wrong theory. **A control that shares the
failure mode is not a control.**

## Order of evidence

Work outward from the ionosphere to the equipment. Do not skip a step because
the next one looks obvious.

### 1. Is the band even open?

```bash
cd sstv_core
uv run python scripts/check_propagation.py --band 20m
```

Reports OPEN / CLOSED / STORM from N0NBH's solar feed with NOAA SWPC as
fallback, and picks day or night conditions for the band. If it says CLOSED or
STORM, silence is the correct answer and there is nothing to diagnose. K ≥ 5
is a geomagnetic storm — HF will be degraded regardless of your equipment.

### 2. Is the band merely quiet?

SSTV bands are **97.4% silent** — measured over a 10.5 h capture, 2.6% duty
cycle, median ~30 minutes between transmissions. A probe that hears nothing
for ten minutes has measured nothing at all. Do not treat a short quiet
window as evidence of anything.

### 3. Does a different receiver hear it?

**This is the step that was skipped both times.** Use SDR++, a web SDR, or any
receiver that does not share our code path. WWV on 5/10/15/20 MHz runs
continuously, so it is always a valid target.

Which WWV frequencies survive is itself a propagation measurement: losing 15
MHz while 5 MHz holds is the MUF dropping, not a fault.

If the other receiver hears it and ours does not, **the bug is ours** — stop
looking at the antenna.

### 4. Only now, our own path

```bash
uv run python -m sstv_core.cli.main decode --spyserver <host> \
  --frequency 10000000 --gain 8 --timeout 15 --record /tmp/wwv.wav --output /tmp/wwv.png
```

Compare against a known-good reading rather than an absolute. A live 20m band
measured **0.407 rms**; the same chain with the digital-gain bug read
**0.0004**. Three orders of magnitude, and every frequency equally down — which
looked exactly like a dead antenna and was not.

## Stating the conclusion

Say which step produced it, and how confident you are:

- "Propagation says the band is closed" — settled, no further action.
- "A second receiver hears WWV clearly and ours does not" — our bug, and the
  next step is code, not the bench.
- "A second receiver hears nothing either, propagation says open" — now an
  equipment hypothesis is reasonable. Say it is a hypothesis.

Never present a measurement table as a diagnosis. "Broadband attenuation
consistent with an antenna problem" read as a finding when it was a guess.

## Bench facts worth having

- SpyServer at `airspy.local` / `192.168.1.30:5555`. Under launchd, mDNS
  resolution fails inside Python even when `nc` succeeds — resolve to an IP
  first.
- Gain range on this Airspy HF+ is **0–8**; higher values are refused with the
  range in the error.
- `DEAF_RMS = 0.0005` in `cli/main.py` was calibrated against the broken gain
  path (#90). Treat "silent" and "faint" labels as suspect until recalibrated.
