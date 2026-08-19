#!/usr/bin/env python3
"""Regenerate the accepted off-air decode renders.

`test_decode_matches_the_accepted_render` pins each off-air transmission to the
exact picture we accepted, because every statistical floor tried let a visibly
broken decoder through (a 9% Martin M1 timing error moved adjacent-scanline
correlation by 0.002 while smearing the subject off the frame).

Run this only when a change genuinely improves the decodes, and LOOK at the new
pictures before committing them -- the renders are the record of what "working"
means, so refreshing them carelessly destroys the gate.

    uv run python scripts/refresh_offair_renders.py --review
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

CORPUS = ROOT / "tests" / "reference" / "audio" / "offair"
RENDERS = ROOT / "tests" / "reference" / "images" / "offair_decoded"


def _decode(entry: dict) -> np.ndarray | None:
    from sstv_core.decode.martin_decoder import (
        MartinM1Config,
        MartinM1Decoder,
        MartinM2Config,
    )
    from sstv_core.decode.scottie_decoder import (
        ScottieS1Config,
        ScottieS1Decoder,
        ScottieS2Config,
    )
    from sstv_core.decode.sync_detector import SyncPulseDetector

    decoders = {
        "SCOTTIE_S1": (ScottieS1Decoder, ScottieS1Config, 428.22),
        "SCOTTIE_S2": (ScottieS1Decoder, ScottieS2Config, 277.692),
        "MARTIN_M1": (MartinM1Decoder, MartinM1Config, 446.446),
        "MARTIN_M2": (MartinM1Decoder, MartinM2Config, 226.798),
    }

    audio, rate = sf.read(CORPUS / entry["file"], dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    decoder_cls, config_cls, line_ms = decoders[entry["mode"]]
    detector = SyncPulseDetector(sample_rate=rate)
    detector.detect_in_buffer(audio)
    positions = detector.get_sync_positions(line_duration_ms=line_ms)
    if not positions:
        return None

    decoder = decoder_cls(config_cls(sample_rate=rate))
    for _ in decoder.decode_stream(iter([audio]), positions):
        pass
    return decoder.get_image()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--review",
        action="store_true",
        help="write a side-by-side contact sheet instead of overwriting",
    )
    args = parser.parse_args()

    entries = json.loads((CORPUS / "manifest.json").read_text())
    RENDERS.mkdir(parents=True, exist_ok=True)

    changed = []
    for entry in entries:
        image = _decode(entry)
        if image is None:
            print(f"  {entry['file']}: NO SYNC -- refusing to write")
            continue

        target = RENDERS / entry["file"].replace(".wav", ".png")
        new = Image.fromarray(np.asarray(image, dtype=np.uint8), "RGB")

        if target.exists():
            old = np.array(Image.open(target).convert("RGB"), dtype=np.int16)
            diff = float((np.abs(np.asarray(new, dtype=np.int16) - old).max(axis=2) > 0).mean())
            if diff == 0.0:
                print(f"  {entry['file']}: unchanged")
                continue
            changed.append((entry["file"], diff))

        if args.review:
            new.save(RENDERS / (entry["file"].replace(".wav", "") + ".candidate.png"))
        else:
            new.save(target)

    if not changed:
        print("\nNothing changed.")
        return 0

    print(f"\n{len(changed)} render(s) differ:")
    for name, diff in changed:
        print(f"  {name}: {diff:.1%} of pixels")
    if args.review:
        print("\nCandidates written alongside the accepted renders (*.candidate.png).")
        print("Look at them. If they are better, rerun without --review.")
    else:
        print("\nAccepted renders overwritten. Commit only if you looked at them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
