# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

<!-- Delivered as a React/Tauri desktop shell (`sstv_desktop/`, currently an empty
placeholder). The shell bundles the Python core, spawns it as a subprocess, and talks
to it over REST + WebSocket. Design language is web, not native macOS/Windows; the
Tauri layer supplies OS integration (file dialogs, tray, serial access), not a
platform-specific design idiom. -->

## Users

Licensed amateur radio operators receiving and transmitting SSTV (slow-scan
television) images over HF/VHF. Four archetypes are named across the specs; all four
are documented, and no round of user testing has ranked them:

- **Old Guard** — long-time operators migrating from MMSSTV/QSSTV. Expect predictable
  desktop controls, dense readouts, and library import that preserves their existing
  filenames and metadata.
- **Preppers** — want to plug in, pick a device, and receive an image without
  configuration. Drive the first-run flow and the quality of defaults.
- **Activators** — POTA/SOTA field operators on battery power, outdoors, sometimes in
  bright sun or gloves, often on a small laptop screen and offline.
- **Makers** — operate the CLI and REST API directly and script against them. Largely
  served by the existing headless core rather than by the UI.

The operating situation shapes the interface more than the archetype does: an operator
sits at a radio already tuned to a calling frequency (14.230 MHz USB is the common
one), watches for a signal to appear, and decides in real time whether the incoming
audio is worth committing 36–114 seconds to decode.

**Blind and low-vision operators are a real, served audience.** The core already ships
stereo sonification for tuning by ear (`accessibility/audio_guidance.py`) and a `--json`
CLI mode built for screen readers. This is existing product investment, not an
aspiration.

## Product Purpose

Receive, decode, transmit, and log SSTV images with a modern engine and an interface
that does not require the operator to have learned MMSSTV in 2003.

Success is an operator completing a decode they would otherwise have lost — because
auto-detection worked, or because the manual override they needed was reachable in
under two seconds when it didn't.

## Positioning

Two things a neighboring SSTV application could not truthfully copy:

1. **A genuinely headless, API-first core.** The DSP engine is UI-agnostic and complete
   on its own: REST + WebSocket contract, a CLI, and 444 passing tests. Any interface
   is a client. Incumbent SSTV applications are monolithic desktop binaries where the
   UI and the decoder are the same program.
2. **Accessibility designed into the signal path, not bolted onto the chrome.** Stereo
   sonification lets an operator tune by ear — panning a pilot tone by slant error,
   chiming on lock. That is a DSP feature serving blind operators, not an ARIA audit.

The brand voice is "friendly and nerdy" — a capable radio buddy. It shows up in
user-facing error copy: contractions, first person ("I couldn't detect the mode"), and
a concrete `suggested_action`. Screen-reader announcements are the deliberate
exception — factual and direct, never conversational.

## Operating Context

- **SSTV is slow.** A single image takes 36–114 seconds. The interface should not fight
  that rhythm with urgency it cannot deliver on.
- **The audio domain is the whole world.** SSTeVe operates post-SSB-demodulation, on
  300–3000 Hz audio. RF gain, antenna tuning, noise blanking, AGC, and coarse VFO
  tuning belong to the radio and the operator — the software must not imply it controls
  them.
- **Signals are hostile.** QSB fading, contest QRM, urban RF noise, ALC pumping,
  oscillator drift, and satellite Doppler are normal conditions, not edge cases.
- **Half-duplex.** One operation at a time — decode or transmit, never both. Enforced
  by the backend; violations return HTTP 409. The interface must make the active
  operation and its exclusivity legible.
- **Sessions are long.** Field Day and contests run 8+ hours, sometimes overnight,
  sometimes outdoors in direct sun.
- **Hardware is heterogeneous.** USB audio interfaces (Digirig, SignaLink), virtual
  audio cables, and direct line-out all present wildly different input levels. PTT is
  serial RTS/DTR, VOX, or a manual switch on the radio.
- **FCC Part 97 requires station identification.** Transmitted images carry a callsign
  overlay; this is a legal obligation, not a preference.

## Capabilities and Constraints

### Built and working (verified by the test suite)

- RX: bandpass → VIS detection → per-mode decode (Scottie S1, Martin M1, Robot 36) →
  Hough slant correction → save → DB record → WebSocket events.
- TX: mode→encoder mapping, VIS + FSKID generation, serial/VOX PTT with pre/post delays.
- REST + WebSocket API: decode, transmit, devices, config, images, QSO, smart replies,
  MMSSTV import, file-based mode detection. Contract in `docs/core/backend-spec.md` and
  `docs/core/openapi.json`.
- Filesystem library watcher, image importer, MMSSTV importer, CLI, DB + migrations.

### Not built

- **The entire UI.** `sstv_desktop/` contains a README and nothing else. There is no
  `.tsx`, no `package.json`, no design tokens, no component code anywhere in the repo.

### Interaction requirements (distilled from the December 2025 review; behavior only)

These are settled operational constraints. They describe what the interface must *do*,
not what it must look like.

1. **The canvas is never blank while listening.** An operator needs continuous visual
   confirmation that audio is flowing and the signal is where they think it is. An idle
   canvas shows the last decoded image or a deliberate placeholder — never an empty
   void. This was unanimous across all four expert reviews.
2. **A waterfall (300–3000 Hz spectrum) is non-negotiable.** It is how an operator
   confirms a signal exists, judges whether they are tuned correctly, and spots
   interference. Every serious SSTV application has one. It is not a settings-menu
   feature.
3. **Auto-detection sets defaults; it does not replace control.** Gain, squelch, and
   AFC auto-detect all fail at documented, non-trivial rates — 30–40% on weak/fading
   signals for gain, ~20% in contest QRM for squelch, and 100% for satellite work if
   AFC range is wrong. Gain, squelch, and AFC overrides therefore stay in the primary
   interface. Burying them in settings is a correctness failure, not a taste choice.
4. **When automation fails, say what to do about it.** Failures surface an actionable
   next step ("signal too weak — try raising gain") with a path to the relevant control,
   not a bare error.
5. **AFC lock must be verifiable.** Show the detected sync frequency so the operator can
   confirm the lock landed on the 1200 Hz sync pulse and not a harmonic or the black
   level. A silent wrong lock produces a wrong-mode decode with inverted color.
6. **Decode state is a legible progression.** Listening → VIS detected → sync lock →
   decoding (with progress) → complete. Scanlines render as they arrive, with no
   buffering delay.
7. **Transmission requires deliberate confirmation.** Keying a transmitter is a
   real-world, non-undoable act on shared spectrum. It gets an explicit confirmation
   step.
8. **Operating Conditions modes are operational, not decorative.** Standard / Night
   Vision / Sunlight exist to preserve dark adaptation at 2 AM and to stay legible in
   direct sun. They are named for the condition they solve, never for how they look.
9. **Motion sensitivity and focus visibility are user-configurable.**
10. **The main shell does not scroll.** Fixed frame, minimum 1280×720 — the field-laptop
    floor, and 1024×576 effective at Windows' common 125% scaling. Instruments have
    fixed layouts; scrolling hides information that may be critical and is hostile to
    gloves and touchpads. Modals and progressive-disclosure panels may scroll as a last
    resort. Larger viewports gain breathing room, not a different layout.
11. **Desktop-only.** SSTV needs audio I/O, PTT wiring, and a stable surface. There are
    no layouts below 1280px wide.

### Vocabulary

Operator-facing language, used consistently in UI, docs, and audio cues:

| Concept | Term |
|---|---|
| Start receive | Listen |
| Receiving | Listening / Decoding |
| Image saved | Decode Complete |
| Signal strength | Signal Level / SNR |
| Mode selection | SSTV Mode |
| Image gallery | Log / Gallery |

Modes are named as operators name them: Scottie S1, Martin M1, Robot 36.

### Explicitly undecided

- **Control density.** `frontend-spec.md` §20 records an Auto mode (8 controls) and a
  Manual mode (12–15 controls) as a decision, but §20.6 defers the choice to a
  20-participant user test that was never run. No evidence exists for either. The
  tension between novice simplicity and operational flexibility is real and unresolved;
  §20.6's own "both fail" branch points to progressive disclosure within a single
  interface as the fallback. **Do not treat the Auto/Manual split as settled.**
- **Watcher default directory** — with `image_save_directory` unset, the library watcher
  does not start. Whether it should default to `~/sstv_images` is an open product call.
- **Beta date** — the January 2026 target lapsed; no new date is set.

### Deferred by design

AI captioning, multi-receiver, full-duplex, gamification. Post-MVP: QSO tab,
brightness/contrast adjustment, re-decode from archived audio, Field Mode overlay,
CAT control, PD/Wraase modes.

## Brand Commitments

- **Name:** SSTeVe. **Voice:** friendly and nerdy — a capable radio buddy, helpful
  without condescension. Never formal-instrument, never cute.
- Error copy is first person with contractions and a concrete `suggested_action`.
- Screen-reader output is factual and direct — the voice does not follow it there.
- **No visual identity is committed.** The repo previously carried two contradictory
  palette/typography specs; neither was ever implemented, and both were removed on
  2026-08-05 (`docs/design/DESIGN_RATIONALE.md` deleted outright; the visual sections
  of `frontend-spec.md` and `backend-spec.md` stripped). The visual world is an open
  decision, to be chosen deliberately when UI work begins — not recovered from git
  history.

## Evidence on Hand

- **Working backend** — 444 passing tests, zero exclusions; ruff and mypy clean and
  CI-gated. Runnable now: `cd sstv_core && uv run sstv-server` (127.0.0.1:8000).
- **API contract** — `docs/core/backend-spec.md` and `docs/core/openapi.json`
  (regenerate via `sstv_core/scripts/export_api_docs.py`). FastAPI also serves live
  interactive docs at `/docs` when the server is running.
- **Reference audio and images** — `sstv_core/tests/reference/{audio,images}/`. Real
  SSTV signals for the sample-decode onboarding flow and for UI development without a
  radio attached.
- **Documented failure rates** for gain, squelch, and AFC auto-detection
  (`frontend-spec.md` §20.3) — from domain-expert review, not measured in the field.

**Absent — must not be fabricated:** no users, no user testing (the §20.6 protocol was
never run), no telemetry, no SUS scores, no beta testers, no press, no pricing or
licensing decision, no deployment or distribution channel. The "8.5/10 → 9.5/10" design
ratings that appeared in the now-deleted design rationale were AI self-assessments from
an unrecoverable review session, not external validation — if they resurface via git
history, they are not evidence.

## Product Principles

1. **Automation earns trust by failing loudly.** Auto-detection is a good default and an
   unreliable narrator. Every automatic decision is visible, verifiable, and
   overridable in the primary interface — never buried behind a settings modal.
2. **The operator's real conditions outrank the demo.** Night, sun, gloves, a 720p field
   laptop, contest QRM, and a fading signal are the design target. A calm indoor shack
   is the easy case, not the reference case.
3. **Honor the pace of the mode.** Two minutes per image is the medium, not a latency
   bug. Don't manufacture urgency the radio can't deliver, and don't pad the wait with
   theater either.
4. **Accessibility is in the signal path.** Sonification, screen-reader output, and
   keyboard operation are how some operators use this product at all — not a compliance
   layer applied after the visuals are done.
5. **Say what happened and what to do next.** Errors name the cause in plain language
   and point at the control that fixes it.

## Accessibility & Inclusion

- **Target:** WCAG 2.1 AA, with blind operation treated as a supported path rather than
  a compliance checkbox — the backend already invests in it.
- Status transitions announce via live regions. The canvas has a textual equivalent;
  log entries read as descriptive labels ("Picture locked · Scottie S1 · 14:30 UTC").
- Progress indicators expose real values to assistive tech, not just visual fill.
- Full keyboard operation with visible focus, at configurable intensity. Keyboard
  matters for speed and for gloved field operation, not only for assistive tech.
- Motion is configurable down to none.
- Operating Conditions modes serve dark adaptation and sunlight legibility.
- **Untested:** no screen-reader testing has been done with real assistive tech, and no
  blind operator has used the product. Sonification is implemented and unit-tested; it
  has never been validated with its intended users.
