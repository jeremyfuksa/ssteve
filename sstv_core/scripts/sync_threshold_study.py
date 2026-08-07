"""Measure the real distribution of 1200 Hz Goertzel magnitudes across the
reference corpus, to choose a sync detection threshold from data rather than
guesswork.

Context: `SyncPulseDetector.DETECTION_THRESHOLD` is 0.6, but
`GoertzelFilter.magnitude()` divides accumulated power by len(samples), so a
pure full-amplitude 1200 Hz sine only reaches ~0.45. The threshold is
unreachable, and no sync pulse has ever been detected.

The question this script answers: is the fix a corrected threshold, or does
`magnitude()` need normalizing so a threshold means something physical
independent of block size and signal level?

Key test: sync pulses in SSTV are full-amplitude tones, but so is white
(2300 Hz) in a bright image. A usable threshold must separate 1200 Hz from
*other loud tones*, not merely from silence -- so this measures both the
1200 Hz response and the response at 1500/1900/2300 Hz on the same blocks.
"""

from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sstv_core.decode.sync_detector import GoertzelFilter, SyncPulseDetector  # noqa: E402

REFERENCE_AUDIO = Path(__file__).parent.parent / "tests" / "reference" / "audio"

# Scottie S1 sync is 9ms, Martin M1 4.862ms. A 4ms block fits inside both.
BLOCK_MS = 4.0


def load_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wf:
        channels, width, rate = wf.getnchannels(), wf.getsampwidth(), wf.getframerate()
        frames = wf.readframes(wf.getnframes())
    data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data, rate


def theoretical_ceiling(rate: int, block_size: int, freq: float) -> float:
    """Magnitude of a pure full-amplitude tone at `freq` -- the best case."""
    t = np.arange(block_size) / rate
    tone = np.sin(2 * np.pi * freq * t).astype(np.float32)
    return GoertzelFilter(freq, rate, block_size).magnitude(tone)


def main() -> int:
    files = sorted(REFERENCE_AUDIO.rglob("*.wav"))
    if not files:
        print("no reference audio found", file=sys.stderr)
        return 1

    print("=" * 100)
    print("SYNC THRESHOLD STUDY -- 1200 Hz Goertzel response across the reference corpus")
    print(f"block = {BLOCK_MS}ms   current DETECTION_THRESHOLD = "
          f"{SyncPulseDetector.DETECTION_THRESHOLD}")
    print("=" * 100)
    print(f"{'file':<34} {'rate':>6} {'ceil':>6} {'p50':>7} {'p95':>7} "
          f"{'p99':>7} {'p999':>7} {'max':>7} {'sep':>6}")
    print("-" * 100)

    all_p999 = []
    all_p50 = []
    all_max = []

    for path in files:
        audio, rate = load_wav(path)
        bs = int(rate * BLOCK_MS / 1000)
        if bs < 4:
            print(f"{path.name[:33]:<34} {rate:>6}  block too small, skipped")
            continue

        f1200 = GoertzelFilter(1200.0, rate, bs)
        n_blocks = (len(audio) - bs) // bs
        mags = np.array([
            f1200.magnitude(audio[i * bs:(i + 1) * bs]) for i in range(n_blocks)
        ])

        ceiling = theoretical_ceiling(rate, bs, 1200.0)
        p50, p95, p99 = np.percentile(mags, [50, 95, 99])
        p999 = np.percentile(mags, 99.9)
        mx = mags.max()

        # Separation: how far the sync population sits above the typical block.
        sep = mx / p50 if p50 > 0 else float("inf")

        all_p999.append(p999)
        all_p50.append(p50)
        all_max.append(mx)

        print(f"{path.name[:33]:<34} {rate:>6} {ceiling:>6.3f} {p50:>7.4f} "
              f"{p95:>7.4f} {p99:>7.4f} {p999:>7.4f} {mx:>7.4f} {sep:>6.1f}x")

    print("-" * 100)
    print(f"corpus: p50 range {min(all_p50):.4f}-{max(all_p50):.4f}   "
          f"p99.9 range {min(all_p999):.4f}-{max(all_p999):.4f}   "
          f"max range {min(all_max):.4f}-{max(all_max):.4f}")

    # --- Selectivity: does 1200 Hz separate from other SSTV tones? ---
    print()
    print("=" * 100)
    print("SELECTIVITY -- is the 1200 Hz filter actually selective, or just a level meter?")
    print("A sync pulse is a loud tone; so is white (2300 Hz). The filter must tell them apart.")
    print("=" * 100)

    sample = files[0]
    audio, rate = load_wav(sample)
    bs = int(rate * BLOCK_MS / 1000)
    print(f"probe file: {sample.name}  rate={rate}  block={bs}")
    print()
    print(f"{'pure tone at':<16} " + "".join(f"{f'{p}Hz filt':>12}" for p in (1200, 1500, 1900, 2300)))
    print("-" * 68)
    for tone_hz in (1200.0, 1500.0, 1900.0, 2300.0):
        t = np.arange(bs) / rate
        tone = np.sin(2 * np.pi * tone_hz * t).astype(np.float32)
        row = "".join(
            f"{GoertzelFilter(probe, rate, bs).magnitude(tone):>12.4f}"
            for probe in (1200.0, 1500.0, 1900.0, 2300.0)
        )
        print(f"{tone_hz:>10.0f} Hz    {row}")

    print()
    print("Diagonal = on-target response; off-diagonal = leakage. If the diagonal is not")
    print("clearly dominant, the block is too short for the filter to resolve these tones")
    print("and a threshold alone cannot fix detection.")

    # --- Candidate thresholds ---
    print()
    print("=" * 100)
    print("CANDIDATE THRESHOLDS -- blocks passing, per file (want: a few per line, ~256 lines)")
    print("=" * 100)
    candidates = [0.10, 0.15, 0.20, 0.25, 0.30]
    print(f"{'file':<34} {'lines':>6} " + "".join(f"{c:>10.2f}" for c in candidates))
    print("-" * 100)

    for path in files:
        audio, rate = load_wav(path)
        bs = int(rate * BLOCK_MS / 1000)
        if bs < 4:
            continue
        f1200 = GoertzelFilter(1200.0, rate, bs)
        n_blocks = (len(audio) - bs) // bs
        mags = np.array([
            f1200.magnitude(audio[i * bs:(i + 1) * bs]) for i in range(n_blocks)
        ])
        # Expected sync count: ~256 lines for Scottie/Martin.
        counts = "".join(f"{int((mags > c).sum()):>10}" for c in candidates)
        print(f"{path.name[:33]:<34} {256:>6} {counts}")

    print()
    print("A correct threshold yields roughly one contiguous run of passing blocks per")
    print("scanline. Far more means noise is passing; far fewer means sync is being missed.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
