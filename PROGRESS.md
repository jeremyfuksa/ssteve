# Progress, Insights, and Working Notes

Updated: 2025-09-09

## Summary
- Essentials added: AGENTS.md, Architecture.md, ROADMAP.md, PR template, minimal CI (Node build, Rust fmt/clippy/build/test, guarded Python smoke).
- Rust↔Python bridge aligned to engine types; UI wired for decode (file) and encode (image→WAV). Tauri config fixed to build on Linux.

## Key Changes
- Tauri v2 deps corrected; removed invalid `shell-open` feature; explicit `2.0.0` versions for core plugins.
- Commands now take `AppHandle`; default handle removed.
- Python invocation uses `SSTVDecodeRequest`/`SSTVEncodeRequest`; Rust parses `SUCCESS/IMAGE/AUDIO/MODE` lines.
- Dev fallback: `get_python_engine_path()` resolves `core/python` from repo tree when not bundled.
- Icon requirement satisfied with a valid RGBA PNG at `src-tauri/icons/icon.png`.

## Current State
- Build: passes; runtime requires GTK (desktop session) or Xvfb for headless.
- Decode: LOAD FILE → decodes WAV → renders image; status includes mode.
- Encode: TRANSMIT → ENCODE AUDIO → generates WAV using selected mode.
- Tests: small Rust unit test; Python smoke tests guarded by `RUN_ENGINE_TESTS=1`.

## Known Constraints / Next
- Linux runtime requires GUI; use `xvfb-run` in headless.
- Packaging: reintroduce resource bundling once stable; wire save dialogs for audio.
- Optional: live audio streaming decode; broader tests; nicer icons.

## Memory Nuggets
- Tauri resource globs can block dev builds; prefer runtime resolution during development.
- `generate_context!()` enforces a valid RGBA PNG icon.
- Keep embedded Python scripts minimal; prefer JSON I/O or a tiny bridge module.
