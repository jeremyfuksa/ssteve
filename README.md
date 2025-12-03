# SSTV Station

Desktop SSTV toolkit built with Tauri (Rust backend + Vite/JS UI) and a bundled Python engine for encoding/decoding SSTV images. The app targets Windows, macOS, and Linux and ships with a self-contained Python environment for reliable offline use.

## What You Can Do
- Decode SSTV recordings to images (Scottie, Martin, Robot modes).
- Encode images to WAV for transmission.
- Use drag-and-drop, keyboard shortcuts (`Ctrl+O`, `Ctrl+S`), and a Recent list for faster workflows.
- Browse decoded images in the gallery and save outputs.

## Quick Start (Desktop Dev)
```bash
cd sstv-station
npm install
npm run tauri dev
```

For packaging with the bundled Python engine, run `./tools/bundle_python.sh` from the repo root, then `npm run tauri build` inside `sstv-station/`.

## Documentation
- User Guide: `docs/USER_GUIDE.md`

If you are contributing, follow the conventions in `AGENTS.md` and `IMPLEMENTATION_PLAN.md`. Bug reports benefit from including platform details and the SSTV mode or sample file used.
