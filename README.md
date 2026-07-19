# SSTeVe

A modern SSTV (Slow-Scan Television) application for amateur radio operators.

SSTeVe is built as a headless Python core engine — SSTV decoding and encoding (Scottie, Martin, Robot modes), real-time audio I/O, PTT control, FSKID, and smart features — fronted by a FastAPI REST + WebSocket server. A native desktop app (`sstv_desktop/`, Tauri/React) is planned on top of that API.

## Quickstart

```bash
cd sstv_core

# uv is the canonical env tool (pip + requirements.txt works as a fallback)
uv sync --extra dev

# Run the test suite
uv run pytest

# Start the API server (http://127.0.0.1:8000)
uv run sstv-server

# CLI: decode, encode, list-devices
uv run python -m sstv_core.cli.main --help
```

`sounddevice` requires PortAudio (`brew install portaudio` on macOS, `apt install libportaudio2` on Debian/Ubuntu).

## Documentation

- `sstv_core/README.md` — core engine details
- `docs/core/backend-spec.md` — architecture and API contract
- `docs/BETA_LAUNCH_PLAN.md` — roadmap
- `AGENTS.md` / `CLAUDE.md` — conventions and project guide for coding agents
