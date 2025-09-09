#+ Roadmap

This document tracks the minimal milestones required to ship a working desktop SSTV app with decode/encode via UI, plus essentials for maintainability.

## Milestone 0 — Build Green
- Fix Rust compile (e.g., stray quote in `src-tauri/src/main.rs`).
- Run: `cd sstv-station/src-tauri && cargo build && cargo test`.
- Acceptance: build and tests pass locally.

## Milestone 1 — Python Bridge Aligned
- Align Rust→Python calls with engine API (use JSON request/response via `sstv_engine.cli` or direct types).
- Centralize inline Python snippets; consistent SUCCESS/ERROR keys.
- Acceptance: `decode_sstv_file` decodes a small WAV and returns image path + VIS code.

## Milestone 2 — File Decode (UI)
- Wire file picker → Tauri `decode_sstv_file` → canvas render.
- Display mode/VIS and progress.
- Acceptance: Select WAV → image shows with status + mode.

## Milestone 3 — Image Encode (UI)
- Implement `get_sstv_modes`; connect mode selector; call `encode_sstv_image`.
- Enable save dialog for WAV.
- Acceptance: Pick PNG → choose mode → WAV generated and saved.

## Milestone 4 — Resource Bundling
- Bundle `core/python` with Tauri; prefer repo `venv` python, fallback to `python3`.
- Keep path validation and sanitized errors.
- Acceptance: Built app works without dev toolchain.

## Milestone 5 — Cross‑Platform Packaging
- Minimal Tauri config for Windows/macOS/Linux (fs/dialog permissions).
- Acceptance: `npm run tauri build` produces installables; decode smoke test passes per OS.

## Milestone 6 — Tests (Essentials)
- Rust: tests for sanitization, path validators, output parsing.
- Python: encode/decode smoke tests (tiny generated assets; guarded if deps missing).
- Acceptance: `cargo test` + `RUN_ENGINE_TESTS=1 pytest -q core/python/tests` pass.

## Milestone 7 — Docs & UX Polish
- Update `Architecture.md`; add brief User Guide.
- UI: disable buttons during work; basic error toasts.
- Acceptance: New user decodes/encodes in <5 minutes.

## Optional (Defer)
- Live audio capture/streaming decode, broader tests, release signing.

## Definition of Done
- App builds and runs on at least one OS from a clean machine.
- File decode/encode work end‑to‑end via UI.
- CI green with minimal tests.
- Docs reflect actual flows and troubleshooting.

## AI Assistance (Gemini Flash)
Use Gemini Flash for fast drafts and small, surgical patches. Provide exact file paths and ask for minimal diffs. Good prompts by milestone:

- M0 Build Green
  - Prompt: "Scan `sstv-station/src-tauri/src/main.rs` for syntax issues (e.g., stray quotes) and return a minimal patch to compile with Rust 1.75+."
  - Prompt: "Suggest `cargo clippy` fixes that don’t change behavior; output the exact code edits."

- M1 Python Bridge Aligned
  - Prompt: "Refactor Rust inline Python to a single JSON I/O script; update `decode_sstv_file` and `encode_sstv_image` to pass/parse JSON matching `sstv_engine.types` (paths given). Return patch for `main.rs` + the embedded script string."
  - Prompt: "Draft a tiny Python shim `core/python/sstv_engine/bridge.py` exposing `decode_json`/`encode_json`."

- M2 File Decode (UI)
  - Prompt: "In `sstv-station/src/main.js`, add `pickAndDecode()` that opens a file, calls `invoke('decode_sstv_file')`, updates canvas, and shows VIS/mode. Provide only the new methods and the minimal wiring."

- M3 Image Encode (UI)
  - Prompt: "Add `get_sstv_modes` command in Rust and wire a mode dropdown in `main.js`. Provide patches for both files."

- M4 Resource Bundling
  - Prompt: "Propose Tauri 2 config changes to bundle `core/python` and detect `venv` vs `python3`. Return the exact JSON/TOML edits and Rust path resolution tweak."

- M5 Packaging
  - Prompt: "Produce minimal `tauri.conf.json` permissions for dialog/fs and a GH Actions job snippet to build Linux/macOS/Windows."

- M6 Tests
  - Prompt: "Add Rust tests for path validators and JSON output parsing in `src-tauri`. Add pytest param tests for encode/decode using generated images only. Provide test files and updates to CI."

- M7 Docs & UX
  - Prompt: "Write a 1‑page User Guide: open file → decode; encode image → save WAV; common errors."

Tips: Ask for patch-ready edits, avoid new dependencies, and keep changes under 100 lines per request.

---

## Status Update — 2025-09-09

- M0 Build Green: completed
  - Fixed Tauri v2 deps, removed invalid `shell-open` feature, adjusted command signatures to accept `AppHandle`.
- M1 Python Bridge Aligned: completed
  - Rust now uses `SSTVDecodeRequest`/`SSTVEncodeRequest`; normalized `SUCCESS/MODE/IMAGE/AUDIO` output parsing.
- M2 File Decode (UI): implemented
  - “Load File” decodes WAV and renders image; status shows detected mode.
- M3 Image Encode (UI): implemented
  - TRANSMIT mode exposes “Encode Audio”; uses selected mode and reports output path.
- M4 Resource Bundling: deferred (dev fallback present)
  - Added `get_python_engine_path()` resolution (packaged resources or repo `core/python` during dev). Removed resource glob to unblock builds.
- M5 Packaging: pending
  - Tauri icon path fixed with a small RGBA PNG to satisfy context generation.
- M6 Tests (Essentials): partially completed
  - Rust unit test for error sanitization; guarded Python smoke tests added; CI green for build/lint/test.
- M7 Docs & UX: ongoing
  - Added AGENTS.md, Architecture.md, ROADMAP.md, PR template; CI workflow in place.

Known runtime constraint
- Linux dev requires a GUI session (GTK). Headless runs must use Xvfb (see Architecture.md: Dev Runtime Notes).
