# SSTeVe desktop

The window: one Tauri + React shell that listens to a SpyServer and decodes
pictures. The engine is a separate process it talks to over REST and WebSocket.

## Running it

The app starts the engine itself. Build the engine once, then run the app:

```bash
cd ../sstv_core && uv run python scripts/build_engine.py   # ~2 min, 205 MB
cd ../sstv_desktop && npm install && npm run tauri dev
```

`npm run dev` alone serves the same UI in a browser at <http://localhost:5173>,
which is useful for layout work. There it falls back to an engine on port 8000,
so run `uv run sstv-server` yourself for that. The port matters either way: the
engine's CORS admits `localhost:5173` and `tauri://localhost` and nothing else,
so Tauri's default 1420 would be refused.

### How the engine gets started

The shell picks a free port, spawns the frozen engine on it, and waits for it
to answer. Three behaviours worth knowing:

- **An engine already on 8000 is adopted, not replaced.** Running
  `uv run sstv-server` in a terminal and then opening the app gives you one
  engine, not two — and the app will not kill what it did not start.
- **Quitting the app stops the engine it started.** A decode holds the radio's
  audio input and a transmit can leave it keyed, so an orphan is not merely
  untidy.
- **A failure is shown, not swallowed.** "The SSTeVe engine didn't start: the
  engine stopped straight away (exit 1)" rather than an empty window.

The engine ships as a **folder**, not a lone executable: a one-folder
PyInstaller build finds its `_internal` siblings by its own path. A one-file
build would re-extract 205 MB on every launch, turning a 0.9 s start into a
wait. That is why `tauri.conf.json` uses `bundle.resources` rather than
`externalBin`, which copies a single file.

Built for Apple Silicon today. Linux and Windows need the same two commands on
those machines — `build_engine.py` asks `rustc` for the target triple rather
than guessing — plus their own native audio libraries (`libportaudio2`,
`libsndfile`) present at build time. Neither has been built yet.

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
