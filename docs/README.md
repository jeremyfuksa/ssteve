# SSTeVe Documentation

**Last reviewed:** 2026-08-05

> **This index deliberately states no status of its own.** It has been wrong twice.
> Earlier versions claimed "~70-75% complete", "Phase 4: Filesystem ⏳ Pending", and
> "~63 hours remaining" long after that work had shipped, which is worse than having no
> index at all — it caused completed work to be re-scheduled.
>
> **`status/PROJECT_STATUS.md` is the single source of truth for what works.** It is
> re-baselined against the tree and the test suite, not against other docs. When any
> document here disagrees with the code, the code wins.

---

## Start here

| If you want… | Read |
|---|---|
| What actually works right now | [`status/PROJECT_STATUS.md`](status/PROJECT_STATUS.md) |
| Who this is for and what must stay true | [`../PRODUCT.md`](../PRODUCT.md) |
| Backend architecture and the API contract | [`core/backend-spec.md`](core/backend-spec.md) |
| Build commands, module map, definition of done | [`../CLAUDE.md`](../CLAUDE.md) |

---

## Layout

```
docs/
├── README.md              # this index
├── BETA_LAUNCH_PLAN.md    # beta roadmap (target date lapsed; see its banner)
├── core/                  # specifications and API contract
├── status/                # PROJECT_STATUS.md + historical phase summaries
└── features/              # feature specifications
```

### `core/` — specifications

- **`backend-spec.md`** — core engine architecture, REST + WebSocket contract,
  database schema, accessibility algorithms. Authoritative for the API.
- **`frontend-contract.md`** — what the UI and the core engine agree on: API→UI
  mapping, error and empty states, accessibility criteria, canvas and waterfall
  requirements, documented auto-detect failure rates, Operating Conditions
  requirements, and the 1280×720 no-scroll floor. Cited by shipped source code, so
  section numbers are stable. Replaced `frontend-spec.md` on 2026-08-21.
- **`TRANSMIT_SPEC.md`** — transmit pipeline: image preprocessing, callsign overlay,
  PTT control, audio encoding.
- **`openapi.json`** — exported OpenAPI schema. Regenerate with
  `scripts/export_api_docs.py` whenever the API changes.

### `status/`

- **`PROJECT_STATUS.md`** — ⭐ current truth. Start here.
- **`PHASE[1-5]_IMPLEMENTATION_SUMMARY.md`** — historical completion reports. They
  record what was believed true when written; **PROJECT_STATUS.md supersedes every
  status claim they make.** Useful for archaeology, not for planning.

### `features/`

- **`CRITICAL_DSP_IMPLEMENTATION.md`** — Hough slant correction, correlation VIS
  detection, bandpass filter, real-time audio levels. All four are implemented.
- **`FSKID_SPECIFICATION.md`** — FSKID (frequency-shift keyed identification).
  Authoritative for the wire format: tones, timing, symbol encoding, checksum.
- **`AUTO_RSV_SPECIFICATION.md`** — automatic signal-report generation.

---

## Removed documentation

**Removed 2026-08-05** — deleted as actively misleading, not merely dated. Each
asserted things the tree contradicts. Recoverable via `git log` if ever needed.

- `design/DESIGN_RATIONALE.md` — described a complete React design system (palette,
  typography, motion, component inventory) as "✅ 100% implemented" and
  "production-ready." None of it was ever built, and its palette contradicted the
  then-current frontend spec §7.1. Its durable content — the hardware/software boundary, why
  AFC and manual sync exist, PTT timing rationale — is now in `PRODUCT.md`.
- `features/V1_FEATURE_LIST.md` — claimed "~50-60% complete", "API not wired to DSP
  (simulation only)", and "✅ UI components exist (CaptureView, TransmitView,
  LogView)". The API is wired; no UI code exists anywhere in this repository.
- `reference/README.md` — indexed four files that no longer exist and listed the API
  wiring, WebSocket events, filesystem integration, and testing as ❌ not working. All
  four ship today.
- `archive/` (`FSKID_IMPLEMENTATION_PLAN.md`, `FSKID_RSV_IMPLEMENTATION_STATUS.md`) —
  January 2026 FSKID planning docs. Deleted after verifying that every wire constant
  they carried (1900/2100 Hz mark/space, 1500 Hz × 300 ms preamble, 2100 Hz × 100 ms
  guard, 22 ms bits, `0x0A`/`0x01` markers, 6-bit symbols with `−0x20` offset and XOR
  checksum) is covered — more completely — by `features/FSKID_SPECIFICATION.md` and by
  the shipped, tested decoder and generator. What they added beyond that was a stale
  task breakdown and a list of modules mixing shipped code with proposals that were
  never built (`decode/signal_analyzer.py`, `decode/rsv_calculator.py`,
  `config/settings.py` — none exist).

**Removed 2026-01-16** — `BACKEND_TASKS.md`, `API_DSP_WIRING_PLAN.md`,
`MAKE_OR_BREAK_FEATURES.md`, and assorted early UX research notes.

---

## Maintenance rules

1. **Status lives in exactly one file.** `PROJECT_STATUS.md`. Do not add completion
   percentages, phase tables, or hour estimates to this index or to any spec — that
   duplication is what rotted twice.
2. **Verify against the tree before writing a status claim.** Run the test suite. Read
   the module. Do not extrapolate from another document, including this one.
3. **Regenerate `openapi.json`** via `scripts/export_api_docs.py` on any API change.
4. **Visual direction is undecided.** Do not reintroduce palettes, typography, or
   design tokens into these specs. `PRODUCT.md` records the visual world as an open
   decision, to be settled deliberately when UI work begins.
