# SSTeVe MoSCoW

> Drafted 2026-08-21. Where a line makes a claim about what the code does today,
> it is annotated with what is actually true — a Must is a commitment, and it is
> worth knowing the size of one before making it.

## Must / Must Not

### Connectivity

- App must have three connectivity methods:
  - Aux in/out
  - USB
    - Airspy HF+
    - HackRF (future support)
  - SpyServer
- Transmit is available only for Aux in/out. HackRF transmit is future.
  **SpyServer never transmits** — it is someone else's receiver.

  *Consequence for the UI: the transmit region's presence is driven by the
  connectivity method, not by license or preference. On SpyServer and
  receive-only USB it is absent, not disabled.*

### Modes

**What "most used" means here is measured, not assumed.** The mode list is
tiered by the evidence behind it, because the evidence is thin and uneven.

| Tier | Modes | Evidence |
|---|---|---|
| **Heard on air** | Scottie S2, Martin M1, Martin M2 | 14 off-air captures — 6 Scottie S2, 4 Martin M1, 4 Martin M2 (manifest.json); plus the first live decode (KG5JJ, Martin M1, 2026-08-21) |
| **Asserted common, never captured** | Robot 72, PD 120 | Domain claims in `AUTO_FIRST_PLAN.md` and PRODUCT.md. **Zero** appearances in our own captures |
| **Detected, never heard** | Scottie S1 / DX, Robot 36, PD 90 / 180 / 240 | VIS templates only |

- App **must** decode and display every mode in the *heard on air* tier.
- App **should** decode Robot 72 and PD 120, on capture evidence.
- Modes outside the detected set are **recognized and declined by name**, never
  silently failed.

*The uncomfortable finding: Scottie S2 is the most-heard mode in our data.
Robot 36 has a decoder and has never once appeared in a capture. The mode
priority the docs assert and the mode distribution we measured do not agree,
and only one of them is evidence.*

*Sample caveat: 14 transmissions, one location, one band, mostly one day. Enough
to know Scottie S2 and Martin M1 are common; not enough to conclude Robot 72 and
PD 120 are rare. The right response is more capture, not a firmer claim.*

#### Every mode we have actually heard now decodes

Found broken 2026-08-21 by cross-checking four sources; fixed 2026-09-11
(#140, #153). Verified state:

| Mode | Engine (`rx_manager`) | API | Test suite | Off-air captures |
|---|---|---|---|---|
| Scottie S1 | ✅ | ✅ | ✅ | 0 |
| **Scottie S2** | ✅ | ✅ *(was rejected)* | ✅ | **6** |
| Martin M1 | ✅ | ✅ | ✅ | **4** |
| **Martin M2** | ✅ *(was no dispatch)* | ✅ | ✅ | **4** |
| Robot 36 | ✅ | ✅ | — | 0 |

The finding that made this urgent still stands as a lesson: **Robot 36 —
never once heard on air — was the only mode that worked end to end, while
every mode we had actually captured was blocked somewhere.** Neither defect
was in the DSP. Both were lists.

1. **Scottie S2 was rejected by the API.** `SUPPORTED_DECODE_MODES` restated
   the engine's `DECODABLE_MODES` and drifted from it, so `POST /decode/start`
   returned 400 for the most-captured mode in the corpus while the decoder
   handled it fine. The API set is now derived from the engine's, and a test
   fails if the two ever disagree again. Auto-detect was never affected, which
   is why it went unnoticed: only a *forced* mode hit the list.

2. **Martin M2 decoded in tests but not in the product.** The corpus suite
   maps `MARTIN_M2 → (MartinM1Decoder, MartinM2Config, 226.798)` and all four
   fixtures pass pixel-exact, but `rx_manager._get_decoder` had no `martinm2`
   branch, so the product answered "I can't decode that yet" for both of the
   only two captures carrying a verified FSKID callsign. It was a missing
   `elif`, and the verification evidence already existed.

*The suite proving a mode decodes while the product cannot reach it is the
shape to watch for: a test that bypasses the wiring tests the DSP and nothing
else.*

*Contrast with Robot 72 / PD 120, which `AUTO_FIRST_PLAN.md` correctly calls
blocked on capture: no recordings, no encoder, no independent oracle. Martin M2
is blocked on nothing.*

*Doc drift found alongside: PRODUCT.md and `AUTO_FIRST_PLAN.md` say 3 modes
decode (it is 4); `AUTO_FIRST_PLAN.md` says the corpus is "6 Scottie S2, 5
Martin M1, 3 Martin M2" (the manifest says 6 / 4 / 4, 14 total); the comment at
`decode.py:38` says the enum advertises 12 modes (it has 14).*

*Loose end: `SSTVMode` carries 14 entries; only 11 have detector templates. PD 160
and Wraase SC2-180 are returned by `from_vis_code` and never matched from a
signal, so they fail detection rather than being named and declined — which
contradicts the "recognized and declined" rule above.*

### The window

- User must be able to use **every feature of this app from the one main
  window**.

  *This is the single-window model — see
  `docs/superpowers/specs/2026-08-21-single-window-activity-log-design.md`.
  It settles a question that spec left open: deep browsing (bulk operations,
  MMSSTV import review) cannot be a second window. It is a modal or an expanded
  state, which requirement 10 permits for progressive disclosure.*

- The window must **fit inside 1280×720**, but it is **not 16:9**. Shape is
  whatever serves the UI.

  *Sized to its content the window is taller than wide — roughly 1020×880 at a 2×
  canvas. 16:9 was a screen measurement mistaken for a UI requirement; forcing a
  5:4 picture, a wide presence strip and a row grid into it produced a canvas
  stretched wide and half empty. Recorded in `frontend-contract.md` §20.11.*

  *When the window is too small for everything, **canvas scale degrades first** —
  1.5× at the field floor, 2× at ~1020×880. The presence strip and the log hold.
  A picture at 1.5× is still legible; a presence display with four seconds of
  history is not proof of anything.*

- Display view for the rx/tx image must be **no bigger than it needs to be**.

  *The canvas is sized to the picture, not to a share of the viewport. SSTV
  frames are small and fixed — 320×256 for Scottie S1 and Martin M1, 320×240 for
  Robot 36. The canvas shows the current mode's frame at a whole-number scale and
  claims no space it is not using to display pixels. Whatever it does not need
  belongs to the log. Rule recorded in `docs/core/frontend-contract.md` §20.4.*

- The waterfall is a **presence display, not a tuning instrument**.

  *Because everything is automatic — AFC locks and reports its frequency, VIS reads
  the mode — nobody reads a number off the spectrum to make a decision. Its job is
  visual proof that reception is happening, which needs a ~64px strip rather than
  the 200px panel the old spec assigned it. It doubles as the silence display: the
  same spectrum feed shows the live noise floor when nothing is on the air, which
  is 97.4% of the time.*

### The record

- App must keep a record of all received and transmitted images, including
  **date/time, mode, and frequency**. This can be turned off in settings.

  *New requirement: frequency. The `Image` model stores filepath, callsign, SNR
  and timestamp — frequency is not among them, so this is a schema change.*

  *It also inherits the provenance problem: on the SpyServer path the frequency
  is the **server's** tuned frequency, and the reception is not the operator's.
  This lands next to the QSO / reception report / remote reception split that
  PRODUCT.md already flags as needing schema work — the two should be one
  migration, not two.*

## Open

- Does "can be turned off in settings" mean *stop recording images*, or *stop
  recording metadata about them*? The first is a file-writing decision, the
  second a database one, and they have different consequences for the log.
