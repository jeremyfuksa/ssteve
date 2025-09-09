# Architecture Overview

This project is a desktop SSTV application built with a Tauri (Rust) backend, a Vite/JavaScript UI, and a Python engine for decode/encode/enhance.

## Components
- UI (Vite + JS) — `sstv-station/src/`
  - Renders controls, status, and canvases; calls backend with `@tauri-apps/api`.
- Backend (Tauri 2, Rust) — `sstv-station/src-tauri/src/main.rs`
  - Validates inputs, mediates filesystem access, and invokes Python securely.
  - Commands: decode file, encode image, list modes, basic image enhancement stub.
- Engine (Python) — `core/python/sstv_engine/`
  - Decoder/Encoder/Enhancer implementations, plus a small CLI for local use.

## Data Flow (Decode)
1. UI selects an audio file and invokes `decode_sstv_file`.
2. Rust validates the path, locates the engine (`core/python`), resolves venv Python, and runs a temporary Python script with env vars.
3. Python decoder produces status lines (SUCCESS/IMAGE/VIS). Rust parses and returns a structured result to the UI.

## Data Flow (Encode)
1. UI provides an image and mode to `encode_sstv_image`.
2. Rust validates inputs, runs the Python encoder, and returns the resulting audio path.

## Notable Considerations
- Security: strict path validation, temporary files with UUIDs, sanitized error messages, minimal resource exposure.
- Local Dev: optionally use `venv/` for Python 3.10+, install `core/python/requirements.txt`.
- Tests: focused smoke tests only; large media assets are optional and fetched via scripts under `tools/`.

## Dev Runtime Notes
- Python engine path resolution: Rust uses `get_python_engine_path()` to locate `core/python` either from bundled resources (packaged) or the repo tree (dev). No resource glob is needed during development.
- Icons: Tauri requires a valid RGBA PNG at `src-tauri/icons/icon.png`; a small 16×16/64×64 RGBA file is sufficient.
- Linux GUI requirement: GTK must initialize (desktop session). In headless environments, use `xvfb-run -a -s "-screen 0 1280x720x24" npm run tauri dev`.
