# Known Gaps Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every buildable item in PROJECT_STATUS.md "Known Gaps" (post-audit list, 2026-08-07) so the backend has no stored-but-unconsumed config, no stubbed endpoints, and no real-but-orphaned features.

**Architecture:** Ten small single-purpose PRs to `main`, same discipline as the audit remediation (plan 2026-08-07). DSP features follow their specs in `docs/features/`. Each lands with tests that fail before and pass after; suite + ruff + mypy green; CI verified before merge (exit codes checked bare — no pipes).

**Tech Stack:** Python 3.12, numpy/scipy, FastAPI, SQLAlchemy, pytest; uv from `sstv_core/`.

## Global Constraints

- Done = full `uv run pytest`, `uv run ruff check src/`, `uv run mypy src/` — exit codes verified, never piped through tail.
- API changes regenerate `docs/core/openapi.json` via `scripts/export_api_docs.py`.
- Graceful degradation: every auto feature keeps its manual override; confidence gates per CLAUDE.md (≥0.85/0.70).
- OUT OF SCOPE (stated, not silently dropped): Digirig hardware verification (needs a physical unit), Dependabot version upgrades (triage/report only), desktop shell (roadmap, not a gap).

---

### Task 1 (PR G1): Measured signal metrics + Auto-RSV (gap 3)

Per `docs/features/AUTO_RSV_SPECIFICATION.md`.
**Files:** Create `src/sstv_core/decode/rsv.py` (DecodeMetrics, RSVReport, RSVCalculator per spec); Modify `rx_manager.py` (measure noise floor pre-VIS, peak amplitude, snr_db = 20·log10(peak/noise), sync jitter, collect scanline confidences; attach a DecodeMetrics to the completed session); Modify `api/dsp_manager.py` (`_create_image_record` populates rx_snr_db/rx_peak_amplitude/rx_noise_floor/rsv_*/decode_metrics_json; scanline WS events + DecodeStatusResponse carry real snr_db). Test `tests/decode/test_rsv.py` (calculator table-driven per spec S-mapping; metrics measured on synthetic audio with known SNR).

### Task 2 (PR G2): Consume AFC + squelch config (gap 5)

**AFC:** during decode, measure mean instantaneous frequency across detected sync pulse windows (Hilbert demodulator, existing); offset = mean − 1200 Hz, clamped to ±`afc_range_hz`; when `auto_afc`, shift the decoder's black/white/sync frequencies by the offset. Manual override: `auto_afc=false` disables (constraint: satellite/Doppler ops).
**Squelch:** in the VIS-wait loop, when `auto_squelch`, skip VIS processing for chunks whose RMS dB < `squelch_threshold_db`.
**Files:** `rx_manager.py`, `api/dsp_manager.py` (read the four knobs from config and pass to RXManager). Tests: synthetic off-frequency (e.g. +60 Hz) transmission decodes correctly with AFC on and mistints with AFC off; squelch skips noise below threshold and passes signal above.

### Task 3 (PR G3): Wire FSKID, both directions (gap 4a)

Per `docs/features/FSKID_SPECIFICATION.md`: TX appends the FSKID frame after image audio when a callsign is provided; RX feeds post-image audio (~3 s) to FSKIDDecoder after decode completes, storing fskid_detected/confidence/checksum_valid and the callsign on the image record (callsign only when checksum valid).
**Files:** `encode/tx_manager.py`, `decode/rx_manager.py`, `api/dsp_manager.py`. Test: full TX→RX roundtrip — encode with callsign, decode, assert image record carries the callsign via FSKID.

### Task 4 (PR G4): Session-based mode detection (gap 1)

RXManager keeps a rolling raw-audio window (last 15 s) during an active session; DSPManager exposes `get_session_audio(session_id)`; `POST /decode/detect_mode` with `session_id` runs the (now-correct) sync-timing detector on it instead of returning SESSION_ANALYSIS_NOT_SUPPORTED.
**Files:** `rx_manager.py`, `api/dsp_manager.py`, `api/routes/decode.py`. Test: real DSPManager with a fake stream feeding Martin audio; detect_mode(session_id) returns MartinM1.

### Task 5 (PR G5): CLI live-device decode (gap 2)

`decode --device` runs the real pipeline: AudioStreamManager + RXManager.receive via asyncio.run, progress → log events, image saved to `--output`; honest errors preserved for device failures.
**Files:** `cli/main.py`. Test: monkeypatched stream manager feeding WAV samples through the ring buffer; CLI exits 0 and writes the image.

### Task 6 (PR G6): Wire audio guidance (gap 4b)

Accessibility sonification (eyes-free operating situation, PRODUCT.md): when guidance is enabled in config (`get_guidance_config` already exists), decode lifecycle events play the module's existing cues through the output stream — VIS-detected chime, progress ticks, completion chord, error tone. Off by default; TX untouched (half-duplex is radio-side, local speaker is fine).
**Files:** `api/dsp_manager.py` (hooks), `accessibility/audio_guidance.py` (playback adapter), config plumbing. Test: enabled guidance calls the playback adapter on VIS/complete events; disabled never does.

### Task 7 (PR G7): Delete superseded orphans (gap 4c/4d)

`SlantDetector` class (redundant with the wired HoughSlantCorrector; move `SlantErrorData` to the corrector's module) and `AudioTransmitter` (superseded by TXManager's callback path; would corrupt audio if used). Delete modules + their orphan-only tests; fix imports/`__init__` exports.

### Task 8 (PR G8): Watcher default directory + save-path alignment (gap 7)

Decision (recommended default, reversible in config): `image_save_directory` defaults to `~/sstv_images` — where RXManager already saves — so the watcher starts out of the box; `dsp_manager` reads the configured directory for decode saves instead of hardcoding. One directory, watched and written.
**Files:** `config/manager.py`, `api/main.py`, `api/dsp_manager.py`. Tests: default config starts the watcher on ~/sstv_images; configured dir is used by both saver and watcher.

### Task 9 (PR G9): datetime.utcnow migration (gap 8a)

Mechanical sweep: `datetime.utcnow()` → `datetime.now(UTC)` (naive-comparison sites audited as touched). Suite warning count drops accordingly; no behavior change intended.

### Task 10 (PR G10): Status rebaseline + Dependabot triage report

Update PROJECT_STATUS.md Known Gaps (should shrink to: hardware verification, dependency upgrades, desktop shell, session detection nuances if any). Add a triage of the Dependabot backlog (what's safe, what needs care, recommendation) WITHOUT applying upgrades.
