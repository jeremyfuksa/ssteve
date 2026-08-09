# SSTeVe Project Status

**Last Updated:** 2026-08-09 (documentation reconciliation, #70; every claim verified by measurement, not extrapolated)
**Current Focus:** Backend complete for beta scope. Next epoch: the desktop shell (`sstv_desktop/` is still empty; the REST/WebSocket contract it builds on is done and honest).

---

## Executive Summary

Two remediation rounds landed back to back:

1. **Audit remediation (2026-08-07, PRs #26–#37):** a full adversarial audit
   found the green suite was structurally blind and ~20 BLOCKS-PROD defects
   ("the backend was a lie"); all were fixed the same day. Record:
   `docs/superpowers/plans/2026-08-07-backend-audit-remediation.md`.
2. **Known-gaps remediation (2026-08-08, PRs #38–#47 + this one):** every
   buildable item on the previous Known Gaps list closed. Record:
   `docs/superpowers/plans/2026-08-08-known-gaps-remediation.md`.

**Ground truth** (CLI `encode --output` → file decode with VIS auto-detect,
gradient card): ScottieS1 **0.9999** / MartinM1 **0.9999** / Robot36 **0.9978**
overall correlation. (Audit-day baseline: 0.70 / 0.15 / 0.04.)

Reproduced by `tests/cli/test_cli_file_roundtrip.py::test_file_roundtrip_per_mode_via_vis_autodetect`,
which prints each figure on `-s`; measured 2026-08-09. The earlier Robot36
headline of 0.96 predated that test and understated the real number — no test
reproduced it, so it could not be checked.

- **Tests:** 569 passing, zero exclusions; ruff + mypy clean; CI green on `main`.
  (Milestone-1 PRs in flight add coverage on top of this: #75, #76, #77, #78.)
- Suite deprecation warnings: **1** (down from ~490), and it is third-party
  (starlette's TestClient/httpx notice). The project's own `datetime.utcnow()`
  calls in `tests/` were migrated 2026-08-09 — PR #47 had covered `src/` only —
  and the unregistered `pytest.mark.integration` is now declared in `pytest.ini`.
- Dependabot: scanning enabled, **0 open alerts** — all 35 from the
  2026-08-05 baseline are state *fixed* via landed dependency updates;
  0 open dependency PRs. (Verified via the GitHub API 2026-08-08.)

## What landed in the known-gaps round (PRs #38–#47)

- **Auto-RSV + measured SNR** (#38): the decode pipeline measures noise
  floor, peak, SNR, sync jitter, and per-line confidence; RSV reports
  (spec: `docs/features/AUTO_RSV_SPECIFICATION.md`) and the January
  `rx_snr_db`/`rsv_*` columns are now populated. Live SNR feeds scanline
  WS events and decode status.
- **AFC + squelch consumed** (#39/#40): sync pulses are 1200 Hz references —
  measured offset (median of 3, clamped to `afc_range_hz`) shifts the video
  mapping when `auto_afc`; verified on a heterodyne-shifted +60 Hz signal.
  `auto_squelch` gates VIS processing below `squelch_threshold_db`. Manual
  overrides preserved (Doppler/contest constraints).
- **FSKID wired both directions** (#41): TX appends the MMSSTV-compatible ID
  when a callsign is given; RX decodes it from the post-image tail and
  populates the `fskid_*` columns (callsign adopted only when
  checksum-valid and not operator-supplied).
- **Session-based mode detection** (#42): the stub is gone; a rolling 15 s
  raw-audio window per session feeds the sync-timing detector.
- **CLI live-device decode** (#43): `decode --device` runs the real RX
  pipeline — and the first end-to-end live test found and fixed two real
  bugs: the final scanline never completed (silence follows a
  transmission), and Robot36's `get_image()` returned a never-built RGB
  buffer on the live path (all-black images).
- **Audio guidance wired** (#44): lock chime on VIS, double chime on
  completion, via local output when `stereo_guidance_enabled` (default
  off). Playback failure never fails a decode.
- **Orphans deleted** (#45): the redundant `SlantDetector` class and
  `AudioTransmitter` (`SlantErrorData` survives; Hough is the wired slant
  corrector, off by default with measured rationale).
- **One image directory** (#46): `image_save_directory` defaults to
  `~/.ssteve/images`; the decoder saves into the configured directory and
  the watcher watches the same one. Empty string = watcher opt-out.
- **Timezone-aware datetimes** (#47): DB stays naive-UTC (matching stored
  rows), events/WS timestamps carry `+00:00`, session bookkeeping aware
  end-to-end.

## What Works (verified end-to-end)

- Encode→decode roundtrip on gradient content, all three modes, VIS
  auto-detected (numbers above).
- Live-path decode: real transmission through the real ring buffer at
  live pacing → ≥0.9 correlation (automated test).
- Honest failures everywhere exercised: bad device, unsupported mode,
  no-signal timeout, not-enough-audio session analysis.
- Half-duplex sessions, config persistence, QSO logging (public UUID
  bridge), Smart Reply generate/transmit, MMSSTV import, watcher
  auto-import, FSKID, RSV, AFC, squelch, guidance.

## Remaining

The 2026-08-08 pre-frontend review opened Milestone 1 ("Pre-hardware fixes"),
so buildable work *is* open — this heading previously read "nothing buildable
is open," which stopped being true the moment those issues were filed. Track
them in GitHub Milestone 1; two are blocked rather than buildable:

- **#52 `image_library_path` validator** — blocked on a product decision
  (enforce home-containment, or accept arbitrary absolute paths and drop the
  misleading docstring).
- **#73 Digirig VID/PID** — blocked on physical hardware; see below.

1. **Digirig VID/PID hardware verification** — the profile uses CP2102N
   0x10C4/0xEA60 per digirig.net. With the unit plugged in, run
   `uv run python scripts/verify_device_profiles.py` from `sstv_core/`; it
   compares every profile's VID/PID against attached hardware and exits 0
   (confirmed), 1 (contradicted — fix the profile), or 2 (nothing attached).
2. **Desktop shell** (`sstv_desktop/`) — unstarted by design; see
   `PRODUCT.md` and `DESIGN.md` before any UI work.
3. Deferred by design: AI captioning, multi-receiver, full-duplex, PD/
   Wraase/Scottie-S2-DX decoder implementations (the API 400s them
   honestly), calibrated-SNR refinement beyond the peak/floor estimate.

## Where Things Live

- Backend spec / API contract: `docs/core/backend-spec.md`,
  `docs/core/openapi.json` (regenerate with `scripts/export_api_docs.py`).
- Remediation records: `docs/superpowers/plans/2026-08-07-*.md` and
  `2026-08-08-*.md`.
- Definition of done, commands, module map: `CLAUDE.md`. The gradient
  roundtrip gate (`tests/integration/test_roundtrip_gradient.py`) is the
  regression canary — never skip it.
- Phase summaries under `docs/status/PHASE*_IMPLEMENTATION_SUMMARY.md` are
  historical records; this file supersedes their status claims.
