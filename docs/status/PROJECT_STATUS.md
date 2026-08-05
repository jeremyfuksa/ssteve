# SSTeVe Project Status

**Last Updated:** 2026-08-05 (full re-baseline, verified against code and CI — not extrapolated from prior status docs)
**Current Focus:** Backend hardening complete; next work is the session-based mode-detection stub and the desktop shell.

---

## Executive Summary

The backend core is feature-complete for the beta scope and fully green:

- **Tests:** 444 passing, zero exclusions. CI runs the entire suite plus `ruff check src/` and `mypy src/` (both clean, enforced as gates since PR #14).
- **PR #13** landed the long-uncommitted correctness pass: removed the conftest decoder fakes and fixed the real bugs they masked (TX mode/encoder mismatch, ring-buffer re-reads, FSKID tone aliasing and discarded checksum, phantom half-duplex lock, three routers on stub DB dependencies, non-UUID image ids on WebSocket events).
- **PR #14** zeroed ruff (1,205 → 0) and mypy (93 → 0) debt and fixed four runtime crashes the type gate surfaced (decode-start progress emission, decoded-image save call, serial-PTT constructor kwarg, DB-disabled mode crash).
- **PR #15** made the image-library watcher actually work: WebSocket library events are now delivered across threads (`run_coroutine_threadsafe`; they previously never reached clients), the watcher starts from the `image_save_directory` config key instead of an unset env var, `soundfile` became a declared dependency (detect_mode 500'd without it), and 56 tests were backfilled for the watcher and the previously untested import/detect_mode/apply_settings endpoints.

## What Works (verified by the test suite)

- Full RX pipeline: bandpass → correlation VIS detection → per-mode decode (Scottie S1, Martin M1, Robot 36) → Hough slant correction → save → DB record → WebSocket events (VIS, scanlines, audio levels at 10 Hz, completion).
- Full TX pipeline: mode→encoder mapping (Scottie/Martin/Robot), VIS + FSKID generation, non-truncating playback, serial/VOX PTT with pre/post delays.
- FSKID decode: physical-tone Goertzel bins, post-end-marker checksum handling.
- API layer: decode, transmit, devices (including `apply_settings`), config, images, QSO, smart replies, MMSSTV import (`/import/mmsstv`, `/validate`, `/preview`), mode detection (`/decode/detect_mode`, file-based), WebSocket manager, half-duplex session management with failure cleanup.
- Filesystem: library watcher (debounced, config-driven, cross-thread event delivery), image importer, MMSSTV importer.
- Smart features, accessibility modules, CLI, database schema/migrations.

## Known Gaps

1. **Session-based mode detection is stubbed** — `POST /decode/detect_mode` with a `session_id` returns `SESSION_ANALYSIS_NOT_SUPPORTED`; it needs ring-buffer access through the stream manager. File-based detection works.
2. **Watcher default directory is a product decision** — with `image_save_directory` unset (the default), the watcher doesn't start. Decide whether it should default to `~/sstv_images` (where RXManager saves).
3. **`sstv-decode` / `sstv-encode` console scripts are broken** (`pyproject.toml` points at functions that don't exist); use `python -m sstv_core.cli.main`. `sstv-server` works.
4. **`datetime.utcnow()` deprecation warnings** throughout (488 in the test run) — mechanical migration to `datetime.now(UTC)` pending.
5. **Dependabot backlog** — 35 vulnerabilities flagged on the default branch and ~9 open dependency PRs (including starlette 0.50→1.0.1 and transformers 5.0.0rc3, which need care). Not yet triaged.
6. **Desktop shell (`sstv_desktop/`) does not exist** — all "Tauri frontend" items (canvas/waterfall UI, Edit-in-Default-App, drag-and-drop, settings UI) are unstarted. The backend REST/WebSocket contract they build on is done.
7. Deferred by design: AI captioning, multi-receiver, full-duplex.

## Where Things Live

- Backend spec / API contract: `docs/core/backend-spec.md`, `docs/core/openapi.json` (regenerate with `scripts/export_api_docs.py` — now writes the canonical path).
- Definition of done, commands, module map: `CLAUDE.md` (rewritten; the known-failures list is gone because there are none).
- Phase summaries under `docs/status/PHASE*_IMPLEMENTATION_SUMMARY.md` are historical records; this file supersedes their status claims.

---

**Caution for future updates:** this repo's status docs have twice drifted badly from the code (features marked "not implemented" that were done and wired). Verify against the tree and the test suite before scheduling work from any planning doc, this one included.
