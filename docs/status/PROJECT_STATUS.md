# SSTeVe Project Status

**Last Updated:** 2026-08-07 (post audit-remediation; every claim below verified by measurement in that session, not extrapolated)
**Current Focus:** Backend remediation complete (PRs #26–#36). Next work: session-based mode detection, desktop shell, and the deliberate deferrals listed below.

---

## Executive Summary

On 2026-08-07 a full adversarial audit (four subsystem readers + a measured
encode→decode roundtrip) found that the previous "fully green" status was
misleading: the suite passed while the encoder emitted broken audio, device
selection was a no-op, and several features were fabrications. All findings
were remediated the same day in eleven PRs (#26–#36). The audit report and
remediation plan live in `docs/superpowers/plans/2026-08-07-backend-audit-remediation.md`.

**Ground truth after remediation** (CLI `encode --output` → file decode with
VIS auto-detection, gradient test card): ScottieS1 1.000 / MartinM1 1.000 /
Robot36 0.96 channel correlation. Before: 0.70 / 0.15 / 0.04.

- **Tests:** 546 passing, zero exclusions; `ruff check src/` and `mypy src/` clean; CI green on `main`.
- The suite is no longer structurally blind: a gradient roundtrip gate
  (`tests/integration/test_roundtrip_gradient.py`) fails on any encoder or
  sync regression; DSPManager, smart features, the watcher, and the
  WebSocket contract now have real (non-mock-asserting-mock) tests; `pytest`
  can no longer touch `~/.ssteve`.

## What was fixed (PRs #26–#36, all measured)

- **Encoders** (#26): phase now accumulates in radians — gradient content
  (i.e. photographs) previously produced a full-scale click at every pixel
  boundary and decoded as noise. Sync windows overlap so Martin's 4.862 ms
  pulse can't fall between blocks (~6% of scanlines were silently dropped).
- **CLI** (#27): `--file` decode auto-detects from VIS (was hardcoded
  ScottieS1); `encode` really encodes to WAV or transmits (was a fabricated
  event stream); `sstv-decode`/`sstv-encode` console scripts work.
- **API↔DSP seam** (#28): device IDs actually route (every real ID silently
  fell back to the default device); transmit reads saved PTT config
  (DTR-keyed rigs could never key); decode failures report `failed` + error
  event (were silent "stopped"); unsupported modes 400 up front.
- **RF safety** (#29): cancelling a transmission unkeys the radio (was a
  dead-key); VOX preamble is a 1900 Hz tone (was silence, which can't trip
  VOX); serial open no longer key-glitches; transmissions carry exactly one
  VIS header (was two).
- **Audio hygiene** (#30/#31): bandpass applied once, on the decode path
  (was twice on VIS, never on decode); ring-buffer overflow fails loudly
  instead of silently corrupting the timeline; duplicate identical hardware
  gets addressable device IDs; no PortAudio at import on headless boxes.
- **WebSocket contract** (#32): one contract — the models.py event models —
  emitted everywhere (three incompatible shapes coexisted; no client could
  parse the real stream). Unmeasurable fields are honestly null, not
  fabricated. Broadcasts aren't serialized behind one slow client.
- **Smart features** (#33): mode detection uses real line periods (the old
  table made Scottie/Martin/PD undetectable in principle); Smart Reply's
  three template base images exist (zero templates loaded before); detected
  device profiles apply cleanly (always 400'd before); field population
  honors overrides and reads the real dB column.
- **Filesystem** (#34): the watcher actually imports new files (created
  event was superseded by modified, which dropped unknown files — measured
  0 rows imported); it recognizes SSTeVe's own output filenames.
- **DB/test hygiene** (#35): `alembic upgrade head` works on app-created
  databases (init stamps head); the 447-line dead synthetic-data simulator
  and its green tests are gone.
- **API coherence** (#36): QSO/Smart Reply accept the public image UUIDs
  the API actually exposes (they demanded raw DB keys no endpoint
  returned); Smart Reply transmit is a real half-duplex session (was an
  admitted mock); fabricated dims/modes/SNR removed; `callsign` is really
  overlaid on transmitted images; blocking file IO moved off the event loop.

## What Works (verified end-to-end this session)

- Encode→decode roundtrip on gradient content, all three modes, with VIS
  auto-detection (numbers above).
- Server boots and serves real data; bad device / unsupported mode return
  honest SSTeVe-voice 400s (exercised live via curl).
- Half-duplex session management, config persistence, QSO logging, Smart
  Reply generate/transmit, MMSSTV import, watcher auto-import.

## Known Gaps

1. **Session-based mode detection is stubbed** — `POST /decode/detect_mode`
   with a `session_id` still returns `SESSION_ANALYSIS_NOT_SUPPORTED`;
   file-based detection works.
2. **CLI live-device decode is not wired** — `decode --device` fails
   honestly (exit 2) and points at `--file`. The API path does live decode.
3. **No calibrated SNR measurement exists.** `snr_db` fields are honestly
   null everywhere until the engine truly measures it (rx_snr_db is
   populated only by the FSKID/RSV path when that runs).
4. **Deliberately unwired modules** (product decisions, not defects —
   the code is real but nothing invokes it): FSKID encode/decode,
   accessibility audio guidance (stereo sonification), the sync-timing
   SlantDetector (the Hough corrector is the wired one, off by default),
   and `AudioTransmitter` (superseded by TXManager's callback path).
   Decide per-feature: wire or delete.
5. **Auto-AFC/squelch config knobs are stored but not consumed** by the
   decode path — wiring them is feature work, tracked here so the config
   surface doesn't read as implemented.
6. **Digirig VID/PID (CP2102N 0x10C4/0xEA60) is unverified against
   physical hardware** — confirm with `lsusb` on a real unit.
7. **Watcher default directory is a product decision** — with
   `image_save_directory` unset the watcher doesn't start; RXManager saves
   to `~/sstv_images`. Also note `dsp_manager` hardcodes that save path
   rather than reading config — align when the decision lands.
8. `datetime.utcnow()` deprecation warnings (~400) — mechanical migration
   pending. Dependabot backlog untriaged. Desktop shell unstarted.

## Where Things Live

- Backend spec / API contract: `docs/core/backend-spec.md`,
  `docs/core/openapi.json` (regenerate with `scripts/export_api_docs.py`).
  **Breaking change 2026-08-07:** QSO/Smart Reply image IDs are public
  UUIDs; WebSocket events are keyed `event_type` per the models.py shapes;
  `TransmitRequest.include_vis` is gone.
- Audit + remediation plan:
  `docs/superpowers/plans/2026-08-07-backend-audit-remediation.md`.
- Definition of done, commands, module map: `CLAUDE.md`.
- Phase summaries under `docs/status/PHASE*_IMPLEMENTATION_SUMMARY.md` are
  historical records; this file supersedes their status claims.
