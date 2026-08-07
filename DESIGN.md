# DESIGN.md — SSTeVe visual system

## 1. Status

**Date:** 2026-08-05.

**What this is:** a visual world proven in a working prototype at `prototype/`
(`index.html`, `style.css`, `app.js`, screenshots in `prototype/shots/`). Every token,
class, and measurement in this document is read out of those three files. It is the
first committed visual proposal for SSTeVe after the two contradictory palette specs
were deleted on 2026-08-05 (`CLAUDE.md`, `PRODUCT.md` "Brand Commitments").

**What this is not:**

- Not implemented in the shipping app. `sstv_desktop/` is still a README and nothing
  else — no `.tsx`, no `package.json`, no component code.
- Not wired to the backend. `prototype/app.js:1-9` states it plainly: all data is
  synthetic except the decoded images, which are real reference captures from
  `sstv_core/tests/reference/images/`. Callsigns, SNR figures, RMS levels, and device
  names are authored demonstration data.
- Not user-tested. No round of testing has been run against this or anything else
  (`PRODUCT.md`, "Absent — must not be fabricated").

Treat this as a reference for what the prototype does, and as a proposal for the real
UI — not as a record of shipped work.

> **Staleness note (2026-08-07).** This document describes the prototype as of roughly
> v5. The prototype has since moved to v10 and one structural change is not reflected
> below: **`.ctable`, the four-column control table documented in §6, no longer exists
> in `prototype/index.html`.** Controls now live in a right-hand rail (gain, squelch,
> AFC, and the primary actions), and the fields column gained a `.session` cell listing
> the captures accumulating this session. See `prototype/shots/v8-restructured.png`
> through `v10-session.png`.
>
> The rest of the document — tokens, type, the confidence grammar, signal rendering,
> canvas sizing, motion, accessibility, and §10 — was verified against the current
> files and still holds. §6's `.arrival`, `.board`, `.fall`, `.btn`, `.segset`,
> `.pass`, and `.toast` entries remain accurate; only `.ctable` is gone.
>
> The AUTO/SET column contract that `.ctable` carried was the clearest expression of
> `PRODUCT.md` interaction requirement 3 (auto-detection sets defaults, it does not
> replace control). Whatever replaces it must still show what the machine derived and
> what the operator overrode, both at once. Do not treat the right rail as a decision
> on control density — `PRODUCT.md` still records that as explicitly undecided.

## 2. The world

A decode is a table row being typeset in real time, not a progress bar filling. The
image is not a stage with a caption bar underneath it; it is the largest cell of one
record, and the record's other cells — time, mode, callsign, SNR, slant, lines — set
themselves into their columns as the machine works them out.

This refuses the dark-glass instrument panel that every SSTV application ships: near-
black chrome, cyan waterfall, glowing bezels. Instead: departure board meets segmented
travel document. Pale card stock, near-black ink, one saturated yellow reserved for
change and the primary action, dashed perforation rules dividing fields, tabular
figures on a strict column grid, dark board panels for live listings. No cards, no
rounded corners anywhere, no glow, no shadow except the focus halo.

The argument is that an SSTV operator is reading a record, not monitoring a machine.
The medium is slow — 36 to 114 seconds per image — and the interface should behave like
something being printed rather than something being streamed.

Form: "Boarding pass & gate board", user-selected over the roll's assigned alternative.
Seed key 6063ab5b (`prototype/index.html:37-38`).

## 3. Tokens

All tokens are custom properties declared in `:root` (`prototype/style.css:8-59`).
Every colour is a variable because all three Operating Conditions modes reskin the
entire interface by overriding the same names.

### Type

| Token | Value | Role |
|---|---|---|
| `--sans` | `ui-sans-serif, system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif` | Labels, buttons, table headers, nav |
| `--mono` | `ui-monospace, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace` | Every data value, every table cell, every input |

### Size scale

| Token | Value | Used for |
|---|---|---|
| `--fs-micro` | `clamp(0.55rem, 0.62vw, 0.7rem)` | Nav rail labels, table `thead`, `kbd`, waterfall scale, unseen badge |
| `--fs-label` | `clamp(0.62rem, 0.7vw, 0.78rem)` | `.lbl` field captions, `.btn`, `.segset`, `.pct`, `.range` |
| `--fs-body` | `clamp(0.75rem, 0.85vw, 0.92rem)` | Body default, `.ctable` cells, board rows |
| `--fs-data` | `clamp(0.85rem, 1.05vw, 1.15rem)` | `.arrival .val`, `.telem .val`, station callsign, pass stub values |
| `--fs-lead` | `clamp(1.1rem, 1.6vw, 1.6rem)` | `.pass h2` (first-run heading) — the only display size in use |

### Tracking

| Token | Value | Role |
|---|---|---|
| `--track-label` | `0.14em` | All uppercase label voice |
| `--track-tight` | `-0.01em` | `.arrival .val`, `.pass h2` — large text pulled in |

### Palette — Standard

| Token | Value | Role |
|---|---|---|
| `--stock` | `#F4F1EA` | Card stock ground |
| `--stock-2` | `#EAE6DC` | Recessed field (arrival row, table head, hover) |
| `--stock-3` | `#DEDACE` | Rule / perforation colour |
| `--ink` | `#16181C` | Primary ink; also heavy borders |
| `--ink-2` | `#4A4F58` | Secondary ink (body copy, control names) |
| `--ink-3` | `#61666F` | Tertiary: labels, ranges, auto column |
| `--board` | `#16181C` | Dark board panel ground |
| `--board-2` | `#23262C` | Board row stripe |
| `--board-ink` | `#E8E5DD` | Ink on board |
| `--board-ink-2` | `#9AA0A8` | Secondary ink on board |
| `--alert` | `#F5C518` | The one saturated colour: change + primary action |
| `--alert-ink` | `#16181C` | Ink on alert |
| `--live` | `#2E7D5B` | Confirmed / locked (lamp fill only) |
| `--warn` | `#C4562E` | Fault (TX lamp fill, danger button ground) |

### Signal ramp

Five steps, luminance-ordered, never hue-ordered (§7 below).

| Token | Standard | Night | Sunlight | Role |
|---|---|---|---|---|
| `--sig-0` | `#E4E0D6` | `#240D01` | `#FFFFFF` | Noise floor; also `.meter` track and waterfall ground |
| `--sig-1` | `#B9B4A6` | `#6B2E0A` | `#B0B0B0` | Upper noise floor |
| `--sig-2` | `#7C7768` | `#B85A18` | `#5A5A5A` | Weak signal; also the listening sweep gradient |
| `--sig-3` | `#3A382F` | `#FF8A3D` | `#000000` | Strong signal; also `.meter` fill |
| `--sig-sync` | `#16181C` | `#FFC48A` | `#000000` | 1200 Hz sync pulse |

Note: in Sunlight, `--sig-3` and `--sig-sync` are both `#000000` — the sync tier is not
visually distinguishable from the strong tier in that mode. See §10.

### Metrics

| Token | Value | Role |
|---|---|---|
| `--rail` | `clamp(5.25rem, 6vw, 6.5rem)` | Nav rail width; also the strip's first column |
| `--strip` | `clamp(2.5rem, 3.4vh, 3.25rem)` | Top strip height |
| `--gap` | `clamp(0.5rem, 0.8vw, 1rem)` | Inline gaps |
| `--pad` | `clamp(0.6rem, 1vw, 1.1rem)` | Standard cell padding |
| `--rule` | `1px` (Sunlight `2px`) | Hairline rule |
| `--rule-heavy` | `2px` (Sunlight `3px`) | Structural rule, button borders, focus ring |

### Motion

| Token | Value | Role |
|---|---|---|
| `--t-fast` | `110ms` | Hover, meter fill, lock/unlock |
| `--t-mid` | `260ms` | Conditions change, toast rise |
| `--ease` | `cubic-bezier(0.2, 0.8, 0.2, 1)` | All eased transitions |

### Operating Conditions are token overrides

All three modes are **pure token overrides on `#app[data-conditions]`** — there is no
mode-specific layout, no mode-specific component, and no mode-specific class anywhere.
`applyConditions()` (`app.js:768-778`) writes the single attribute, re-derives the rail
label from it, refreshes the cached ramp, and repaints the canvases. Nothing else moves.

**Standard** (`data-conditions="standard"`, `:root` defaults) — pale card stock, near-
black ink, one alert yellow.

**Night Vision** (`style.css:66-88`) — not a dark theme. The CSS comment states the
reason: blue light at *any* brightness defeats scotopic adaptation, so the whole
interface moves to long wavelengths only. Every hue sits at or above roughly 590 nm; no
blues, no greens, no whites. Grounds drop to near-black warm browns (`#120600`,
`#0B0300`), ink becomes amber (`#FF8A3D`), the alert desaturates upward to `#FFB067`,
and the signal ramp runs from `#240D01` to `#FFC48A`. `--live` and `--warn` are
re-hued into the same long-wavelength band (`#D96A22`, `#FF5B1A`) rather than kept
green and red.

**Sunlight** (`style.css:94-119`) — WCAG AAA (7:1 minimum) with thickened strokes so
structure survives glare. Pure white ground, pure black ink, no mid-tones to wash out,
`--stock-3` promoted from a pale rule to solid `#000000`, and `--rule` / `--rule-heavy`
stepped up to `2px` / `3px`. This is the only mode that changes a metric token.

## 4. Type

**System stack, deliberately.** `--sans` and `--mono` are system font stacks with no
webfont anywhere in the prototype — a directive, not an oversight. There is no `@font-
face`, no font asset, and no network font request in `prototype/`. The consequence is
that the type renders in the operator's platform UI face; the world's character is
carried by grid, rule, case, and tracking rather than by a typeface purchase.

**Tabular numerals are load-bearing.** `style.css:143-147` applies `--mono` plus
`font-variant-numeric: tabular-nums` and `font-feature-settings: "tnum" 1, "zero" 1` to
`.mono, .data, td, th, input, .val` — every place a number lives. This is not
decoration. Values in this interface update continuously during a decode (SNR every
scanline, RMS every scanline, line count, elapsed, percent), and proportional figures
would make each column twitch horizontally on every tick. Tabular figures are what let
the thesis hold: a column can be read as a column while it is being written. The `zero`
feature adds the slashed zero, which matters for callsigns, where `W0XYZ` and `WOXYZ`
are different stations.

**Label voice** (`.lbl`, `style.css:150-157`): `--fs-label`, `--track-label` (0.14em),
uppercase, `--ink-3`, weight 600, `white-space: nowrap`. This is the boarding-pass
field caption, and it is used identically for arrival fields, telemetry segments,
section heads, and the pass stub. Table `thead` cells use the same voice one step
smaller (`--fs-micro`, weight 700).

Only two weights carry structural meaning: 700/800 for values and actions, 300 for
low-confidence values (§5). Body copy in `.pass p` is the sole place with a comfortable
`line-height: 1.55`; everything else is set tight and gridded.

## 5. The confidence grammar

The most distinctive idea in the build. `PRODUCT.md` Principle 1 says automation earns
trust by failing loudly, and auto-detection fails at documented, non-trivial rates.
This system answers that typographically: **how a value is set tells you how much to
trust it.** Applied via `data-conf` on `.val` (`style.css:407-419`).

| `data-conf` | Rendering | Meaning |
|---|---|---|
| `certain` | weight 700, `--ink` | The machine knows. VIS-detected mode, locked SNR, line count. |
| `guess` | weight 300, `--ink-3`, `letter-spacing: 0.18em`, italic | The machine is offering a value it does not trust. Light, faded, tracked apart, sloped — the word visibly loosens. Used for early SNR (`~9 dB`), `no FSKID`, `no VIS`. |
| `unknown` | weight 300, `--ink-3` | Nothing known yet. The em-dash placeholder state every field starts in. |
| `manual` | weight 700, `--ink`, `box-shadow: inset 0 -0.35em 0 var(--alert)` | A human set this. Rendered as a yellow highlighter swipe under the value — the pen mark on a printed document. |

Why typographic and not badged: a badge is a separate object that says something *about*
the value; it costs a column, it can be scanned past, and at six fields it becomes six
pieces of chrome. Setting the value differently means the confidence is read in the same
glance as the value itself, with no added surface. It also survives the palette
constraint — `guess` reads as weak in all three modes because weight, tracking, and
slope are hue-independent, which a coloured badge would not be under Night Vision.

The `manual` treatment and the control table's `.set[data-overridden]` use the *same*
inset yellow underline (`style.css:661`), so an operator-set value looks the same
whether it is in the record or in the control surface. That is the single yellow doing
its one job: marking change and human intent.

Confidence is animated as well as set: `.val[data-flap="1"]` runs a 90 ms `steps(1)`
opacity/translate tick while a field resolves (§8).

## 6. Components

### `.arrival` — the row

The signature surface (`style.css:343-354`, `index.html:115-169`). One record, typeset.
A three-column grid: `minmax(9rem, clamp(9rem, 15vw, 15rem))` for fields, `minmax(0,
1fr)` for the image, `clamp(8rem, 12vw, 12rem)` for telemetry. Ground is `--stock-2`.

- **`.fields`** — six `.cell` segments stacked down the left column (Time UTC, Mode,
  Callsign, SNR, Slant, Lines), each separated by a **dashed** `--stock-3` rule. The
  dashed rule is the perforation; solid rules are structure, dashed rules are tear
  lines. The column itself is closed with a dashed right border.
- **`.cell.detect`** — the detection-failure segment, `hidden` by default. Ground is
  `color-mix(in srgb, var(--alert) 18%, transparent)` — the only tinted panel in the
  system, and it exists for the 20–40% case the confidence grammar was built for. It
  carries a `.segset` of the three modes so the operator resolves what the machine
  couldn't. Visible in `prototype/shots/v2-sun-detectfail.png`.
- **`.imagecell`** — the row's largest field, and labelled `IMAGE` exactly like every
  other field, which is the thesis in one detail. Grid rows `auto minmax(0, 1fr)`. The
  chain from `.arrival` down through `.frame` to `canvas` carries **no `min-height`
  anywhere** (comment at `style.css:425-429`): a short viewport shrinks the picture, it
  never overflows onto the waterfall or the controls.
- **`.frame canvas`** — absolutely centred, `image-rendering: pixelated`, `--board`
  ground, `--rule-heavy --ink` border. **Width and height are set by JS, not CSS**, and
  carry no `aspect-ratio`: see §7a. Pixelated is correct here — smoothing an SSTV frame
  invents detail the radio did not send.
- **`.pct`** — progress percentage riding the frame's top-right in `--alert` with
  `--alert-ink`, tabular, `hidden` when idle.
- **`.scaleNote`** — native resolution and applied scale (`320x240 · 2x`) at the frame's
  bottom-left, in `--fs-micro` on `--stock-2`. The operator is told what they are
  looking at rather than left to guess whether a soft image is the signal or the zoom.
- **`.idle-note`** — "Press Listen to begin", bottom-centred, uppercase label voice.
  Backs the requirement that the canvas is never blank.
- **`.telem`** — three `.seg` segments (Signal, Input level, Sync) on
  `grid-auto-rows: min-content` / `align-content: start`, closed with a solid left rule
  and dashed internal rules, ground `--stock`. Centre freq (a constant 1900 Hz that
  never moved) and Elapsed (duplicated by the progress percentage and the scanline
  position) were cut: what survives is what changes and what changes a decision.
- **`.meter`** — a 0.5rem ruled bar, `--sig-0` track, `--sig-3` fill, `--stock-3`
  border. The fill animates by `transform: scaleX()` and not `width`, explicitly
  because it updates every scanline and animating width would relayout the panel each
  time (`style.css:511-515`).

States: every `.val` carries a `data-conf`; `resetArrival()` (`app.js:230-237`) returns
all six fields to `—` / `unknown`.

The transmit view reuses `.arrival` as a flat six-cell strip of `certain` values
(`index.html:206-213`) — same grammar, no image cell.

### `.ctable` — the control table

Every control is a row you edit in place. Columns are **CONTROL | AUTO | SET | RANGE**
(`style.css:546-724`, built by `buildTable()` at `app.js:97-183`).

This is `PRODUCT.md` interaction requirement 3 made structural rather than scattered:
the AUTO column shows what the machine derived, the SET column is the operator's
override, and both are visible at once on the same line. `.auto` is `--ink-3` at weight
400 (recessive); `.set` is weight 700 (dominant). An overridden `.set` cell gets the
yellow inset underline. When `c.auto` exists and an override is present, a small
`.revert` button labelled `auto` appears in the cell (`app.js:166-172`).

Three cell editors: `seg` renders a `.segset`, `num` and `text` render a borderless
input that only shows a border on hover (`--stock-3`) and focus (`--ink`) — it looks
like the cell until you touch it.

**Locked state** (`.ctable[data-locked]`, `style.css:700-714`) is how half-duplex
becomes legible in the control surface. `lockTable()` (`app.js:441-447`) disables every
input and button in the body, sets `aria-disabled`, and toggles the attribute. The
table then drops to `opacity: 0.72`, kills row hover, appends a `LOCKED` chip after
every control name, and mutes pressed segment buttons to `--ink-3`. The comment
explains why (`app.js:437-440`): an operator editing PTT method on a locked-out
transmitter otherwise gets no feedback that the edit is inert. The top strip
simultaneously reads "Transmit (RX locked)" or "Receive (TX locked)".

### `.board` — the gate board

The Log view (`style.css:726-789`, `prototype/shots/log-board.png`). Dark `--board`
panel, sticky `thead` in `--board-ink-2` label voice, monospace tabular rows at
`0.85em` vertical padding, `--board-2` zebra stripe on even rows, hover
`color-mix(in srgb, var(--alert) 14%, var(--board-2))`. Thumbnails are `5.5em × 4.1em`,
`object-fit: cover`, `image-rendering: pixelated`, bordered in `--board-ink-2`.

The departure-board mechanic: `tr[data-changed]` gets a `--rule-heavy --alert` outline
at `-2px` offset and `--alert` text, and **it holds until the operator looks at the
Log** — not on a timer. `acknowledgeLog()` fires from `goto('log')` (`app.js:625-632,
796`), with the comment that a timer would clear the highlight while the operator is
still watching the decode finish. The same unseen count drives a `--alert` badge on the
rail's Log button via `.rail button[data-unseen]::after` (`style.css:304-317`).

`.emptyboard` is the empty state: "No captures yet." plus a dimmed pointer at the
sample decode.

### `.fall` — the waterfall

A ruled measuring strip, never a glowing spectrum (`style.css:517-544`). A `.scale` row
of eight monospace frequency ticks (300 / 800 / 1200 SYNC / 1500 / 1900 / 2300 / 2800 /
3000 Hz) sits above a canvas of `clamp(4.5rem, 11vh, 7.5rem)`, on `--stock` ground with
hairline rules. Rendering detail in §7.

### `.btn` and `.segset`

`.btn` (`style.css:584-621`): `--fs-label`, weight 800, `--track-label`, uppercase,
`0.7em 1em` padding, `--rule-heavy --ink` border, `--stock` ground, square corners.
Content is a flex `space-between` of label and a `kbd` chip, so every primary action
carries its own keyboard shortcut on its face (`F5`, `Space`, `F9`, `F6`, `Esc`).
States: hover `--stock-2`; active inverts to `--ink` ground with `--stock` text;
disabled goes `--ink-3` on `--stock-2` with a `--stock-3` border. `[data-primary]` is
the `--alert` ground — the only button that gets the yellow, and there is exactly one
per view. `[data-danger]` is `--warn` ground with `--warn-ink` text, which flips per
mode (black in Standard and Night, white in Sunlight) because the warn ground is a
bright orange in the first two and a dark oxblood in the third.

`.segset` (`style.css:681-698`): an inline-flex of buttons in a single `--stock-3`
box with hairline dividers, no gaps, no radius. Selected is `aria-pressed="true"`,
rendered as full inversion — `--ink` ground, `--stock` text. It reads as a set of
punched positions on a card rather than a pill group.

### `.pass` — the first-run modal

Used only for first run, the one place that genuinely needs protected focus
(`style.css:874-910`, `index.html:288-308`). `.sheet` is a `color-mix(in srgb,
var(--board) 78%, transparent)` scrim. `.pass` is a two-column grid capped at
`min(46rem, 96vw)` and `92dvh`.

The `.stub` is the tear-off: a `--board` panel joined to the body by a **dashed
`--rule-heavy --ink` left border** — the perforation, at full modal scale — carrying
four label/value pairs (Station, Band, Calling, Mode) in board ink. It is the clearest
statement of the boarding-pass metaphor in the build. Copy is in brand voice: "Hey! I'm
SSTeVe."

### `.toast`

Bottom-centre, fixed, `--board` ground with a `--rule-heavy --alert` border, capped at
`min(34rem, 92vw)`, `rise` animation, auto-dismissed at 6000 ms (`app.js:466-472`). Two
lines by contract: `.what` (weight 700) names what happened, `.next`
(`--board-ink-2`, `--fs-label`) says what to do. This is `PRODUCT.md` Principle 5 as a
component shape — the structure makes it impossible to ship a bare error. Live examples
in `app.js`: "I couldn't work out the mode from the signal." / "The VIS header was too
noisy to read. Pick a mode above and I'll decode with it."

## 7. Signal rendering

Four content levels plus a sync level, resolved by `tone()` (`app.js:358-365`):

| Amplitude | Token | Meaning |
|---|---|---|
| `> 0.88` | `--sig-sync` | 1200 Hz sync pulse |
| `> 0.50` | `--sig-3` | Strong signal |
| `> 0.26` | `--sig-2` | Weak signal |
| `> 0.13` | `--sig-1` | Upper noise floor |
| else | `--sig-0` | Noise floor |

**Why it must not depend on hue.** The ramp has to survive the Night Vision palette,
which permits nothing below ~590 nm. A conventional blue-to-red spectral waterfall is
unrepresentable there — every hue it needs is banned. So the ramp is defined as
luminance steps and re-declared per mode, and signal is additionally encoded by *bar
height*: `drawFall()` draws each bin at `Math.max(1, Math.round(rh * (0.45 + v *
0.55)))` within a 4 px row band (`app.js:414`), so strength is legible from density and
height even where two adjacent tones are close. This also serves colour-blind operators
and the Sunlight mode, where mid-tones are deliberately absent.

**The measured distribution.** The four levels must actually appear in the data, not
merely exist as tokens (`app.js:367-371`). `pushFallRow()` (`app.js:373-398`) generates
96 bins across 300–3000 Hz:

- Noise floor: `0.05 + random() * 0.07` → 0.05–0.12, lands in `--sig-0`.
- Video band 1400–2400 Hz, centred 1900: `(0.18 + shoulder^1.6 * 0.46) * fade +
  random() * 0.07` added on top, where `shoulder = (1 - |hz-1900|/500)`. Band shoulders
  land roughly 0.20–0.45 (`--sig-1` / `--sig-2`); band centre lands roughly 0.50–0.85
  (`--sig-3`).
- QSB envelope: `fade = 0.72 + sin(qsb) * 0.28`, advancing 0.06 rad per row — a slow
  fade that walks band energy down into the weak tier and back.
- Sync: bins within 45 Hz of 1200 are forced to `0.92 + random() * 0.08` whenever the
  phase is past `listening`, giving `--sig-sync` a dedicated treatment rather than
  letting it read as "just a strong bin".
- VIS phase adds `0.3` to bins within 60 Hz of 1900.

The soft shoulders exist specifically so the strip does not jump from floor straight to
strong, which would collapse the four-level distinction to two.

Two printed reference rules are drawn over the strip (`app.js:419-427`): a dashed
`--ink-3` line at 1900 Hz (video centre) and a solid 2 px `--ink` line at 1200 Hz
(sync). They are drawn as rules on a measuring strip, not as markers on a scope.

Rows advance every 90 ms (`app.js:822`), retaining `ceil(height / 4)` rows. Tone lookups
are cached in `toneCache` and refreshed only on a conditions change — `getComputedStyle`
per bin was 96 lookups per row (`app.js:349-357`).

The decode canvas follows the same discipline: `themeColors()` (`app.js:250-258`) reads
`--board`, `--ink-3`, `--alert`, and `--sig-2` from the live computed style, with the
comment that the canvas is the largest light-emitting surface in the app, so Night
Vision cannot suppress blue in the chrome and then paint a cool grey slab here.

## 7a. Canvas sizing

SSTV modes do not share a resolution. `MODES` (`app.js:16-28`) carries the roster from
`backend-spec.md`'s `MODE_TIMINGS`:

| Mode | Native | Aspect | Status |
|---|---|---|---|
| Robot 36, Robot 72 | 320x240 | 4:3 | implemented (36) / planned |
| Scottie S1/S2/DX, Martin M1/M2, PD90 | 320x256 | 5:4 | Scottie S1, Martin M1 implemented |
| PD120, PD180, PD240 | 640x496 | ~1.29:1 | post-MVP |

Two consequences the layout must absorb.

**No fixed aspect-ratio.** The canvas carries none in CSS. A hardcoded `5 / 4` squashes
Robot 36 and the whole PD family, and the operator is judging a received photograph —
a distorted frame is a false reading, not a cosmetic issue. `sizeCanvas()`
(`app.js:300-329`) writes width and height inline from the active mode. The backing
store stays at native resolution so scanlines are drawn in real pixel coordinates;
only the CSS box scales.

**The cap bounds the display box, not the scale.** `CANVAS_MIN` 288px and `CANVAS_MAX`
660px. A flat multiplier would be wrong in both directions: 2x renders Scottie S1 at
640x512 and PD180 at 1280x992, which does not fit the row at any realistic viewport.
Bounding the box instead means every mode lands at roughly the same physical size,
which is correct — they are the same photograph at different fidelities.

`displaySize()` (`app.js:30-49`) snaps to a whole-number scale only when that costs
under 8%. Integer-only scaling produced a real defect: Robot 36's 240 lines fit 2x in a
500px frame while Scottie S1's 256 lines do not, so the *lowest*-resolution mode
rendered twice as large as the others. Measured at 1440x900, the current rule holds all
eight modes within **3.2%** of each other in displayed height with zero distortion:

| Mode | Display | Scale |
|---|---|---|
| Robot 36 / 72 | 640x480 | 2x (exact) |
| Scottie S1 / Martin M1 / PD90 | 620x496 | 1.94x |
| PD120 / 180 / 240 | 640x496 | 1x |

Above the ceiling the reclaimed width returns to the layout rather than being spent on
upscaled pixels. Past roughly 2x, an upscale of a noisy 320px capture shows bigger
pixels, not more picture — and can make a bad decode look smoother than it was.

## 8. Motion

Tokens: `--t-fast` 110ms, `--t-mid` 260ms, `--ease`
`cubic-bezier(0.2, 0.8, 0.2, 1)`.

**The split-flap typeset.** `typeset()` (`app.js:203-228`) is the signature mechanic.
A resolving field runs 7 ticks at 55 ms (385 ms total), and on each tick the characters
that have not yet "landed" are replaced with random glyphs from a pool of
`0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ·-`; the landing front advances left to right as
`i < (ticks / total) * text.length`. Spaces and colons are never scrambled, so time
values keep their shape. On completion the element takes its final text and its
`data-conf`. Concurrently `.val[data-flap="1"]` runs a 90 ms `steps(1)` keyframe
dropping to `opacity: 0.45` and `translateY(-1px)` — the physical flap tick. The
mechanic exists to make a field *arrive*, which is the whole thesis: the record is
being typeset, and you can see the machine committing.

Field order and delays in a decode (`app.js:524-581`): time and mode set at VIS, then
SNR arrives 300 ms in as a `guess`, and at 35% completion SNR firms to `certain`,
callsign lands at +260 ms, slant at +520 ms.

**The listening sweep.** `startListenSweep()` (`app.js:276-297`) runs a rAF loop while
`S.phase === 'listening'`: a 40 px linear gradient from transparent to `--sig-2` at
`globalAlpha: 0.5` descends at 1.1 px per frame over the ruled idle placeholder, with a
1 px `--alert` head line at the leading edge. Visible in
`prototype/shots/v2-night.png`. Its purpose is `PRODUCT.md` requirement 1: the canvas
must look *alive*, not merely non-blank, so the operator has continuous confirmation
that audio is flowing.

**The scanline reveal.** `revealScanlines()` (`app.js:311-330`) draws two lines per
tick with a 14 ms sleep, and paints a 2 px `--alert` rule at the decode head between
ticks — the live scanline, in the active palette.

**Other motion:** the status `.lamp` blinks on a `steps(1)` keyframe (1.1s listening,
0.7s TX) rather than pulsing smoothly — it is a relay contact, not a breath. `.toast`
rises 0.5rem on `--t-mid`.

**Reduced motion is handled in both layers, and that is deliberate.** CSS
(`style.css:950-956`) collapses all animation and transition durations to 0.001ms via
`prefers-reduced-motion`. But CSS alone would leave the JS still stepping 7 scramble
ticks and still sleeping 14 ms per scanline pair — visually static, functionally slow.
So `S.reduced` (`app.js:46`) is read from `matchMedia` at boot and short-circuits the
mechanics themselves: `typeset()` sets text and confidence immediately, the listening
sweep never starts, `revealScanlines()` sets `perTick = total` and draws the whole
image in one pass with no sleep, and every phase `sleep()` collapses (1900ms → 200ms,
340ms → 60ms, TX steps → 80ms). The animation is removed, not merely made instant.

## 9. Accessibility

**Measured contrast.** Ratios computed from the token values in `style.css` (WCAG 2.1
relative luminance). Every text pair in the system:

| Pair | Standard | Night | Sunlight |
|---|---|---|---|
| `--ink` on `--stock` | 15.76 | 8.51 | 21.00 |
| `--ink-2` on `--stock` | 7.30 | 6.70 | 17.40 |
| `--ink-3` on `--stock` | 5.12 | 5.39 | 12.63 |
| `--ink-3` on `--stock-2` | 4.63 | 5.20 | 11.09 |
| `--ink` on `--stock-2` | 14.26 | 8.21 | 18.43 |
| `--board-ink` on `--board` | 14.12 | 8.72 | 21.00 |
| `--board-ink-2` on `--board` | 6.74 | 6.28 | 15.91 |
| `--board-ink-2` on `--board-2` | 5.75 | 6.02 | 14.72 |
| `--board-ink` on `--board-2` | 12.04 | 8.36 | 19.44 |
| `--alert-ink` on `--alert` | 10.90 | 10.85 | 14.87 |
| `--alert` on `--board` | 10.90 | 11.35 | 14.87 |
| `--alert` on `--board-2` | 9.30 | 10.88 | 13.76 |

All text pairs clear 4.5:1 in all three modes. The tightest text pair in the system is
`--ink-3` on `--stock-2` in Standard at **4.63:1** — the label voice on a recessed
field, which is why the `--ink-3` comment in `style.css:19` reads "must clear 4.5:1 on
stock". Sunlight ranges **11.09:1 to 21.00:1**, clearing the AAA target its comment
claims. Night's floor is 5.20:1.

Two non-text pairs do not clear 4.5:1 and are noted honestly in §10.

**Two-tone focus.** `:focus-visible` (`style.css:175-189`) is a `--rule-heavy --alert`
outline at `1px` offset *plus* a `box-shadow` halo of `--ink` at `--rule-heavy + 2px`.
The comment records why: a single-token outline was invisible on every dark surface
(measured at 1.0:1 — `--ink` outline on the `--ink` board). One rule now works on both
grounds because the yellow ring reads on the dark board and rail while the surrounding
dark halo reads on pale card stock. On dark surfaces (`.rail`, `.board`, `.strip`,
`.pass .stub`) the halo inverts to `--board-ink` so the ring stays separated. `z-index:
5` keeps the ring above adjacent rules.

**Live regions.** A single `<p class="sr" role="status" aria-live="polite" id="live">`
(`index.html:315`) is written by `announce()` (`app.js:464`) at every state transition:
listening, mode detected, detection failure, each transmit step, picture locked (with
mode, callsign, and save confirmation), conditions change, and every control edit and
revert. The announcements are factual and direct, not conversational — `PRODUCT.md`
records screen-reader output as the deliberate exception to the brand voice, and the
prototype holds that line ("Mode set to Martin M1", not "OK, I'll use Martin M1").

The decode canvas has `role="img"` and a live `aria-label` that starts as "Decode
canvas. No image received yet." and is rewritten on lock to "Decoded image, {mode},
{lines} lines." (`app.js:590`). The `.toast` is `role="status"`.

**Semantic tables.** All four control surfaces and the log are real `<table>` elements
with `<caption class="sr">`, `<thead>`, and `scope="col"` headers. The control-table
caption states the column contract for screen-reader users: "Auto column shows values
SSTeVe derived; Set column shows your overrides." Segmented controls are
`role="group"` with `aria-label` and per-button `aria-pressed`. Number inputs get
`aria-label` including units ("Gain in %"). Nav uses `aria-current="page"`.

**Keyboard.** Global handler at `app.js:849-856`, guarded by `if (e.target.matches
('input')) return` so typing in a cell never fires a shortcut. `F5` Listen/Stop, `F6`
go to Transmit and transmit, `F9` sample decode, `Space` manual sync (only when
enabled), `Esc` aborts a transmission and dismisses first run. Each shortcut is printed
on its button's `kbd` chip, so the keyboard path is discoverable without documentation
— which serves gloved field operation as much as assistive tech.

## 10. Open decisions and known gaps

**Two responsive rules exist, and they do different jobs.**

`@media (max-height: 700px)` is load-bearing and works. Below that height the fields
column cannot hold six stacked cells (259px) plus the detection-failure cell (63px),
so the record reflows: fields become a horizontal strip above the image. This exists
because the previous approach — clipping the column with `overflow: hidden` — silently
deleted metadata fields and, at 620px, made the detection-failure recovery buttons
unreachable with no scroll to reach them. Verified at 1440x620 and 1440x400: all seven
fields visible, all three recovery buttons reachable, no scroll on either axis. The
canvas absorbs the loss instead (33px tall at 400px height), which is the correct
trade: the picture shrinks, no control or metadata disappears. **Never reintroduce
`overflow: hidden` on `.arrival .fields`** — a visible failure is better than a
silent one.

**There is no mobile layout, and that is a decision, not a gap.** The former
`@media (max-width: 900px)` block was deleted. It reflowed the shell into a viewport
that could not hold it and produced a broken result — clock overlapping status,
telemetry clipped mid-word, buttons past the right edge, canvas collapsed to a sliver —
which read as support that was never real. `PRODUCT.md` requirement 11 states there are
no layouts below 1280px; SSTeVe is a desktop shell bundled in Tauri and operated beside
a radio.

Below 1000px the views are hidden and `.below-floor` states the constraint in the
product's voice ("I need a wider window"), keeping the nav rail and top strip so the
app still reads as itself rather than an error page. The status group is suppressed
there because no operation can be running and it collided with the clock. A phone-sized
SSTeVe would be a different product with a different information architecture, not a
narrower version of this one.

**The Night Vision photograph conflict is unresolved.** Two requirements collide.
`PRODUCT.md` and the CSS comment demand blue-light suppression *everywhere*, because
blue at any brightness defeats scotopic adaptation — and the canvas is the largest
light-emitting surface in the app. But the operator's actual job is judging a received
picture, which requires accurate colour. The prototype currently resolves this by
theming everything around the image (ground, scanline head, sweep, placeholder rules,
waterfall) while drawing the decoded photograph at its true colours — i.e. **the image
is an operator-controlled exception**. That is a defensible position and it is not a
settled one. There is no UI in the prototype for the operator to control the exception,
so today it is an exception by omission rather than by choice.

**Auto/Manual control density is still unresolved.** `PRODUCT.md` "Explicitly
undecided" records `frontend-spec.md` §20's Auto (8 controls) / Manual (12–15 controls)
split as deferred to a 20-participant test that was never run. The prototype does not
resolve it — it shows seven RX controls at all times and makes AUTO and SET visible on
the same row, which is closer to §20.6's progressive-disclosure fallback than to either
named mode. Do not read the control table as a decision on density.

**No user testing.** None has been done on this prototype or on anything else. No
screen-reader testing with real assistive technology, and no blind operator has used
it, consistent with `PRODUCT.md`. The accessibility work above is measured and
structural, not validated.

**Two non-text pairs fail 4.5:1.** `--live` `#2E7D5B` on `--board` measures **3.56:1**
and `--warn` `#C4562E` on `--board` measures **3.99:1** — these are the status
`.lamp` fills. As non-text UI components the applicable bar is 3:1, which both clear,
so this is compliant; but the lamp is the only carrier of "locked" versus "transmitting"
in the strip, and it is worth confirming that the adjacent `statusText` is doing the
real work.

*Fixed 2026-08-05, after this document's first pass:* `.btn[data-danger]` previously
hardcoded `color: #fff` on `--warn`, measuring 4.45:1 in Standard and **3.10:1** in
Night — a real AA failure on the Abort button's label, and invisible to a token-level
contrast audit because it was the stylesheet's only colour literal. It is now
`--warn-ink`, defined per mode: 4.72:1 Standard, 6.76:1 Night, 9.17:1 Sunlight. The
three dead tokens (`--fs-board`, `--t-slow`, `--focus`) were removed rather than wired.

**Sunlight collapses the top of the signal ramp.** `--sig-3` and `--sig-sync` are both
`#000000`, so the 1200 Hz sync pulse is not distinguishable from strong signal by tone
in that mode. Bar height still differentiates them, but the token intent is not met.
Unresolved: giving sync a distinct tone in Sunlight means either lifting `--sig-3` off
pure black (weakening the AAA contrast the mode exists for) or carrying the distinction
entirely in bar height and the printed 1200 Hz rule.

**Not covered by the prototype.** Transmit confirmation (`PRODUCT.md` requirement 7 —
the prototype's Transmit button keys immediately with no confirmation step), the QSO
tab, image import, sonification controls, and the "motion sensitivity and focus
visibility are user-configurable" requirement (requirement 9 — the prototype reads the
OS preference but exposes no in-app setting). Smart replies were on this list and are
now **cut from scope** (`PRODUCT.md` §Scope, 2026-08-07).

**Two 2026-08-07 product decisions the visual system has not yet answered.**

1. **Record provenance** (`PRODUCT.md` interaction requirement 12). Every decode must
   show where it was heard — the operator's own antenna, or a remote SpyServer
   receiver — and the three record types (QSO / reception report / remote reception)
   must be distinguishable at a glance in the Log and in the record itself. This is a
   direct problem for the thesis: the `.arrival` row is a record being typeset, and a
   record that does not say where it came from is incomplete. It likely wants a field
   in `.fields` and a column on `.board`, but the confidence grammar (§5) may be the
   better instrument — provenance is a claim about trust, which is what that grammar
   already encodes. Unresolved.
2. **SDR as a first-class source.** Native SDR support (local devices and SpyServer) is
   v1 scope. That implies surfaces the prototype has none of: source selection, server
   connection state, push-button band frequencies, and honest reporting when a network
   stream stalls or drops mid-decode. A dropped stream must not read as a weak signal.
