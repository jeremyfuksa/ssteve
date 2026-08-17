"""Replay a WAV window through the live decode path at wall-clock rate.

Offline decode -- `detect_in_buffer` over a whole file, then slice between
known sync positions -- is proven: the 2026-08-16 capture yielded 24 of 24
transmissions with two legible callsigns. Live decode from a stream has never
produced an image.

The two paths differ in a way that matters. Offline is non-causal: it can look
at sync pulse N+1 to decide where line N ends, so clock drift is absorbed
line-by-line and slant never appears. A live decoder has to commit to a line's
boundaries before the next sync arrives. Whatever breaks live is in that gap,
plus the plumbing around it -- VIS on incremental chunks, ring-buffer
starvation, the decode-phase bound from #94.

This feeds a known-good window from a capture into `RXManager` through the
same `AudioSource` seam a sound card or SpyServer uses, paced at wall-clock
rate so the manager sees audio arriving the way it really does. Same signal,
same decoders, different plumbing -- so any difference is the streaming path,
isolated, and reproducible without waiting on the band.

Usage:

    uv run python scripts/replay_wav.py CAPTURE.wav --start 08:51:30
    uv run python scripts/replay_wav.py CAPTURE.wav --start 0:25:00 --mode ScottieS2
    uv run python scripts/replay_wav.py CAPTURE.wav --start 08:51:30 --speed 4

`--speed` multiplies the feed rate. Above 1 the manager's 100 ms poll sees
proportionally more audio per turn, which stops being a faithful reproduction
of live timing -- useful for a quick pass, not for judging whether live works.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from sstv_core.audio.ring_buffer import AudioRingBuffer
from sstv_core.decode.rx_manager import RXManager

logger = logging.getLogger("replay")


@dataclass
class ReplayLevels:
    """Mirrors `audio.stream_manager.AudioLevels`.

    RXManager only reads these fields off the audio source; duplicating the
    shape here keeps the harness from depending on the sound-card module.
    """

    rms: float = 0.0
    peak: float = 0.0
    is_clipping: bool = False


class WavReplaySource:
    """An `AudioSource` that plays a WAV window at wall-clock rate.

    Implements the same four methods `SpyServerSource` does, which is the
    seam RXManager is written against. Samples are pushed from a background
    thread so the manager's async loop starves and waits exactly as it would
    on a real stream -- feeding the whole window at once would just be the
    offline path in disguise.
    """

    def __init__(
        self,
        path: Path,
        start_sec: float,
        duration_sec: float,
        *,
        speed: float = 1.0,
        chunk_ms: float = 100.0,
    ) -> None:
        self._path = path
        self._start_sec = start_sec
        self._duration_sec = duration_sec
        self._speed = speed
        self._chunk_ms = chunk_ms

        with wave.open(str(path)) as w:
            self._sample_rate = w.getframerate()
            self._channels = w.getnchannels()
            self._sampwidth = w.getsampwidth()
            self._total_frames = w.getnframes()

        if self._sampwidth != 2:
            raise ValueError(
                f"{path.name} is {self._sampwidth * 8}-bit; this harness reads 16-bit PCM"
            )

        # Sized to the window so nothing is dropped if the consumer stalls;
        # a real stream would drop, but here a drop would be the harness
        # lying about the decoder's input rather than a property of it.
        self._buffer = AudioRingBuffer(
            max_samples=int(self._sample_rate * (duration_sec + 5)),
            sample_rate=self._sample_rate,
        )
        self._levels = ReplayLevels()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._finished = threading.Event()
        self._samples_fed = 0

    @property
    def sample_rate(self) -> int:
        """RXManager reads this to size its VIS templates and decoders."""
        return self._sample_rate

    @property
    def samples_fed(self) -> int:
        return self._samples_fed

    @property
    def exhausted(self) -> bool:
        return self._finished.is_set()

    def start_input(self, device_index: int | None = None) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._finished.clear()
        self._thread = threading.Thread(target=self._feed, name="wav-replay", daemon=True)
        self._thread.start()

    def stop_input(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def get_input_buffer(self) -> AudioRingBuffer:
        return self._buffer

    def get_input_levels(self) -> ReplayLevels:
        return self._levels

    def _feed(self) -> None:
        chunk_frames = max(1, int(self._sample_rate * self._chunk_ms / 1000.0))
        want_frames = int(self._duration_sec * self._sample_rate)

        with wave.open(str(self._path)) as w:
            start_frame = max(0, int(self._start_sec * self._sample_rate))
            w.setpos(min(start_frame, self._total_frames))

            fed = 0
            # Pace against a fixed origin rather than sleeping a fixed
            # interval each turn: per-chunk sleeps accumulate the time spent
            # reading and converting, so a long window would drift slower
            # than real time and quietly flatter the decoder.
            origin = time.monotonic()
            while not self._stop.is_set() and fed < want_frames:
                raw = w.readframes(min(chunk_frames, want_frames - fed))
                if not raw:
                    break

                samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
                if self._channels > 1:
                    samples = samples.reshape(-1, self._channels).mean(axis=1)

                self._buffer.add(samples)
                fed += len(samples)
                self._samples_fed = fed

                if len(samples):
                    peak = float(np.max(np.abs(samples)))
                    self._levels = ReplayLevels(
                        rms=float(np.sqrt(np.mean(samples**2))),
                        peak=peak,
                        is_clipping=peak >= 0.999,
                    )

                target = origin + (fed / self._sample_rate) / self._speed
                delay = target - time.monotonic()
                if delay > 0:
                    self._stop.wait(delay)

        self._finished.set()


def parse_timestamp(value: str) -> float:
    """Accept SS, MM:SS, or HH:MM:SS."""
    parts = value.split(":")
    if len(parts) > 3:
        raise argparse.ArgumentTypeError(f"unrecognised timestamp: {value}")
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60.0 + float(part)
    return seconds


async def replay(args: argparse.Namespace) -> int:
    path = Path(args.wav).expanduser()
    if not path.exists():
        logger.error("no such file: %s", path)
        return 2

    start = parse_timestamp(args.start)
    source = WavReplaySource(
        path,
        start_sec=max(0.0, start - args.lead_in),
        duration_sec=args.duration + args.lead_in,
        speed=args.speed,
        chunk_ms=args.chunk_ms,
    )

    save_dir = Path(args.output).expanduser()
    save_dir.mkdir(parents=True, exist_ok=True)

    manager = RXManager(
        stream_manager=source,
        save_directory=save_dir,
        slant_correction=args.slant_correction,
    )

    seen_states: list[str] = []
    last_line = -1

    def on_progress(progress) -> None:
        nonlocal last_line
        state = progress.state.value if hasattr(progress.state, "value") else str(progress.state)
        if not seen_states or seen_states[-1] != state:
            seen_states.append(state)
            logger.info(
                "state -> %-12s %s", state, progress.message or ""
            )
        if progress.current_line and progress.current_line != last_line:
            last_line = progress.current_line
            if last_line % 32 == 0:
                logger.info(
                    "  line %3d/%-3d  mode=%s conf=%.2f",
                    progress.current_line,
                    progress.total_lines,
                    progress.mode,
                    progress.mode_confidence,
                )

    manager.set_progress_callback(on_progress)

    logger.info(
        "replaying %s from %s for %.0fs at %.1fx (lead-in %.0fs, chunk %.0fms)",
        path.name, args.start, args.duration, args.speed, args.lead_in, args.chunk_ms,
    )
    if args.mode:
        logger.info("mode forced to %s -- VIS detection skipped", args.mode)

    wall_start = time.monotonic()
    saved = await manager.receive(
        mode=args.mode,
        timeout_sec=args.timeout,
    )
    elapsed = time.monotonic() - wall_start

    logger.info("-" * 60)
    logger.info("finished in %.1fs wall clock", elapsed)
    logger.info("audio fed: %.1fs", source.samples_fed / source.sample_rate)
    logger.info("states: %s", " -> ".join(seen_states))
    logger.info("final state: %s", manager.state.value)

    if saved is None:
        logger.warning("no image produced")
        return 1

    logger.info("image saved: %s", saved)
    try:
        import cv2
    except ImportError:
        return 0

    img = cv2.imread(str(saved))
    if img is not None:
        g = img.astype(np.float64).mean(axis=2)
        # Row-to-row correlation separates real content from noise: noise is
        # spatially uncorrelated, a picture is not. Offline decodes of this
        # capture ran 0.03-0.30, so anything in that range is comparable.
        vcorr = float(np.corrcoef(g[:-1].ravel(), g[1:].ravel())[0, 1])
        logger.info(
            "  %dx%d  std=%.1f  row-row corr=%.3f",
            img.shape[1], img.shape[0], float(np.std(img)), vcorr,
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replay a WAV window through the live decode path.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage:")[-1],
    )
    parser.add_argument("wav", help="capture file (16-bit PCM WAV)")
    parser.add_argument(
        "--start", required=True,
        help="offset into the file where the transmission begins (SS, MM:SS, or HH:MM:SS)",
    )
    parser.add_argument(
        "--duration", type=float, default=140.0,
        help="seconds of audio to replay (default: 140, covers Scottie S1)",
    )
    parser.add_argument(
        "--lead-in", type=float, default=10.0,
        help="seconds to start before --start, so the VIS header is included "
             "(default: 10). Sync-periodicity timestamps mark where the picture "
             "starts, which is after the header.",
    )
    parser.add_argument(
        "--mode", default=None,
        help="force a mode (ScottieS1, ScottieS2, MartinM1, Robot36) and skip "
             "VIS detection. Use to test decode independently of #97.",
    )
    parser.add_argument(
        "--speed", type=float, default=1.0,
        help="feed rate multiplier (default: 1.0 = wall clock). Above 1 the "
             "manager sees more audio per poll, so it stops reproducing live timing.",
    )
    parser.add_argument(
        "--chunk-ms", type=float, default=100.0,
        help="size of each pushed chunk in ms (default: 100)",
    )
    parser.add_argument(
        "--timeout", type=float, default=180.0,
        help="RXManager VIS timeout in seconds (default: 180)",
    )
    parser.add_argument(
        "--slant-correction", action="store_true",
        help="enable Hough slant correction (off by default; see rx_manager for why)",
    )
    parser.add_argument(
        "--output", default="~/sstv_replay",
        help="directory for decoded images (default: ~/sstv_replay)",
    )
    parser.add_argument("--verbose", action="store_true", help="DEBUG logging")

    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    return asyncio.run(replay(args))


if __name__ == "__main__":
    sys.exit(main())
