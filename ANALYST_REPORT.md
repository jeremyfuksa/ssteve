# SSTV Station – Analyst Readout

## Goal
Desktop SSTV app that decodes recorded audio to images and encodes images to SSTV audio, with a Tauri (Rust) shell, Vite/JS UI, and a Python engine for the heavy lifting.

## How Close to the Goal
- Core decode/encode flows are implemented end-to-end in development mode: UI calls Tauri commands → Rust validates/launches Python → engine returns images/WAVs with mode metadata.
- Builds and basic tests pass locally; CI covers Node build plus Rust fmt/clippy/build/test and guarded Python smoke tests.
- Packaging/bundling for distribution is not finished; cross-platform installers and fully bundled Python are still pending.

## What Is in Place
- **Architecture:** Vite/JS UI under `sstv-station/src`; Tauri 2 backend in `sstv-station/src-tauri` mediates filesystem access and spawns Python; Python engine in `core/python/sstv_engine` (decoder/encoder/enhancer, CLI entrypoints).
- **Rust↔Python bridge:** Uses typed requests (`SSTVDecodeRequest`/`SSTVEncodeRequest`), parses `SUCCESS/MODE/IMAGE/AUDIO` lines, and resolves engine path from repo during dev; icon path fixed to satisfy Tauri.
- **UI flows:** “Load File” decodes WAV and renders image with detected mode; TRANSMIT panel encodes PNG → WAV with selected mode.
- **Docs:** AGENTS.md (structure/commands), Architecture.md (flows, constraints), ROADMAP.md (milestones), PR template, minimal CI workflow.
- **Testing:** Small Rust unit test (sanitization), optional Python smoke tests (`RUN_ENGINE_TESTS=1`), manual helper scripts under `core/shared/testing/scripts`; reference assets live in `core/shared/testing/reference`.

## What Remains / Gaps
- **Packaging & bundling:** Bundle `core/python` and choose `venv` vs `python3` for packaged builds; reintroduce resource globs safely. Produce installers for Windows/macOS/Linux (`npm run tauri build`).
- **UX polish:** Save dialog for encoded audio, disable buttons during work, basic error toasts; add a brief user guide.
- **Tests:** Broader Rust coverage (path validators, JSON parsing), real Python encode/decode tests with generated assets, and possibly UI smoke.
- **Headless/dev ergonomics:** Linux GUI requirement (GTK); headless needs Xvfb. Consider clearer instructions or automation.
- **Optional stretch:** Live audio streaming decode and richer QA around real-world signals.

## Quick Run Notes
- Dev app: `cd sstv-station && npm install && npm run tauri dev` (needs GTK/X session; use `xvfb-run` in headless).
- Web preview: `cd sstv-station && npm run dev` (no Rust).
- Engine CLI: `python -m venv venv && source venv/bin/activate && pip install -r core/python/requirements.txt`; decode `python -m sstv_engine.cli decode input.wav out.png --json`; encode `python -m sstv_engine.cli encode input.png out.wav --mode ScottieS1`.
