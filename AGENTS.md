# Repository Guidelines

## Project Structure & Module Organization
- `sstv-station/` – Tauri app UI and shell
  - `src/` (Vite + JS), `index.html`, `vite.config.js`
  - `src-tauri/` (Rust backend, Tauri 2) – `Cargo.toml`, `src/main.rs`
- `core/python/sstv_engine/` – Python decode/encode/enhance engine
- `core/shared/testing/` – reference assets and helper test scripts
- `tools/` – utility scripts (e.g., `setup_platform.sh`, `download_test_files.py`)
- `venv/` – optional Python virtual environment (local development)

## Build, Test, and Development Commands
- Prerequisites: Node 18+, Rust toolchain, Python 3.10+.
- App (desktop dev): `cd sstv-station && npm install && npm run tauri dev`
- App (web preview only): `cd sstv-station && npm run dev`
- App (desktop build): `cd sstv-station && npm run tauri build`
- Python engine setup: `python -m venv venv && source venv/bin/activate && pip install -r core/python/requirements.txt`
- Engine CLI examples:
  - Decode: `python -m sstv_engine.cli decode input.wav out.png --json`
  - Encode: `python -m sstv_engine.cli encode input.png out.wav --mode ScottieS1`
- Test helpers (manual): see `core/shared/testing/scripts/*.js` (Node scripts operate on assets under `core/shared/testing`).

## Coding Style & Naming Conventions
- JavaScript: ES modules, 2‑space indent, kebab‑case files (e.g., `main.js`, `style.css`). Prefer Prettier defaults.
- Rust: Edition 2021. Format and lint before pushing: `cargo fmt` and `cargo clippy` (from `sstv-station/src-tauri`).
- Python: PEP 8, snake_case modules. Prefer `black`/`ruff` if available.
- Paths: use project‑relative paths; avoid hardcoding absolute paths.

## Testing Guidelines
- Primary coverage via sample decode/encode runs (Engine CLI) and JS helper scripts in `core/shared/testing/scripts`.
- Large test assets are not stored by default. Use scripts under `tools/` to fetch assets if needed.
- Name ad‑hoc tests clearly (e.g., `roundtrip_test.js`) and write outputs to `core/shared/testing/results/`.

## Commit & Pull Request Guidelines
- Commits: imperative mood, concise subject (≤72 chars), include scope when helpful (e.g., `tauri:`, `engine:`). Example: `engine: add Martin M2 mode validation`.
- PRs: include purpose, summary of changes, test steps, and screenshots for UI‑visible changes. Link related issues and note platform impacts (web vs. desktop).

## Security & Configuration Tips
- Python is invoked from the Rust backend; keep paths validated and prefer the repo `venv` interpreter.
- Do not bypass input/path validation or expand resource access beyond Tauri’s allowed dirs.
- Store secrets outside the repo; `.env` is for local dev only.

