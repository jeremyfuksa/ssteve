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
receiver that does not share our code path. WWV on 2.5/5/10/15 MHz runs
continuously, so it is always a valid target. (20 and 25 MHz read as noise
from Kansas City — 3.8 dB measured — so they prove nothing here.)

Which WWV frequencies survive is itself a propagation measurement: losing 15
MHz while 5 MHz holds is the MUF dropping, not a fault.

If the other receiver hears it and ours does not, **the bug is ours** — stop
looking at the antenna.

### 4. Only now, our own path

```bash
uv run python scripts/calibrate_receiver.py --spyserver <host>:5555
```

About 26 seconds. Sweeps WWV 2.5/5/10/15 MHz on one connection and reports
**carrier SNR** at each, with a verdict. Add `--json cal.json` to keep it.

**Judge on carrier SNR, never on a level.** A level cannot tell a carrier from
noise, because broadband noise raises it exactly like a station does. Measured
2026-08-19: WWV 5 MHz read mean |IQ| 0.01210 and a silent 20m read 0.01036 —
indistinguishable — while carrier SNR was 13.1 dB and 1.3 dB. The recorder's
old `rms < 0.01 = deaf` rule would have called a working receiver deaf that
night. Anything above ~8 dB is a carrier; every real WWV signal measured has
cleared 13 dB and nothing empty has come within 9 dB of it.

Reference, 2026-08-19 21:15 UTC at gain 8, SFI 125 / K 1:

| WWV 2.5 | WWV 5 | WWV 10 | WWV 15 | 20m SSTV |
|---|---|---|---|---|
| 31.6 dB | 23.6 dB | 33.7 dB | 38.3 dB | **1.3 dB** |

That last column is the shape of a healthy receiver on an empty band. Expect
movement with propagation — WWV 5 read 13.1 dB an hour earlier the same
evening.

**Nothing on any frequency** is the one result that implicates the receive
chain, and even then only after steps 1–3 have cleared. The script exits 2 in
that case so a scheduled run can react.

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
