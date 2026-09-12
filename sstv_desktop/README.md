# SSTeVe desktop

The window: one Tauri + React shell that listens to a SpyServer and decodes
pictures. The engine is a separate process it talks to over REST and WebSocket.

## Running it

Two processes today. The core is spawned as a sidecar in #143; until then start
it yourself:

```bash
cd ../sstv_core && uv run sstv-server     # engine on 127.0.0.1:8000
cd ../sstv_desktop && npm install && npm run tauri dev
```

`npm run dev` alone serves the same UI in a browser at <http://localhost:5173>,
which is useful for layout work and is why the port matters: the engine's CORS
admits `localhost:5173` and `tauri://localhost` and nothing else, so Tauri's
default 1420 would be refused.

## Seeing a decode without waiting for the band

The band is silent 97.4% of the time and 20m closes after dark. Settings has
**Replay a recording**: give it a path to a WAV and the engine plays it through
the live decoder at the speed it was recorded — the same VIS, scanline,
waterfall and completion events a live decode produces. The repository ships
real off-air captures:

```
../sstv_core/tests/reference/audio/offair/cap1_020978s_martin_m1.wav
```

## What is here

| File | What it holds |
| --- | --- |
| `src/core.ts` | The engine's REST + WebSocket surface, in one place |
| `src/App.tsx` | The window: posture, session wiring, log, settings |
| `src/Canvas.tsx` | The picture, painted line by line as it arrives |
| `src/Waterfall.tsx` | The presence strip |
| `src/theme.css` | The visual direction as tokens — provisional, see #152 |
| `src/layout.css` | The fixed instrument and the elastic log |

`layout.css` rather than `app.css` because macOS is case-insensitive and the
template already has an `App.css`; the two names are the same file, which cost
one confusing build failure.

## The shape of the window

Settled in `docs/superpowers/specs/2026-08-21-single-window-activity-log-design.md`:
a fixed-cost instrument (canvas, waterfall, controls) and an elastic log that
takes the remainder. The canvas is sized to the picture at a whole-number scale
and is what degrades on a small window — not the waterfall, not the log.
