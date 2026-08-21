# Auto-first: what is measured, what is blocked, what is next

SSTeVe's product position is the SSTV application that needs the least manual
work. This file records what that costs in engineering terms: what is already
measured, what cannot be built yet and why, and what the one unbuilt piece
would have to do.

Written 2026-08-20.

## The position, stated precisely

Least manual work means driving the *rate* of human intervention toward zero.
It does not mean removing controls. `CLAUDE.md` requires gain, squelch, and
AFC overrides to stay in the primary interface, and that requirement protects
the position rather than fighting it: automation that misses with no reachable
exit does not read as "90% right", it reads as broken. Overrides are what
make automation safe to trust. Nobody should touch them on a good day.

## Measured today

`tests/decode/regression/test_auto_success.py` runs each off-air fixture the
way an unattended session would -- mode read from the VIS header, decoder
selected from that, nothing supplied by hand -- and scores it against the
accepted render byte for byte.

**14 of 14 as of 2026-08-20.**

That number is an upper bound, not a field rate, for two structural reasons:

1. The corpus holds only modes that already decode (6 Scottie S2, 5 Martin M1,
   3 Martin M2). Robot 72 and PD 120 are common on 14.230 and absent.
2. Recorded WAVs sit at fixed level. Gain is the one setting with no correct
   default, and a file cannot exercise a control loop that responds to level.

Both gaps are addressed below.

## Blocked: Robot 72 and PD decoders

Eight of the eleven VIS-detectable modes have no decoder. Robot 72 and PD 120
are the two that matter, because both are common on the air. Auto-detecting a
mode and then reporting "I cannot decode this" is a failed session from the
operator's chair however clean the message is.

These are not blocked on effort. They are blocked on **verification**.

There is no off-air audio for either mode in this repo, and no encoder for
them either (`tx_manager` maps Scottie S1, Martin M1, and Robot 36 only). So
"write it and roundtrip it" would mean writing the encoder and the decoder
from one reading of the spec and confirming they agree with each other. They
always will, whether or not the reading is right.

This repo has already been bitten by exactly that. The MMSSTV FSKID
specification is **wrong** about bit order -- transmissions are LSB-first on
air -- and no test caught it, because every test encoded with the same wrong
assumption it decoded with. What broke the tie was an independent oracle (the
XOR checksum) plus real off-air audio.

PD is worse placed than FSKID was: it carries no checksum, so there is no
internal consistency check available at all. The only oracle is a real
transmission decoding into a picture that looks right.

Shipping an unverified decoder would also damage the auto-first position
specifically. Current behaviour on an undecodable mode is honest -- the
session stops and names the mode (`rx_manager.py:598-615`). A subtly wrong PD
decoder would instead hand back a garbled picture and call it success, and
`test_auto_success.py` would score it green, because it would be pinned
against its own wrong output.

### Unblocking it: capture first

The tooling already exists and is how the current corpus was built.

```bash
cd sstv_core
uv run python -m sstv_core.cli.main decode \
  --spyserver --band 20m --gain 8 \
  --record ~/captures/20m-$(date +%Y%m%d).wav \
  --timeout 36000 --verbose
```

`--record` switches decoding to continuous and keeps listening until timeout,
so one run both decodes what it can and preserves everything for later.

Undecodable modes are logged by name as they arrive ("Detected SSTVMode.PD_120
but no decoder is available for it"), so **the capture reports its own
usefulness** -- grep the log to see whether the night carried the modes wanted
without re-scanning the audio.

Afterwards, find every transmission in the recording:

```bash
uv run python -m sstv_core.cli.main decode --file ~/captures/20m-YYYYMMDD.wav --scan
```

Notes from previous capture runs, worth not rediscovering:

- Use `--gain 8` on the Airspy HF+, not the auto-derived value.
- SSTV bands are quiet: measured 2.6% duty cycle over 10.5 hours, median 30
  minutes between transmissions. A near-empty capture is normal, not a fault.
- SpyServer is single-client -- stop other listeners first.
- Before concluding the receiver is deaf, follow `sstv-rf-diagnosis`. That
  mistake has been made twice.

Once a Robot 72 or PD transmission is captured, it becomes a fixture the same
way the current 14 did, and the decoder can be written against a real signal.

## Unbuilt: gain automation (AGC)

Gain is the highest-value auto target left and the only one with **no correct
default at all**. `SpyServerSettings.gain` is `None` deliberately: 0 is both a
legal value and a deaf one on an Airspy HF+, and the old default of 0 made a
working receiver look broken (issue #90). The current fallback derives a gain
from the device's own maximum, and bench work found that value wrong in
practice -- `--gain 8` is what actually works.

So the honest description is that SSTeVe does not automate gain today; it
guesses once at startup and never revisits.

### What an AGC would have to do

Not "pick a better default" -- track. Measure input RMS continuously, walk the
gain index when the level leaves a working band, and recover when the signal
fades. The measurement primitives already exist and are already calibrated:

- `DEAF_RMS = 0.0005` and `HEALTHY_RMS = 0.005` in `cli/main.py`, both measured
  against WWV 10 MHz rather than assumed.
- `describe_level()` already classifies a reading as silent / faint / healthy.

Today those only report. An AGC closes the loop on them.

Three properties it must have, each from a documented failure:

1. **Do not hunt during QSB.** Fading is the normal state of an HF signal, not
   an error. A loop that chases every dip will oscillate and wreck decodes
   that would otherwise have survived.
2. **Never move gain mid-transmission.** A gain step part-way through a frame
   changes the black/white mapping and bands the picture. Adjust between
   transmissions.
3. **Say when it hits the stop.** At maximum gain the advice "raise the gain"
   is useless and sends the operator to the wrong subsystem;
   `_deaf_receiver_action()` already handles this for the one-shot case and
   the loop must preserve it.

### Why it is not built here

It cannot be honestly tested yet. The file corpus is fixed-level, so the only
available test is synthetic: programmatically fade the existing fixtures and
assert the loop compensates. That proves the loop responds to an attenuation
curve someone wrote -- not that it survives real QSB, Doppler, or the AGC
interaction of an actual SDR front end.

Given this repo's history -- four defects on the SDR path that only live
hardware revealed -- synthetic-only validation is the weaker half of the job.
The recommended sequence is to build the loop *alongside* live capture work,
so the same overnight runs that collect Robot 72 and PD fixtures also exercise
the gain loop against real fading.

## Sequence

1. **Done.** Auto-success harness (PR #130). Baseline 14/14, with caveats
   attached to the number.
2. **Needs the radio.** Overnight 20m captures until a Robot 72 and a PD 120
   are in hand. Self-reporting via the log line above.
3. **After 2.** Robot 72 decoder, then the PD family, each verified against a
   real transmission and pinned as accepted renders.
4. **Alongside 2.** AGC, built against live captures rather than synthetic
   fades alone.

Steps 2 and 4 depend on hardware time, not engineering time. Step 3 is
straightforward once step 2 lands, and dishonest before it.
