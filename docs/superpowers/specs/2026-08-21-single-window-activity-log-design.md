---
title: Single-window shell — activity instrument plus elastic log
created: 2026-08-21
status: Design approved; unimplemented. `sstv_desktop/` is still empty.
supersedes: frontend-spec.md §19.1 (four peer routes), §20.11 Auto/Manual layout budgets
---

# Single-window shell: activity instrument plus elastic log

## Why this exists

MMSSTV splits its interface into several small windows. The observation that
prompted this design: send and receive need few controls and little space,
while the log/gallery needs a full window for an image grid — so the activity
windows end up mostly empty.

The conclusion MMSSTV drew from that (separate windows) was an artifact of
2003 Win32 MDI convention, not a consequence of the problem. This document
records a different answer: **one window, where the small thing is fixed and
the big thing is elastic.** The activity instrument's apparent "wasted space"
was never its space — it belongs to the log.

## 0. The governing frame: it is fishing

SSTV is the radio equivalent of fishing. You can sit all day and not get a
bite. Measured over a 10.5-hour capture, the band was **97.4% silent** — a
2.6% duty cycle, median ~30 minutes between transmissions.

Two consequences, and they pull in opposite directions. Holding both is the
design problem:

1. **For the 97.4%, the experience should be as simple as possible.** The
   interface should ask nothing of an operator who is waiting. This is why
   auto-first is the default posture rather than a convenience feature, and
   why the log — not the instrument — gets the elastic space. The log is what
   you look at while nothing is biting; it is what makes an eight-hour session
   tolerable.

2. **For the 2.6%, you must reach the tackle box at a moment's notice.** When
   a signal appears you have 36–114 seconds and no second chance — miss it and
   the band goes quiet for another half hour. Every control that can rescue a
   decode in progress must be reachable *now*, without hunting.

Nearly every decision in this document falls out of that tension:

| Decision | Which side it serves |
|---|---|
| Receive is the default posture | The 97.4% — the common state needs no action |
| Log takes the elastic space | The 97.4% — the waiting should be worth looking at |
| Canvas never blank while listening | The 97.4% — silence must still read as *working* |
| Gain + squelch on a thin strip | The 2.6% — these fail mid-decode, so they cannot be behind a gesture |
| Everything else in a drawer | Both — closed while fishing, one gesture when it bites |
| Theme and input in settings | The 97.4% — no failure rate, no decode-length window |

**A tackle box is closed while you fish.** A permanent 15-control rail is
fishing with the box upended on the deck: everything visible, nothing to hand.
The drawer is the box — shut during the wait, open in one motion when it
matters.

## 1. Window model

One window containing two zones with different economics:

- **Activity instrument** — fixed cost. Holds its size and arrangement at
  every viewport.
- **Log region** — variable cost. Takes the remainder.

Growing the window grows the log and nothing else.

| Window size | Log region | What gives |
|---|---|---|
| ~1920×1080 | Full grid, several rows | Nothing; the comfortable case |
| ~1366×768 | Grid, 1–2 rows | Log rows, gradually |
| 1280×720 (floor) | Single filmstrip row | Waterfall drops 200px → 80px minimum |

Nothing reflows, nothing relocates, no region appears or disappears. One
region gets a different amount of room. This satisfies PRODUCT.md interaction
requirement 10 ("larger viewports gain breathing room, not a different
layout") on its actual terms.

**Why the log is the elastic one.** It is the only region without a hard
functional minimum. The canvas has a legibility floor, the waterfall has an
FFT-resolution floor (80px = 10 seconds of history, per §20.4 in
`frontend-contract.md`), and controls have a touch-target floor. A log grid
degrades from many rows to one because each row is independently meaningful.

**What the log earns by being on the operating surface:**

1. **It fills the silence.** The band is quiet 97.4% of the time (median ~30
   minutes between transmissions). That dead time shows the operator's library
   instead of a placeholder.
2. **It is the transmit picker.** Staging an image never requires leaving the
   operating surface.
3. **It puts provenance next to live decode.** Requirement 12 needs QSO /
   reception report / remote reception distinguishable on the row; adjacency
   to the live canvas is where that distinction is most load-bearing.

## 2. Activity instrument

Receive is the default posture. Transmit has a permanent but subordinate home
inside the receive instrument.

**Canvas** — the page's one big instrument. Shows *the picture currently on
the air*, incoming or outgoing. Never blank (requirement 1): idle shows the
last decode; listening shows it receded so it cannot be mistaken for live
signal; decoding shows scanlines arriving; transmit shows the outgoing image
with the callsign overlay burned in.

The canvas changing character **is** the transmit confirmation (requirement
7). The operator's whole view of the world visibly switches from receiving to
sending — louder than a modal, and harder to click through by reflex.

**Waterfall** — directly under the canvas, always visible, 300–3000 Hz
(requirement 2). Its 200px → 80px compression is the shock absorber that lets
the filmstrip survive at the floor.

**Thin control strip** — gain and squelch only, always visible, ~48px.

**Manual controls drawer** — AFC range with detected sync frequency displayed
(requirement 5), frequency offset, slant, FSKID. One gesture from the operating
surface; the canvas and waterfall stay visible behind it.

### Where a control lives

The split above is derived from failure rates, not from vocabulary:

| Placement | Test | Controls |
|---|---|---|
| **Thin strip** | Fails *during* a 36–114s decode; adjusted while watching the picture | Gain (30–40% on fading signals), squelch (~20% in contest QRM) |
| **Drawer** | Fixes a signal problem, but set-and-leave within a session | AFC range, frequency offset, slant, FSKID |
| **Settings** | Does not change in response to the signal | Input source, Operating Conditions theme, station details, paths |

Requirement 3 calls burying gain/squelch/AFC a correctness failure rather than
a taste choice. The drawer satisfies it on two conditions, both load-bearing:

1. **It opens in one gesture from the operating surface** — the requirement's
   real test is "reachable in under two seconds," not "permanently visible."
2. **Failures surface themselves.** When auto-detection fails, the relevant
   control comes forward unasked — the thin strip shows the failure, the drawer
   holds the fix. Requirement 4 already demands failures point at the control
   that fixes them. A drawer the operator must *remember to check* is settings
   with an animation.

A permanent 15-control rail shows every control whether or not any of them
matter right now. The drawer shows what this moment needs — and, unlike the
rail, it cannot be missed on failure.

**Operating Conditions theme is settings, not drawer.** Requirement 8 explains
why the feature exists (dark adaptation and sunlight legibility are
physiological, not taste); it does not follow that the control needs primary
placement. Theme has no failure rate and no decode-length window, and with a
median ~30 minutes between transmissions, the switch is overwhelmingly made
during silence. Putting it in the drawer would also dilute what the drawer is
for — it stays useful only while everything in it is there for the same reason.

**Transmit home** — compact and permanent: staged image thumbnail,
callsign-overlay indicator, mode, Send. Small because picking happens in the
adjacent log region, with a file-picker escape hatch for images not in the
library. Present and quiet when idle, never hidden.

### Two properties this arrangement gets for free

**Receive-only amputates cleanly.** PRODUCT.md requires that for SDR/SpyServer
listeners, transmit and PTT configuration be *absent*, not merely disabled.
Removing one subordinate region leaves a complete, intentional receive
instrument with a log — not a layout with a hole in it.

**Half-duplex needs no arbitration UI.** `SessionManager` returns HTTP 409 if
a transmit starts during a decode. With one canvas and one instrument, the
operator cannot construct the illegal state; there is no second surface to
start a conflicting operation from. The constraint is expressed by the layout
instead of explained by an error.

## 3. Log region

**One component at three densities.** Grid, a row or two, or a single
filmstrip row. Same component, same rows, same information per row — fewer of
them as the window shrinks. It never becomes a different thing.

**What a row carries.** Thumbnail, callsign, mode, time, and — non-negotiably
— **source** (requirement 12). Provenance lives on the row, not behind a
click: an operator switches sources mid-session, and the log must stay
readable a week later without recalling which decode came from where.

**Transmit staging is a two-surface gesture in one window.** Select in the log
→ the image appears in the transmit home's staged slot → confirm → canvas
takes over. Both surfaces stay visible throughout, so the operator watches the
picture travel from library to staged to on-air without a navigation step. In
a two-window model this gesture crosses a window boundary and the operator
loses sight of one end of it.

**Deep browsing is a different task.** Scrolling years of decodes, bulk
operations, and MMSSTV import review are browsing, not operating. Those belong
in a modal or expanded state that may scroll (requirement 10 permits scrolling
for progressive disclosure) — not in a second window competing with the
instrument.

## Control density — reframed, not settled

PRODUCT.md marks the Auto (8 controls) vs Manual (12–15) split explicitly
unresolved: no evidence either way, and the 20-participant user test was never
run. `frontend-contract.md` records §20.6's own "both fail" branch pointing at
progressive disclosure within a single interface as the fallback.

**The drawer takes that fallback.** It dissolves the question as posed —
"8 or 15?" assumes controls compete for permanent space. With a thin strip plus
a drawer, the count visible at rest is small and the count *available* is
complete, and no mode switch is needed to move between them.

What remains genuinely open is narrower and more answerable:

- Does the drawer's disclosure logic show the right controls for a given
  situation, or does the operator end up hunting?
- Does a failure reliably pull its own control forward, or do operators still
  miss clipping?

Both are testable with a working prototype. Neither needs a 20-participant
study to move forward.

## The floor case: measured, not assumed

Wireframed 2026-08-21. Two windows measured.

**At ~1020×880 — what the UI actually wants:**

| Region | Height |
|---|---|
| Top strip | 32 |
| Canvas at 2× (640×512) + status gutter | 536 |
| Signal-presence strip | 64 |
| Control strip — gain + squelch | 44 |
| Log — 4 rows | 152 |
| **Total** | **828** in an 880px window |

**At the 1280×720 field floor,** the same layout with the canvas at 1.5×
(480×384) and the log at 1–2 rows fits in ~680px of workspace with room to
spare. Nothing moves; the picture is smaller and there are fewer log rows.

**Two things make it fit**, and neither is layout cleverness:

1. **The drawer.** Returning AFC, offset, slant and FSKID to a permanent rail
   costs ~180px this budget does not have.
2. **Sizing the canvas to the picture.** The earlier draft gave the canvas the
   largest region and then under-filled it — 880×340 labelled "2×" for a frame
   that needs 640×512. Sizing honestly returned enough room for a signal panel
   and three more log rows.

Still unverified: legibility and touch-target sizes with gloves and in direct
sun. The pixels fit; whether they can be *operated* in field conditions is a
different claim and has not been tested.

## Provenance

Settled in conversation on 2026-08-21:

- Default posture is receiving.
- Transmit borrows the canvas rather than getting its own preview.
- Transmit images come from the log, plus a file-picker escape hatch.
- Window size is flexible; 1280×720 is the shrink floor, not the design target.
- At the floor the log persists as a filmstrip rather than vanishing.
- Manual controls live in a drawer; gain and squelch stay on a thin strip.
- Input source and Operating Conditions theme both live in app settings.
- The window is whatever shape serves the UI; 1280×720 is a fit constraint, not
  an aspect ratio.
- Canvas scale is what degrades on a small window — not the presence strip, not
  the log.
- The waterfall is a presence display, not a tuning instrument: everything is
  automatic, so its job is visual proof that reception is happening.

`DESIGN.md` and `prototype/` were deleted in commit 062b3ba. That was
deliberate — the visual path they represented is abandoned and should not be
recovered from git history. This design is written against PRODUCT.md's
behavioral requirements only.
