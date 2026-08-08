# Backend Audit Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix every defect found in the 2026-08-07 backend audit so the core engine is honestly prod-ready: real encode, real device routing, real error reporting, real tests.

**Architecture:** Nine small single-purpose PRs to `main`, each independently green. Every fix lands with a test that fails before and passes after; the encoder PR adds a permanent gradient-roundtrip CI gate that makes the whole class of "green suite, broken DSP" lies impossible to reintroduce.

**Tech Stack:** Python 3.12, numpy/scipy DSP, FastAPI, SQLAlchemy 2.0, pytest; uv from `sstv_core/`.

## Global Constraints

- All commands run from `sstv_core/`. Done = `uv run pytest` (full suite), `uv run ruff check src/`, `uv run mypy src/` clean for touched files.
- API-contract changes regenerate `docs/core/backend-spec.md` / `docs/core/openapi.json` via `scripts/export_api_docs.py`.
- One concern per PR; semantic commit subjects `fix(scope): summary`; branch per PR; merge via `gh pr`.
- Never store image blobs in DB. Error messages use SSTeVe voice (first person, contractions, `suggested_action`).
- Orphaned-but-future modules (FSKID, audio_guidance, SlantDetector) are NOT wired in this remediation — product decision deferred; only actively-harmful dead code is deleted.

---

### Task 1 (PR 1): Phase-continuous encoders + gradient roundtrip gate

**Files:**
- Modify: `src/sstv_core/encode/scottie_encoder.py` (`_generate_tone`, `_phase` semantics)
- Modify: `src/sstv_core/encode/martin_encoder.py` (same)
- Modify: `src/sstv_core/encode/robot_encoder.py` (same)
- Test: `tests/integration/test_roundtrip_gradient.py` (new)

**Interfaces:** `_generate_tone(freq, num_samples) -> np.ndarray` keeps its signature; `self._phase` becomes accumulated phase in RADIANS (float, wrapped mod 2π), advanced by `2π·freq·num_samples/sample_rate`.

- [ ] Step 1: Write failing test: for each of the three encoders, encode one all-gradient image (every pixel differs from its neighbor), assert `max(abs(diff(audio))) < 0.30` (a pure ≤2300 Hz tone at 0.8 amplitude at 48 kHz can never exceed ~0.24 sample-to-sample; clicks exceed 1.0), AND full roundtrip: encode gradient test card → demodulate each channel via the existing per-mode decoder `decode_stream` on synthetic sync positions → per-channel correlation vs source ≥ 0.95.
- [ ] Step 2: Run it, verify it fails on max-diff (current measured 1.594) for all three encoders.
- [ ] Step 3: Implement radian phase accumulator in each `_generate_tone`:
  ```python
  def _generate_tone(self, freq: float, num_samples: int) -> np.ndarray:
      step = 2.0 * np.pi * freq / self._config.sample_rate
      phases = self._phase + step * np.arange(1, num_samples + 1)
      samples = (np.sin(phases) * 0.8).astype(np.float32)
      self._phase = float(phases[-1] % (2.0 * np.pi)) if num_samples else self._phase
      return samples
  ```
  Reset sites that set `_phase = 0.0` stay valid (radians zero == samples zero at start).
- [ ] Step 4: Full suite + ruff + mypy green.
- [ ] Step 5: Branch `fix/encoder-phase-continuity`, commit `fix(encode): phase-continuous tone synthesis; gradient roundtrip CI gate`, PR, merge.

### Task 2 (PR 2): Honest CLI — real auto-detect on --file, real encode, working console scripts

**Files:**
- Modify: `src/sstv_core/cli/main.py` (`cmd_decode` file path ~lines 160-200, `cmd_encode` ~lines 300-360, dead else-branch 129-137, `cv2.imwrite` check ~269)
- Modify: `pyproject.toml:51-52` (console scripts)
- Test: `tests/cli/test_cli_decode_autodetect.py`, `tests/cli/test_cli_encode.py` (new)

**Interfaces:** file decode uses `CorrelationVISDetector` (from `sstv_core.decode.correlation_vis_detector`) on the WAV's opening seconds to choose the decoder when `--mode` is absent; falls back to honest error (exit 2, `suggested_action: pass --mode`) when VIS not found. `cmd_encode` gains `--output` (WAV path); with `--device` it transmits via `TXManager`; fabricated event stream deleted.

- [ ] Step 1: Failing tests: (a) decode MartinM1 WAV without `--mode` → decoded mode logged as MartinM1 and channel order correct (reuse gradient card, assert color-bar region correlation ≥0.9 against source); (b) `encode --image x.png --output out.wav` writes a WAV whose duration matches the mode spec ±1% and which round-trips through file decode; (c) `encode` with neither `--output` nor working device exits nonzero with no `transmit_complete` event; (d) `python -c "from sstv_core.cli import decode, encode"` — entry-point targets exist.
- [ ] Step 2: Verify fails (auto-detect currently hardcodes ScottieS1; encode fabricates success).
- [ ] Step 3: Implement: VIS detection over the first ~3 s of file samples via `CorrelationVISDetector.detect(...)`; map VIS mode name into the existing `decoders` registry. Rewrite `cmd_encode`: load image (cv2), resize to mode dims, encoder `encode_image`, then `--output` → WAV write (int16), else device → `TXManager` with `PTTController(method="vox")` default. Export `decode`/`encode` thin wrappers in `sstv_core/cli/__init__.py` that parse sys.argv via `main` with the subcommand prefilled; point pyproject at them.
- [ ] Step 4: Suite + ruff + mypy green.
- [ ] Step 5: Branch `fix/cli-honesty`, commit `fix(cli): real auto-detect for --file, real encode, working console scripts`, PR, merge.

### Task 3 (PR 3): dsp_manager truth — device routing, config-driven TX, honest failures, mode gating

**Files:**
- Modify: `src/sstv_core/api/dsp_manager.py` (`:116`, `:247` device mapping; `start_transmit` config read; `_handle_decode_complete` error propagation; decode mode gate)
- Modify: `src/sstv_core/decode/rx_manager.py:449-456` (stop swallowing: return error info / re-raise non-cancel errors)
- Modify: `src/sstv_core/api/routes/decode.py` (400 for modes without decoders)
- Test: `tests/api/test_dsp_manager_real.py` (new — real DSPManager, mocked hardware only at the sounddevice boundary)
- Modify: `tests/conftest.py` (autouse DSP mock stays for legacy route tests, but new test module opts out via fixture override)

**Interfaces:** `DSPManager._resolve_device_index(device_id: str | None) -> int | None` calls `AudioDeviceManager.get_device_index()`; unknown ID raises `ValueError` → route 400. `start_transmit` reads `ConfigManager` (ptt_method, ptt_serial_port, ptt_serial_signal, pre/post delays) via its injected session factory. `rx_manager.receive` returns `None` only on cancel/timeout; decode errors propagate so `_handle_decode_complete` sets state FAILED and emits the error WS event with SSTeVe-voice message.

- [ ] Step 1: Failing tests: (a) `_resolve_device_index("ca_Foo")` returns the index device_manager maps, `int`-string still works, garbage raises; (b) `start_transmit` constructs PTTController with configured DTR signal + delays (assert via monkeypatched PTTController capturing kwargs); (c) decode session whose RXManager raises reports state `failed` and emits error event; (d) `POST /decode/start` with `mode="PD90"` → 400 naming the three supported modes.
- [ ] Step 2: Verify all fail.
- [ ] Step 3: Implement per Interfaces above.
- [ ] Step 4: Suite + ruff + mypy; regenerate API docs (error responses/modes documented).
- [ ] Step 5: Branch `fix/dsp-manager-seams`, commit `fix(api): route device IDs, read PTT config, report decode failures honestly, gate unsupported modes`, PR, merge.

### Task 4 (PR 4): RF safety — cancel unkeys, VOX preamble is audible, no open-glitch

**Files:**
- Modify: `src/sstv_core/encode/tx_manager.py` (`transmit` gains try/finally → `_cleanup()`; CancelledError path)
- Modify: `src/sstv_core/audio/ptt_controller.py` (`generate_vox_preamble` → real tone; `_open_serial` constructs unopened with rts/dtr False then opens)
- Test: extend `tests/encode/test_tx_manager_regressions.py` (mid-flight cancel), `tests/test_audio.py` (preamble non-silence — replaces the asserts-zeros test), new serial-open-order test with a recording fake Serial.

**Interfaces:** `generate_vox_preamble()` returns a 1900 Hz tone at 0.5 amplitude for `vox_preamble_ms` (VOX trip tone at the SSTV leader frequency); `transmit()` guarantees `unkey_radio()` + stream stop via `finally` even on `asyncio.CancelledError` (re-raised after cleanup).

- [ ] Step 1: Failing tests: (a) start transmit, `task.cancel()` mid-wait, assert PTT unkeyed and output stream stopped; (b) preamble RMS > 0.1; (c) fake `serial.Serial` records that rts=False/dtr=False are set before `open()`.
- [ ] Step 2: Verify fails (cancel currently leaves keyed; preamble zeros; open-glitch).
- [ ] Step 3: Implement.
- [ ] Step 4: Suite + ruff + mypy green.
- [ ] Step 5: Branch `fix/rf-safety`, commit `fix(audio): unkey on cancel, audible VOX preamble, glitch-free serial open`, PR, merge.

### Task 4b (PR 4b): Audio pipeline hygiene

**Files:**
- Modify: `src/sstv_core/decode/rx_manager.py` (apply `BandpassFilter` once, to the decode loop's samples; VIS loop stops double-filtering — correlation detector already filters internally, so rx_manager's pre-filter moves to the decode phase only; audio_levels attached to per-line progress events at ≤10 Hz)
- Modify: `src/sstv_core/audio/ring_buffer.py` (overflow counter: track samples dropped by maxlen eviction, expose `dropped_samples`, log warning once per burst)
- Modify: `src/sstv_core/audio/device_manager.py:125-137` (Darwin/Windows IDs get `_<index>` suffix on collision so duplicate hardware stays addressable)
- Modify: `src/sstv_core/api/dsp_manager.py:751` (module-level singleton constructs `AudioDeviceManager` lazily on first use, not at import)
- Modify: `src/sstv_core/audio/stream_manager.py:197,242` (also catch `ValueError` from sounddevice → `AudioStreamError`)
- Modify: `src/sstv_core/audio/bandpass_filter.py:123-142` (delete dither add/remove pseudo-science; filter output returned as-is)
- Modify: `src/sstv_core/config/manager.py:61` (delete dead `sample_rate_override` knob)
- Test: extend `tests/audio/test_bandpass_filter.py`, `tests/test_audio.py`; new `tests/audio/test_device_ids.py`

- [ ] Step 1: Failing tests: (a) decode-loop samples pass through bandpass exactly once (spy on filter); (b) ring buffer overflow increments `dropped_samples`; (c) two devices named "USB Audio" → distinct IDs, both resolvable; (d) `import sstv_core.api.dsp_manager` with sounddevice raising → import succeeds, first use raises `AudioDeviceError`.
- [ ] Step 2: Verify fails.
- [ ] Step 3: Implement.
- [ ] Step 4: Suite + ruff + mypy green.
- [ ] Step 5: Branch `fix/audio-hygiene`, commit `fix(audio): filter decode path once, surface buffer overflow, collision-proof device IDs, lazy hardware init`, PR, merge.

### Task 5 (PR 5): One WebSocket contract

**Files:**
- Modify: `src/sstv_core/api/dsp_manager.py` (all `_emit`/broadcast payloads → `models.py` event models: `event_type`, spec'd fields, real timestamp, decode_complete carries mode/snr; populate `snr_db` metadata for status route)
- Modify: `src/sstv_core/api/models.py` (only where the model demands data that cannot exist — make `vis_code` optional with reason)
- Modify: `src/sstv_core/api/websocket_manager.py:109-131` (snapshot connections under lock, send outside it)
- Modify: `docs/core/backend-spec.md` WS section via `scripts/export_api_docs.py` + hand-align event table
- Test: `tests/api/test_ws_event_contract.py` (new — every emitted payload validates against its models.py model)

**Interfaces:** emitters build payloads by instantiating the models (`ScanlineUpdateEvent`, `VISDetectedEvent`, `DecodeCompleteEvent`, …) and `.model_dump()`; clients get exactly the models.py shape. `DecodeStatusResponse.snr_db` fed from rx signal_quality mapping.

- [ ] Step 1: Failing test: capture broadcasts from a real DSPManager decode run (fake stream feeding the ScottieS1 reference WAV), validate each against its model; assert `timestamp != 0`; assert broadcast doesn't hold the manager lock during a stalled client send (slow fake connection, second client still receives within tolerance).
- [ ] Step 2: Verify fails (current `"event"` shape, timestamp 0, lock held).
- [ ] Step 3: Implement.
- [ ] Step 4: Suite + ruff + mypy; regenerate docs.
- [ ] Step 5: Branch `fix/ws-contract`, commit `fix(api): emit spec-shaped WebSocket events; don't serialize broadcasts behind one slow client`, PR, merge.

### Task 6 (PR 6): Smart features that do what they say

**Files:**
- Modify: `src/sstv_core/smart_features/mode_detector.py:16-28` (import and use `sync_detector.MODE_TIMINGS` line periods; drop duplicate table; distinct PD entries or drop unlisted-decoder modes)
- Modify: `src/sstv_core/smart_features/device_detector.py` (`recommended_serial_port` as its own field; Digirig VID/PID → CP2102N 0x10C4/0xEA60 per Digirig docs; `get_recommended_settings` emits `ptt_serial_port`, never audio fields)
- Modify: `src/sstv_core/api/routes/devices.py` (apply_settings normalizes `serial_rts`/`serial_dtr` → `serial` + signal, same as config routes)
- Modify: `src/sstv_core/smart_features/field_populator.py:63-82` (parenthesize/fix fallback chain; use real columns `rx_snr_db`, drop phantom `station_callsign`/`default_frequency_hz` tiers or read existing config keys)
- Create: `templates/smart_reply/qsl_card_base.png`, `monitor_frame_base.png`, `minimal_badge_base.png` (generated 320×256 PNGs, committed)
- Create: `scripts/generate_template_bases.py` (the generator, for regeneration)
- Test: `tests/smart_features/test_mode_detector.py`, `test_device_detector.py`, `test_field_populator.py`, `tests/smart_features/test_template_engine_loads.py` (all new)

**Interfaces:** `detect_mode_from_sync_timing(intervals_ms)` unchanged signature, correct table. `get_recommended_settings` returns only keys `ConfigManager.update` accepts (verified in test by actually calling it).

- [ ] Step 1: Failing tests: (a) synthetic 428.22 ms intervals → `("ScottieS1", ≥0.85)`; 446.446 → MartinM1; 150 → Robot36; (b) `ConfigManager.update(get_recommended_settings(digirig))` succeeds against a real scratch DB; (c) field_populator: image with `frequency_hz` + override → override wins; `rx_snr_db` → `snr_db`; (d) `TemplateEngine(...)` loads 3 templates and `render_template` produces an image.
- [ ] Step 2: Verify fails.
- [ ] Step 3: Implement; generate the three base PNGs (simple branded frames via PIL: border, callsign/field text zones per each JSON's coordinates).
- [ ] Step 4: Suite + ruff + mypy green.
- [ ] Step 5: Branch `fix/smart-features-real`, commit `fix(smart): correct mode timing table, applyable device profiles, real template bases, honest field fallbacks`, PR, merge.

### Task 7 (PR 7): Filesystem truth — watcher imports, dead code out, own files import cleanly

**Files:**
- Modify: `src/sstv_core/filesystem/watcher.py:100-113` (`_handle_modified` with no DB row delegates to import; debounce keeps latest event but resolves create-vs-update at fire time by DB lookup, not event type)
- Modify: `tests/filesystem/test_watcher.py:132` (supersede test now asserts the import still happens)
- Delete: `ImageSaver.save_with_metadata` (`src/sstv_core/decode/image_saver.py:149-202`) — broken, zero callers
- Modify: `src/sstv_core/filesystem/importer.py:122` (also accept SSTeVe's own `sstv_rx_MODE_YYYYMMDD_HHMMSS` naming)
- Test: extend `tests/filesystem/test_watcher.py` with the real-Observer end-to-end from the audit (tmp dir + file SQLite → row exists)

- [ ] Step 1: Failing tests: (a) end-to-end: write image into watched dir, wait past debounce, assert DB row exists (currently 0 rows); (b) importer parses `sstv_rx_ScottieS1_20260807_120000.png` → mode ScottieS1.
- [ ] Step 2: Verify fails.
- [ ] Step 3: Implement; delete dead method and its absent tests.
- [ ] Step 4: Suite + ruff + mypy green.
- [ ] Step 5: Branch `fix/watcher-imports`, commit `fix(filesystem): watcher actually imports new images; accept own filename convention; drop broken dead save_with_metadata`, PR, merge.

### Task 8 (PR 8): Test-suite hygiene + migration path + dead simulator removal

**Files:**
- Modify: `tests/conftest.py` (session-scoped autouse fixture sets `SSTVE_DB_PATH` to a tmp file before any app import)
- Modify: `src/sstv_core/database/models.py` `init_database` (after `create_all`, stamp `alembic_version` at head via `alembic.command.stamp` with programmatic Config)
- Delete: `src/sstv_core/api/operation_manager.py`, `tests/api/test_operation_manager.py`; remove `main.py:133` reference
- Test: `tests/test_migration_path.py` (new): create DB via `init_database`, run `alembic upgrade head` → succeeds (no-op); fresh empty DB via alembic alone → same schema as create_all (PRAGMA diff already proven equal)

- [ ] Step 1: Failing tests: (a) upgrade-after-create_all currently raises OperationalError; (b) grep-style assertion that running the suite never touches `Path.home()/".ssteve"` (fixture asserts the env var is set and points into tmp).
- [ ] Step 2: Verify fails.
- [ ] Step 3: Implement; delete simulator; fix any import fallout.
- [ ] Step 4: Suite + ruff + mypy green.
- [ ] Step 5: Branch `fix/test-and-migration-hygiene`, commit `fix(db,tests): stamp alembic on init, isolate test DB from ~/.ssteve, remove dead synthetic simulator`, PR, merge.

### Task 9 (PR 9): API coherence — image IDs bridge, honest data, no event-loop stalls

**Files:**
- Modify: `src/sstv_core/api/routes/qso.py`, `smart_reply.py` (accept the public UUID `image_id`; resolve via shared helper)
- Create: `src/sstv_core/api/image_lookup.py` (`resolve_image_uuid(session, uuid) -> SSTVImage | None` — single query over ids mapped through `db_image_id_to_uuid`; fine at this scale, one place to optimize later)
- Modify: `src/sstv_core/api/routes/images.py` (drop fabricated 320×256 dims → nullable; stop mapping `frequency_hz` into `frequency_offset_hz`; reuse lookup helper at `:149-153`)
- Modify: `src/sstv_core/api/routes/decode.py:104,130-156` (`sf.read` + Goertzel analysis via `run_in_executor`)
- Modify: `src/sstv_core/api/routes/transmit.py:150-151` (unknown mode → error detail, not fabricated MartinM1); `websocket_url` built from request base
- Modify: `src/sstv_core/api/routes/smart_reply.py:291-304` (transmit preview → create a REAL transmit session via session_manager + dsp_manager path, or 501 with SSTeVe-voice detail if rendering-to-file only; implement the real path — render template to temp image file, then same flow as `POST /transmit`)
- Modify: `src/sstv_core/api/models.py` + `config/manager.py:118` (Wraase spelling aligned; `include_vis`/`callsign` either honored by TXManager passthrough or removed from `TransmitRequest` — remove `include_vis` (encoders always need VIS), thread `callsign` through to image_preprocessor overlay which exists)
- Modify: `src/sstv_core/api/main.py:331` (`reload=False`)
- Test: `tests/api/test_image_id_bridge.py`, `tests/api/test_smart_reply_transmit_real.py` (new)

- [ ] Step 1: Failing tests: (a) decode-created image's public UUID accepted by `POST /qso/log` and `POST /smart_reply/generate`; (b) smart_reply transmit creates a real session (half-duplex 409 when decode active) and `GET /transmit/status/{tx_id}` returns it; (c) transmit with callsign → preprocessor overlay called.
- [ ] Step 2: Verify fails.
- [ ] Step 3: Implement.
- [ ] Step 4: Suite + ruff + mypy; regenerate `docs/core/openapi.json` + backend-spec (ID types changed — breaking-change note in spec header).
- [ ] Step 5: Branch `fix/api-coherence`, commit `fix(api): bridge public image IDs, real smart-reply transmit, no fabricated data, off-loop file IO`, PR, merge.

### Task 10: Final verification + status docs

- [ ] Full suite, ruff, mypy from clean checkout of `main`.
- [ ] Re-run the audit's ground-truth loop: encode gradient card per mode → CLI file decode (auto-detect, no --mode) → correlation ≥0.95 all three modes.
- [ ] Boot `sstv-server`, smoke: health, devices, config, decode/start with bogus device → honest 4xx/failed (not silent stop).
- [ ] Update `docs/status/PROJECT_STATUS.md`: what the audit found, what's now fixed, what remains deliberately unwired (FSKID, audio_guidance, SlantDetector) as product decisions.
- [ ] Commit `docs(status): record audit remediation` via PR.
