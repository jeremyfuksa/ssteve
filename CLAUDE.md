# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**SSTeVe** is a modern SSTV (Slow-Scan Television) application for amateur radio operators. The repo contains a headless Python core engine (DSP, encode/decode, audio I/O, PTT, FastAPI server) and a placeholder for a future desktop shell.

**Layout:**

- `sstv_core/` — the Python core engine (the only buildable component today)
  - `src/sstv_core/` — package source (src layout)
  - `tests/` — pytest suite; reference audio/images in `tests/reference/{audio,images}/`
  - `scripts/` — utilities (`export_api_docs.py`, `test_websocket.py`)
  - `templates/` — smart-reply templates
  - `alembic.ini` — Alembic config (migrations live in `src/sstv_core/database/migrations/`)
- `sstv_desktop/` — placeholder only (README, no code yet); future Tauri/React shell
- `docs/` — specifications and status (see "Docs to Reference" below)
- `.claude/agents/ssteve-backend-dev.md` — the one repo-defined agent (Python backend work)
- `AGENTS.md` — build commands and code style conventions (canonical for style detail)

**Key principle:** the core is 100% headless and UI-agnostic. All frontend communication happens via REST API and WebSocket. Never couple engine code to UI assumptions.

## Environment & Commands

**uv is the canonical environment tool** (`sstv_core/uv.lock` is checked in). pip + venv works as a fallback (`requirements.txt` / `pip install -e ".[dev]"`).

```bash
cd sstv_core

# Install (including dev deps: pytest, httpx, ruff, mypy)
uv sync --extra dev

# Run all tests
uv run pytest

# Single file / single test
uv run pytest tests/api/test_routes_decode.py
uv run pytest -k "test_list_audio_devices"

# Lint / type check
uv run ruff check src/
uv run mypy src/

# Run the API server (FastAPI + uvicorn on http://127.0.0.1:8000)
uv run sstv-server

# CLI (decode / encode / list-devices)
uv run python -m sstv_core.cli.main --help
```

Notes:

- Always `cd sstv_core` first — pytest, uv, and alembic are all rooted there.
- The `sstv-decode` / `sstv-encode` console scripts declared in `pyproject.toml` are currently broken (they point at `sstv_core.cli:decode`/`:encode`, which don't exist). Use `python -m sstv_core.cli.main` instead. `sstv-server` works.
- `sounddevice` needs PortAudio (`brew install portaudio` on macOS, `libportaudio2` on Debian). Tests mock audio hardware via `tests/conftest.py`.

## Module Map (`sstv_core/src/sstv_core/`)

- `decode/` — RX pipeline: `rx_manager.py` (session orchestration), per-mode decoders (`scottie_decoder.py`, `martin_decoder.py`, `robot_decoder.py`), `vis_detector.py` + `correlation_vis_detector.py` (VIS detection), `sync_detector.py`, `hough_slant_corrector.py` (Hough-transform slant correction), `fsk_decoder.py` (FSKID), `image_saver.py`
- `encode/` — TX pipeline: `tx_manager.py`, per-mode encoders (Scottie/Martin/Robot), `vis_generator.py`, `fsk_generator.py` (FSKID), `image_preprocessor.py`, `audio_transmitter.py`
- `audio/` — `stream_manager.py`, `device_manager.py`, `ring_buffer.py`, `bandpass_filter.py`, `ptt_controller.py` (Serial RTS/DTR + VOX)
- `api/` — **implemented** FastAPI layer: `main.py` (app + `run_server`), `routes/` (decode, transmit, devices, images, config, qso, smart_reply, import_routes, websocket), `websocket_manager.py`, `session_manager.py` (half-duplex enforcement), `operation_manager.py`, `dsp_manager.py`, `models.py` (Pydantic)
- `database/` — SQLAlchemy 2.0 models (`models.py`) + Alembic migrations (`migrations/`); SQLite, metadata only — images live on disk as files
- `smart_features/` — `mode_detector.py` (sync-timing mode detection), `device_detector.py`, `qso_logger.py`, `field_populator.py`, `template_engine.py` (smart replies)
- `accessibility/` — `audio_guidance.py` (stereo sonification), `slant_detector.py`
- `filesystem/` — `watcher.py` (watchdog), `importer.py`, `mmsstv_importer.py`
- `config/` — `manager.py` (thread-safe ConfigManager backed by DB)
- `cli/` — `main.py` (argparse CLI: decode, encode, list-devices; `--json` mode for screen readers)
- `engine/` — currently an empty namespace (docstring only)

The API layer is fully implemented — do not treat it as planned. The REST/WebSocket contract lives in `docs/core/backend-spec.md` and `docs/core/openapi.json`.

## Architecture Constraints

- **Half-duplex:** one active operation at a time (decode OR transmit). `SessionManager` enforces it; violations return 409.
- **Filesystem-native storage:** images are regular files; the database stores metadata only (filepath, callsign, SNR, timestamp). Never store image blobs.
- **Graceful degradation:** SSTV signals are noisy; auto-detection fails 20–40% of the time. Every smart feature needs a manual fallback. Confidence thresholds: ≥0.85 high, 0.70–0.84 medium, <0.70 require manual.
- **Manual overrides stay accessible:** input-gain auto-detect fails on QSB/fading signals, auto-only AFC is dangerous for satellite (Doppler) work, and auto squelch fails in contest QRM. Gain/squelch/AFC overrides must remain in the primary interface, not buried in settings.
- **PTT:** Serial (RTS/DTR via pyserial) or VOX (silence preamble); pre-delay 500 ms, post-delay 200 ms, configurable.
- **Error voice:** SSTeVe brand voice in user-facing errors — contractions, first person ("I couldn't detect the mode"), structured detail objects with `suggested_action`.

## UX Position (settled conclusions)

A December 2025 multi-perspective review of the UI settled these points (the reviews themselves are not recoverable; these conclusions are the record):

- Canvas visibility while listening is non-negotiable; a waterfall display is essential.
- Auto-detection may set defaults, but manual overrides (gain, squelch, AFC) must stay accessible — this is an operational constraint, not a style choice.
- "Operating Conditions" modes (Standard / Night Vision / Sunlight) are operational features, not aesthetics.
- The 8-control vs 15-control density debate is unresolved pending user testing; the tension between simplicity and operational flexibility is intentional.

Design targets four archetypes: Makers (scriptable/headless), Activators (POTA/SOTA field ops), Preppers ("just works"), Old Guard (MMSSTV migrants).

## Definition of Done

Work is done when, from `sstv_core/`:

1. `uv run pytest` passes — the full suite, no exclusions. (As of 2026-08-05 there are no known pre-existing failures; CI runs the whole suite.)
2. `uv run ruff check src/` and `uv run mypy src/` are clean for files you changed.
3. API changes keep `docs/core/backend-spec.md` / `docs/core/openapi.json` in sync (regenerate via `scripts/export_api_docs.py`).

## Docs to Reference

- `docs/core/backend-spec.md` — backend architecture and REST/WebSocket API contract
- `docs/core/frontend-spec.md` — UI components and design system spec
- `docs/core/openapi.json` — exported OpenAPI schema
- `docs/design/DESIGN_RATIONALE.md` — UI design philosophy and voice
- `docs/BETA_LAUNCH_PLAN.md` — beta roadmap and priorities
- `docs/status/` — phase summaries and `PROJECT_STATUS.md` (what works / what doesn't)
- `docs/features/` — FSKID, auto-RSV, and DSP feature specifications
- `AGENTS.md` — canonical code style guide (imports, typing, logging, error handling, test patterns)

GEMINI.md is retired; do not use it.
