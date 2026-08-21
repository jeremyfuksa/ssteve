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

**Control rail** — gain, squelch, AFC with detected sync frequency displayed
(requirement 5), mode. These stay in the primary interface. Requirement 3
calls burying them a correctness failure rather than a taste choice, because
auto-detect fails at documented rates (30–40% on fading signals for gain, ~20%
in contest QRM for squelch, 100% for satellite work with wrong AFC range —
see `frontend-contract.md` §20.3).

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

## Deliberately open

**Control density.** PRODUCT.md marks the Auto (8 controls) vs Manual (12–15)
split explicitly unresolved: no evidence either way, and the 20-participant
user test was never run. This design is compatible with both — the control
rail holds either count — and the fallback of progressive disclosure within a
single interface fits the single-window model naturally. Not settled here.

## Unproven

**The floor case fits.** At 1280×720 the filmstrip is one row and the
waterfall is at its 80px minimum simultaneously. This is the tightest the
design ever gets, and it is the field-ops case: sun, gloves, battery. The
claim that it fits is a belief, not a measurement. **Test it in a wireframe
before building it.**

This repo's history is a catalogue of confident unmeasured claims. This one is
labeled rather than asserted.

## Provenance

Settled in conversation on 2026-08-21:

- Default posture is receiving.
- Transmit borrows the canvas rather than getting its own preview.
- Transmit images come from the log, plus a file-picker escape hatch.
- Window size is flexible; 1280×720 is the shrink floor, not the design target.
- At the floor the log persists as a filmstrip rather than vanishing.

`DESIGN.md` and `prototype/` were deleted in commit 062b3ba. That was
deliberate — the visual path they represented is abandoned and should not be
recovered from git history. This design is written against PRODUCT.md's
behavioral requirements only.
