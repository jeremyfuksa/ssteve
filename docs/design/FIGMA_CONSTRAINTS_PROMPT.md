# Figma constraints prompt — SSTeVe

Paste the block below into Figma AI (or any tool working on this file) before it
touches the SSTeVe design. Every number is verified against
`prototype/app.js` and `prototype/style.css` as of 2026-08-06.

---

You are working on SSTeVe, a desktop SSTV (slow-scan television) application for
licensed amateur radio operators. Before changing any layout, read these
constraints. They are not stylistic preferences — most of them come from radio
physics, human physiology, or a documented failure rate. Violating them produces
a design that looks fine and fails in use.

## 1. The shell is a fixed-size instrument

The app is 1175 × 708 px and does not stretch. It centres in the viewport with
the page ground showing around it.

- The shell **never scrolls**, on either axis. Instrument interfaces don't
  scroll: oscilloscopes, spectrum analysers, and transceivers don't, and neither
  does this. Field operators use gloves and trackpads and cannot scroll easily.
- Two regions may scroll **internally**: the Log board body, and the settings
  sheet body. Nothing else.
- All three tabs (Capture, Transmit, Log) hold the same 1175 × 708 frame. Tabs
  swap content inside a stable frame; the window must not resize when the
  operator changes tab.
- There is **no mobile layout**, deliberately. Below 1000 px wide the app hides
  its views and shows a single message. Do not design phone or tablet
  breakpoints — a phone-sized SSTeVe would be a different product with different
  information architecture, not a narrower version of this one.

Structure, left to right: an 86 px nav rail, then the content column at 1085 px.
Above both, a 40 px top strip spanning the full width.

## 2. Mode dimensions — the core constraint

SSTV is not one format. Each mode transmits a different pixel grid at a
different aspect ratio over a different duration. This is the full roster:

| Mode | Native px | Aspect | Duration |
|---|---|---|---|
| Scottie S1 | 320 × 256 | 1.250 (5:4) | 110 s |
| Scottie S2 | 320 × 256 | 1.250 (5:4) | 71 s |
| Scottie DX | 320 × 256 | 1.250 (5:4) | 269 s |
| Martin M1 | 320 × 256 | 1.250 (5:4) | 114 s |
| Martin M2 | 320 × 256 | 1.250 (5:4) | 58 s |
| Robot 36 | 320 × **240** | **1.333 (4:3)** | 36 s |
| Robot 72 | 320 × **240** | **1.333 (4:3)** | 72 s |
| PD90 | 320 × 256 | 1.250 (5:4) | 90 s |
| PD120 | **640 × 496** | 1.290 | 126 s |
| PD180 | **640 × 496** | 1.290 | 187 s |
| PD240 | **640 × 496** | 1.290 | 248 s |

Scottie S1, Martin M1, and Robot 36 are implemented today. The PD family is
planned. **Design for the whole table**, because the display rule has to survive
all of it.

Two facts drive everything: native width varies (320 or 640) and aspect varies
(1.250 to 1.333). A single hardcoded aspect ratio is therefore wrong for at
least a third of the roster.

## 3. The display rule: one fixed box, every image centred

**The canvas is a fixed 640 × 512 px box. It never resizes.** Each mode's
picture is drawn centred inside it, at a whole-number scale.

The box was derived by normalising the roster and taking the maximum of both
axes — the widest-relative mode is Robot 36 (4:3), the tallest-relative is
Scottie/Martin/PD90 (5:4) — giving 320 × 256 at native, doubled for legibility.

Resulting placement, all values exact:

| Mode | Scale | Drawn size | Offset (x,y) | Unused canvas |
|---|---|---|---|---|
| Scottie S1 / S2 / DX, Martin M1 / M2, PD90 | 2× | 640 × 512 | 0, 0 | none — fills the box |
| Robot 36 / 72 | 2× | 640 × 480 | 0, 16 | 16 px band top and bottom |
| PD120 / 180 / 240 | 1× | 640 × 496 | 0, 8 | 8 px band top and bottom |

Rules that follow, and why:

1. **Never distort the picture.** The operator is judging a received
   photograph; a squashed frame is a false reading, not a cosmetic issue. Do not
   apply a fixed `aspect-ratio` to the canvas. Do not stretch to fill.
2. **Never crop the picture.** The operator must see exactly what arrived.
3. **Whole-number scales only** (1×, 2× — never 1.93×). An SSTV capture is
   already noisy, and interpolating it makes a marginal decode look smoother
   than it was — a flattering lie in a tool whose job is judging signal quality.
   Render with nearest-neighbour / pixelated smoothing, never bilinear.
4. **Accept the bands.** A shorter mode leaving 16 px of unused canvas is a
   deliberate trade. It buys a frame that doesn't move when the mode changes, a
   layout with no circular dependency between canvas and column, and square
   pixels throughout. Do not "fix" the bands by resizing the frame.
5. **Do not scale past 2×.** Beyond that, a 320 px source shows bigger pixels,
   not more picture.
6. **State the scale on screen.** A small readout in the frame reads
   `320x240 · 2x` so the operator knows whether softness is the signal or the
   zoom.

Two failure modes to avoid, both of which were hit and fixed during design:

- **A flat 2× multiplier is wrong.** It renders Scottie S1 at 640 × 512 and
  PD180 at 1280 × 992, which does not fit the layout at any realistic size. The
  cap bounds the *displayed box*, not the scale.
- **Integer-only scaling derived from available height is wrong.** Robot 36's
  240 lines fit 2× into a 500 px frame while Scottie S1's 256 lines do not, so
  the *lowest*-resolution mode rendered twice as large as everything else. The
  fixed box eliminates this: scale is chosen per mode from the box, not from
  leftover space.

## 4. The canvas is never blank

While listening, the canvas must show continuous visual feedback — a ruled
placeholder plus a slow animated sweep. Operators need to verify the receiver is
live even before a signal arrives. A dead grey rectangle is a constraint
violation, not an empty state.

During decode, scanlines fill top to bottom with a bright rule at the decode
head, so the operator can see exactly how much of the picture has arrived.

## 5. Waterfall — four levels, never hue-dependent

The frequency strip sits directly above the canvas, at the same 640 px width,
roughly 60–90 px tall. It spans 300–3000 Hz.

- It must show **four distinguishable signal levels** at a glance: noise floor,
  weak signal, strong signal, and the 1200 Hz sync pulse.
- Those levels must be distinguishable by **luminance, not hue**, because the
  whole interface shifts to a red-amber palette in Night Vision mode. A colour
  ramp that only works in one palette is broken.
- The 1200 Hz sync pulse gets a distinct treatment from raw signal strength —
  the operator uses it to confirm correct tuning, so it must not read as "just a
  strong bin."
- Two printed reference rules: a solid one at 1200 Hz, a dashed one at 1900 Hz
  (the SSTV centre frequency).

## 6. Operating Conditions — three palettes, physiology not theming

Every colour is a token, because the entire interface reskins in three modes.

- **Standard** — pale card stock ground, near-black ink. Must render the decoded
  image with accurate colour; the surrounding UI must not tint it.
- **Night Vision** — *not* a dark theme. Blue light at **any** brightness
  defeats scotopic (dark) adaptation, so every hue in the interface sits at or
  above ~590 nm: amber on near-black, no blues, no greens, no whites. This
  includes the canvas ground and the waterfall, which are the largest
  light-emitting surfaces on screen.
- **Sunlight** — WCAG AAA (7:1 minimum) and **thickened strokes**, so structure
  survives glare. Rules go from 1 px to 2 px, heavy rules from 2 px to 3 px.

All text must clear 4.5:1 against its background in all three modes.

## 7. Live controls must never be buried

Gain, squelch, and AFC stay in the primary interface at all times. They are not
settings.

The reason is documented failure rates: gain auto-detection fails **30–40%** of
the time on weak signals with QSB fading, and **10–15%** with ALC pumping;
squelch auto-threshold fails **20%** in contest QRM and **15%** for urban
operators. Combined with the fact that SSTV is one-shot — an image takes 36–269
seconds and does not repeat — a wrong gain at second 20 of a 110-second decode
must be correctable *while the picture is still arriving*.

Everything genuinely set-once — audio device, sample rate, FFT size, PTT method,
serial port, callsign, save directory — belongs in a modal settings sheet. That
split is the point: hiding the set-once controls is what makes room for the
live ones.

## 8. Half-duplex

One operation at a time: decode **or** transmit, never both. The backend
enforces this and returns HTTP 409 on violation.

The interface must make the active operation and its exclusivity legible. When
receive owns the radio, the transmit controls render visibly locked, and vice
versa. An operator editing an inert control with no feedback is a failure.

## 9. Automation states itself honestly

Confidence is carried typographically, not with badges or percentages:

- **Certain** — solid weight, primary ink.
- **Guess** — light weight, italic, tracked out, tertiary ink.
- **Operator override** — solid weight with a saturated underline, so a human
  correction is visible at a glance.
- **Unknown** — em dash, tertiary ink.

When mode detection fails outright (a documented 20–40% case), the interface
says so in plain language and offers manual mode selection inline — it does not
silently guess.

## 10. Voice

Error and status copy is first person with contractions, and always names a next
step: "I couldn't work out the mode from the signal. The VIS header was too
noisy to read. Pick a mode above and I'll decode with it."

Screen-reader output is the deliberate exception — factual and direct, never
conversational.

## 11. Things that are not up for redesign

- The 640 × 512 canvas box, and centring every mode inside it.
- Whole-number pixel scaling.
- No-scroll shell; no mobile layout.
- Gain / squelch / AFC in the primary interface.
- Four luminance-distinct waterfall levels.
- Night Vision suppressing short-wavelength light across the *whole* interface,
  including the canvas.
