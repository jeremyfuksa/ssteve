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

**Anyone who wants SSTV to just work.** Amateur radio operators receiving and
transmitting SSTV (slow-scan television) images over HF/VHF, plus receive-only
listeners running an SDR. The 30-year operator and the person decoding their first
image should both want this app, for the same reason: it is better made than what
they were using.

The baseline interaction is the same for all of them: the operator sits at a receiver
already tuned to a calling frequency (14.230 MHz USB is the common one), watches for a
signal to appear, and decides in real time whether the incoming audio is worth
committing 36–114 seconds to decode.

**The interface is shaped by operating situation, not by user type.** Situations are
what generate design constraints; a person moves between several of them in one
session. Each entry below names a condition a design can actually be checked against:

- **At the desk, monitoring.** Indoor, mains power, full-size screen, long idle
  stretches watching a calling frequency. The easy case — and not the reference case.
- **Field ops.** POTA/SOTA on battery, outdoors in direct sun or at night, gloves,
  1280×720 laptop, frequently offline.
- **Degraded signal.** QSB fading, contest QRM, urban noise, ALC pumping, oscillator
  drift, satellite Doppler. This is where auto-detection fails and manual overrides
  earn their place in the primary interface.
- **Receive-only.** An SDR with no transmit path — including unlicensed shortwave
  listeners. Decode, library, and logging apply in full; transmit, PTT configuration,
  and callsign-required gates must be *absent* from the interface, not merely disabled.
  Half-duplex arbitration is irrelevant here because nothing contends for the radio.
  This is a designed-for path, not an accommodation: SSTeVe drives the SDR itself —
  local device or SpyServer stream — and offers push-button band access, so the
  operator never assembles a virtual-audio-cable chain to get started. Via SpyServer
  they need no radio hardware at all (see Scope).
- **Eyes-free.** Hands on the radio and eyes off the screen — tuning by ear, working
  by keyboard, checking state without looking. Sonification is a *tuning* aid (pilot
  tone panned by slant error, chime on lock), which makes it as useful in gloves at
  2 AM as it is to a low-vision operator. Not claimed as a market; built because the
  audio domain is where the signal actually lives.
- **Scripted / headless.** The CLI and REST/WebSocket API driven directly, with no UI
  in the loop. Already served by the shipped core. Treat this as *infrastructure that
  pays off*, not as an audience: the headless boundary is why the desktop shell can
  bundle the engine as a subprocess and why the UI could be prototyped against a real
  contract. No evidence exists that scriptable SSTV is something people want.

**Migration matters as a feature, not an audience.** Operators arriving from
MMSSTV/QSSTV bring existing libraries; import must preserve their filenames and
metadata. That is a requirement on the importer, not a user segment.

*Provenance: the specs previously named four archetypes — Old Guard, Preppers,
Activators, Makers. They were inherited from the original spec with no research, no
community observation, and no user testing behind them, and they sliced four different
dimensions (migration history, ideology, environment, interface preference), so they
overlapped instead of partitioning. Preppers was the weakest: SSTV needs a licensed
counterpart, a known frequency, and a matching mode to work at all, which makes it a
poor emergency-comms mode, and the archetype's actual ask — good defaults, no
configuration — is table stakes for everyone. Replaced with situations 2026-08-07. Do
not restore them from git history.*

Eyes-free is the one situation with product investment already shipped: the core
carries stereo sonification for tuning by ear (`accessibility/audio_guidance.py`) and a
`--json` CLI mode built for screen readers. Existing investment, not an aspiration —
though see Accessibility & Inclusion for what remains untested.

## Product Purpose

Receive, decode, transmit, and log SSTV images with a modern engine and an interface
that does not require the operator to have learned MMSSTV in 2003.

**The problem, stated plainly:** the incumbent is a 2003 Windows binary with no point
of view. SSTV itself is not hard — audio in, picture out — but the software makes it
hard for no reason anyone can defend. SSTeVe is what the mode looks like when someone
actually designs it.

That splits into two problems that are really one problem seen twice:

1. **The incumbent is ancient.** MMSSTV and its descendants are 20-year-old desktop
   binaries. This was the original seed for building SSTeVe at all.
2. **The difficulty is manufactured.** Audio routing, input levels, PTT wiring, and
   mode matching defeat people before they ever see an image. None of that is
   intrinsic to SSTV; it is accumulated interface debt.

Success is an operator completing a decode they would otherwise have lost — because
auto-detection worked, or because the manual override they needed was reachable in
under two seconds when it didn't.

## Positioning

**A point of view is the product.** This is a deliberate goal carried over from
bearpaw.app: what makes an application worth using is having an argument about its
subject and holding it consistently, not accumulating features. MMSSTV's real failure
is not that it lacks capability — it is that hundreds of controls sit there with
nothing holding them together.

The consequence is a standard, not a slogan. **Any feature that does not serve the
point of view is a liability.** The failure mode for SSTeVe is becoming MMSSTV with
better typography. `DESIGN.md` carries the current visual argument — a decode is a
record being typeset, not a machine being monitored — and under this framing that
document is product thinking, not decoration. It does not need user validation to be
legitimate; it needs to be true to the medium and held consistently, which is a craft
standard and checkable without users.

Two things a neighboring SSTV application could not truthfully copy:

1. **A genuinely headless, API-first core.** The DSP engine is UI-agnostic and complete
   on its own: REST + WebSocket contract, a CLI, and 452 passing tests — though see
   §Evidence for what those tests do *not* cover. Any interface is a client. Incumbent
   SSTV applications are monolithic desktop binaries where the UI and the decoder are
   the same program.
2. **Feedback designed into the signal path, not bolted onto the chrome.** Stereo
   sonification lets an operator tune by ear — panning a pilot tone by slant error,
   chiming on lock. That is a DSP feature, not an ARIA audit: it works because the
   signal is audio, so the most direct readout of tuning error is also audio. Eyes-free
   by construction rather than by accommodation.

The brand voice is "friendly and nerdy" — a capable radio buddy. It shows up in
user-facing error copy: contractions, first person ("I couldn't detect the mode"), and
a concrete `suggested_action`. Screen-reader announcements are the deliberate
exception — factual and direct, never conversational.

## Operating Context

- **SSTV is slow.** A single image takes 36–114 seconds. The interface should not fight
  that rhythm with urgency it cannot deliver on.
- **Two signal paths, and the boundary differs between them.**
  - *Radio path (default).* SSTeVe operates post-SSB-demodulation, on 300–3000 Hz
    audio. RF gain, antenna tuning, noise blanking, AGC, and coarse VFO tuning belong
    to the radio and the operator — the software must not imply it controls them.
  - *SDR path.* SSTeVe owns the receiver: it tunes, demodulates SSB/FM, and produces
    its own audio, from either a local device or a **SpyServer** network stream. Here it
    genuinely does control the front end, and the interface may say so. Decided
    2026-08-07 — see Scope.

  The DSP core below the audio boundary is identical in all three. The SDR path adds a
  stage in front of it; it does not fork the decoder. A networked source additionally
  introduces stalls and disconnects that no local path can produce.
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
  overlay; this is a legal obligation, not a preference. It binds the *transmit* path
  only — receiving is unlicensed everywhere SSTeVe is likely to run, which is what
  makes the receive-only situation legitimate rather than a loophole.
- **A SpyServer receiver may be nowhere near the operator.** Received signal
  characteristics, propagation, and local time belong to the server's location, not the
  listener's. Anything the record asserts about reception conditions must be attributed
  to the receiver, and a QSO logged from a remote stream is not a contact the operator
  made.

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

- **The shipping UI.** `sstv_desktop/` contains a README and nothing else — no `.tsx`,
  no `package.json`, no component code.
- **A working HTML/CSS/JS prototype does exist** at `prototype/` (~2,900 lines across
  `index.html`, `style.css`, `app.js`, with screenshots in `prototype/shots/`). It is
  unwired: every value is synthetic except the decoded images, which are real reference
  captures. It proves the visual argument and the interaction model; it is not the
  product.
- **`DESIGN.md` describes an earlier revision than the prototype's current state.** The
  document details a four-column control table; the latest screenshots (`v10-session`)
  show that replaced by a right-hand control rail with the record's fields and a session
  list on the left. Reconcile before treating any component section as current.

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
12. **Every record says where it was heard.** Decided 2026-08-07, forced by SpyServer:
    a decode from a remote receiver is not the same claim as a decode from the
    operator's own antenna, and the interface must never let the two blur. Three record
    types, distinguished everywhere they appear:

    | Type | What happened | Export |
    |---|---|---|
    | **QSO** | Two-way exchange from the operator's station | ADIF, uploads |
    | **Reception report** | Heard at the operator's own station; no exchange | SWL conventions only |
    | **Remote reception report** | Heard at *someone else's* receiver via SpyServer | **Never as a QSO** |

    - **Provenance is on the row, not in a detail panel.** An operator can switch
      sources mid-session — three decodes off the local radio, three off a SpyServer in
      Berlin — and the Log must remain readable a week later without the operator
      recalling which was which.
    - **Signal figures display, attributed.** SNR and slant on a remote decode are real
      measurements of a real path; they are simply not the operator's path. Show them
      tied visibly to the receiver rather than suppressing them.
    - **ADIF export hard-blocks remote receptions as QSOs.** Not a warning, not a
      preference — a block. `qso_logger._format_qso_as_adif` currently emits
      `QSL_RCVD: Y` whenever images are attached, which asserts a *confirmed two-way
      contact*; a remote decode reaching that path would put contacts that never
      happened into LoTW, eQSL, or Club Log. The failure escapes SSTeVe and lands in
      shared infrastructure other operators depend on, which is why the boundary is
      absolute.
    - This follows the SWL-logging convention hams already have, rather than inventing
      a parallel one: "I heard you" and "we worked each other" have always been separate
      records, and the distinction is never blurred.
    - **This is a craft requirement, not only a data one.** `DESIGN.md` argues the
      interface is a record being typeset. A record that quietly conflates "I heard
      this" with "someone in Germany heard this" is a dishonest record.

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
| Two-way exchange | QSO / Contact |
| Heard, not worked | Reception Report |
| Heard via someone else's receiver | Remote Reception |
| Where a decode was heard | Source |
| The operator's own antenna | My Station |

Modes are named as operators name them: Scottie S1, Martin M1, Robot 36.

"Worked" is reserved for two-way contacts. A decode the operator only listened to is
"heard" — never "worked", and never "logged" without saying which kind of record.

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
- **Timing-based slant correction — a candidate differentiator, not yet measured.**
  Found 2026-08-07. Two slant systems exist and neither is what it appears:

  - `decode/hough_slant_corrector.py` is the one that runs, wired at
    `rx_manager.py:371`. It executes at Phase 5 (*save*), on the finished bitmap: it
    infers a dominant angle from image content and rotates. **It has no tests.**
  - `accessibility/slant_detector.py` measures drift from sync-pulse timing and reports
    `drift_pixels_per_line` with a confidence figure. **It has no callers** — only its
    `SlantErrorData` dataclass is used, borrowed by Hough to report results.
  - The raw material is already in the decode path: `decode_stream()` receives
    `sync_positions: list[int]` and computes line boundaries directly from consecutive
    positions with no drift model (`scottie_decoder.py:287-297`).

  **The hypothesis:** slant is a timing defect, not a geometric one — the transmitter's
  clock and the receiver's disagree, so each scanline starts fractionally late and the
  error accumulates. Correcting from the timing measurement means the error never
  happens: no rotation, no resampling, and it works identically on a picture of a fence
  and a picture of fog, because it never looks at the picture. Hough infers the
  consequence after the fact, which is weakest exactly where photographs are least
  structured (faces, foliage, sky) and can lock onto genuine diagonals in the subject.

  **Why it could matter:** MMSSTV's slant handling is a manual slider the operator
  nudges. "Straight pictures automatically, including on content where other decoders
  fail" is a claim visible in a side-by-side screenshot, and it serves every operator
  rather than a niche.

  **Why it is listed as undecided rather than scoped:** it is a DSP theory that has not
  been measured. This repo's history is a catalogue of confident unmeasured claims, and
  this must not become another. Sequence agreed 2026-08-07: build the decode-quality
  harness, baseline the current Hough path (including whether it ever *worsens* an
  image), and only then prototype timing-based correction and compare on the same
  corpus.

### Scope

Decided 2026-08-07 against the point-of-view standard: a feature earns its place by
serving the argument, not by existing in the backend.

**In — needs a design surface.** These are built in the core and currently have no UI:

- **MMSSTV library import** (`filesystem/mmsstv_importer.py`) — the load-bearing
  migration feature. It is how an operator's existing library survives the switch, and
  it serves problem #1 directly.
- **QSO logging** (`smart_features/qso_logger.py`, QSO routes) — an operator running a
  real station logs contacts. Promoted out of post-MVP. **Needs schema work before it
  ships:** the `QSO` model is a contact record end to end (`is_sent` "we initiated",
  `report` for an exchanged RST, ADIF export asserting `QSL_RCVD`) with no way to
  express "I only heard this." Interaction requirement 12 requires three record types
  and a hard export block; today's schema can represent exactly one.
- **FSKID and auto-RSV** (`decode/fsk_decoder.py`, `encode/fsk_generator.py`,
  `docs/features/`) — signal-path features a serious operator expects and a newcomer
  never notices. They belong to the record being accurate.

**In — not built at all.** Native SDR support, local *and* networked, decided
2026-08-07:

- **SSTeVe drives the SDR directly** — device open, tuning, and SSB/FM demodulation
  inside the application. Nothing exists for this yet; it is new work at every layer.
- **Two sources, one demodulator.** A local device (RTL-SDR and friends) and a
  **SpyServer** network stream are both just IQ at a requested center frequency. Build
  an IQ-source seam with two implementations behind it and keep the demodulator
  unaware of which is attached. Building local-first without that seam means operating
  on the demod path later to add the network case.
- **SpyServer is the lowest-friction entry to the hobby that exists.** The public
  server directory means an operator with no dongle, no antenna, and no license can
  decode SSTV from a receiver elsewhere in the world. Nothing to buy, nothing to wire —
  the strongest form of the "just works" claim, and a direct fit for the receive-only
  situation.
- **The network source brings a failure mode the pipeline has never modeled:** a socket
  can stall, lag, or drop mid-decode, where a local device cannot. Buffer underruns and
  server disconnects need first-class handling and honest reporting — a half-decoded
  image from a dropped stream must not read as a weak signal.
- **The reasoning is problem #2, not feature count.** The status quo for an SDR
  operator is: install a separate SDR application, install a virtual audio cable
  (VB-Cable, BlackHole), route the SDR app's output into the cable, route the cable
  into SSTeVe, and set levels on both sides — with sample-rate mismatches waiting at
  every step. That chain is the single worst onboarding path in the product and it is
  the *first* thing a receive-only user hits. Owning the device deletes it: plug in the
  dongle, pick it from a list, click a frequency.
- **Push-button band access.** SSTV calling frequencies per band as a first-class
  control — 14.230/14.233 (20m), 7.171 (40m), 21.340 (15m), 28.680 (10m), 3.845 (80m),
  145.500 simplex (2m), and the 145.800 ARISS downlink. On the SDR path these tune the
  receiver. On the radio path they remain a reference the operator tunes to by hand.
- **Accepted cost.** This adds an RF front end to an application that was architected
  post-demodulation, brings a hardware dependency for local devices
  (`soapysdr`/`rtlsdr`) and a wire-protocol implementation for SpyServer, and puts
  device support, sample-rate handling, demodulation quality, and network resilience on
  the maintenance ledger. Taken deliberately: the boundary was protecting an honesty
  claim, and on the SDR path SSTeVe really does control the front end, so the claim
  survives being restated rather than being broken.
- **Not a decoder fork.** The existing DSP core is unchanged; the SDR path feeds it the
  same 300–3000 Hz audio a sound card would.

**Cut — built, not shipped.** Smart replies (`smart_features/template_engine.py`,
`api/routes/smart_reply.py`, `templates/`) generate acknowledgment content on the
operator's behalf. SSTeVe presents the record faithfully; it does not perform for you.
The code stays in the repo and the routes keep working — no UI surface is built for it
and it is not a product commitment.

**Deferred, but now adjacent to a v1 feature.** *CAT control* (Hamlib/rigctl to a
conventional radio) is the radio-path twin of SDR band buttons — the same control,
different transport. It stays post-MVP: a real radio has an amp, an antenna switch, and
possibly a split the software cannot see, so tuning it carries risk that tuning an SDR
does not. *Multi-receiver* likewise moves closer once SSTeVe owns devices, but stays
deferred; half-duplex and the single-record interface both assume one signal path.

**Deferred by design.** AI captioning, full-duplex, gamification.
Post-MVP: brightness/contrast adjustment, re-decode from archived audio, Field Mode
overlay, PD/Wraase modes.

## Brand Commitments

- **Name:** SSTeVe. **Voice:** friendly and nerdy — a capable radio buddy, helpful
  without condescension. Never formal-instrument, never cute.
- Error copy is first person with contractions and a concrete `suggested_action`.
- Screen-reader output is factual and direct — the voice does not follow it there.
- **A visual proposal exists and is not yet committed.** `DESIGN.md` (2026-08-05)
  documents a visual world proven in a working prototype at `prototype/` — departure
  board meets segmented travel document, with a typographic confidence grammar and
  three Operating Conditions modes as pure token overrides. It is measured (contrast
  ratios computed per mode) and honest about its gaps. Treat it as the leading
  candidate and the current argument, not as shipped work: `sstv_desktop/` is still
  empty, and the prototype is unwired to the backend.
- The two contradictory palette/typography specs that preceded it were removed on
  2026-08-05 (`docs/design/DESIGN_RATIONALE.md` deleted outright; the visual sections
  of `frontend-spec.md` and `backend-spec.md` stripped). Do not recover them from git
  history.

## Evidence on Hand

- **Working backend** — 452 passing tests, zero exclusions; ruff and mypy clean and
  CI-gated. Runnable now: `cd sstv_core && uv run sstv-server` (127.0.0.1:8000).
  **Caveat, found 2026-08-07: none of those tests measure decode quality.** The
  integration tests assert HTTP status codes and session state (`201`, `200`, state in
  `[...]`); not one compares a decoded pixel to an expected image. The `reference_images`
  fixture in `tests/integration/test_decode_e2e.py` is defined and never used for
  comparison. "452 passing" means the plumbing works, not that pictures come out right.
- **API contract** — `docs/core/backend-spec.md` and `docs/core/openapi.json`
  (regenerate via `sstv_core/scripts/export_api_docs.py`). FastAPI also serves live
  interactive docs at `/docs` when the server is running.
- **Reference audio and images** — `sstv_core/tests/reference/{audio,images}/`. Thirteen
  real SSTV recordings with paired expected images across three sources: ARISS (real
  satellite passes, noisy), Essex Ham (Martin M2 / Scottie S2), and MMSSTV (five Scottie
  S1 files whose `*_expected.jpg` images are **ground truth from the incumbent
  decoder**). Used today for the sample-decode onboarding flow and for UI development
  without a radio attached. **Not yet used to verify a single decode** — this corpus is
  the foundation for the decode-quality harness, and the reason a Hough-vs-timing
  comparison can be settled by measurement rather than argument.
- **Documented failure rates** for gain, squelch, and AFC auto-detection
  (`frontend-spec.md` §20.3) — from domain-expert review, not measured in the field.
- **A running prototype and its design record** — `prototype/` plus `DESIGN.md`, with
  contrast ratios computed per Operating Conditions mode and a self-reported defect log.
  Evidence that the visual argument holds up in a real browser at real viewport sizes;
  not evidence that anyone wants it.

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

- **Target:** WCAG 2.1 AA as a floor, not a position. The eyes-free path (sonification,
  screen reader, full keyboard) is treated as a real operating mode rather than a
  compliance checkbox, because the backend already invests in it and because gloves,
  sun, and darkness create the same need as impaired vision does.
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
