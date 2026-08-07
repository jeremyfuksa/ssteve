"""Decode-quality harness: measure decoded images against reference ground truth.

Answers two questions the test suite cannot:

1. How good are the decodes, per file, against paired expected images?
2. Does Hough slant correction help, hurt, or do nothing?

Question 2 is the point. `HoughSlantCorrector` runs on every decode
(`rx_manager.py:371`) and has no tests. It infers a rotation angle from image
content, which is expected to be weakest on low-structure photographs -- and a
wrong rotation resamples detail the radio actually delivered. If correction
lowers the score on even one file, that is a real defect, and the per-file
report below is designed to surface it rather than average it away.

Usage:
    uv run python scripts/decode_quality.py
    uv run python scripts/decode_quality.py --json      # machine-readable
    uv run python scripts/decode_quality.py --save-dir /tmp/decodes

Not a pytest test: it is a measurement tool whose output is a report, and it
takes minutes rather than seconds.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sstv_core.decode.hough_slant_corrector import HoughSlantCorrector  # noqa: E402
from sstv_core.decode.martin_decoder import MartinM1Decoder  # noqa: E402
from sstv_core.decode.scottie_decoder import ScottieS1Decoder  # noqa: E402
from sstv_core.decode.sync_detector import SyncPulseDetector  # noqa: E402

REFERENCE_ROOT = Path(__file__).parent.parent / "tests" / "reference"


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def ssim(img_a: np.ndarray, img_b: np.ndarray) -> float:
    """Structural similarity between two grayscale float images in [0, 1].

    Implemented on cv2 primitives rather than pulling in scikit-image for a
    measurement script. Standard Wang et al. formulation: 11x11 Gaussian
    window, sigma 1.5, C1/C2 from L=1.0.

    SSIM rather than raw pixel difference because the expected images are JPEG
    ground truth from another decoder: a decode can be perceptually correct
    while differing numerically everywhere. SSIM tracks structure, which is
    what "did the picture come out right" actually means.
    """
    c1 = (0.01 ** 2)
    c2 = (0.03 ** 2)

    a = img_a.astype(np.float64)
    b = img_b.astype(np.float64)

    kernel = (11, 11)
    sigma = 1.5

    mu_a = cv2.GaussianBlur(a, kernel, sigma)
    mu_b = cv2.GaussianBlur(b, kernel, sigma)

    mu_a_sq = mu_a ** 2
    mu_b_sq = mu_b ** 2
    mu_ab = mu_a * mu_b

    sigma_a_sq = cv2.GaussianBlur(a * a, kernel, sigma) - mu_a_sq
    sigma_b_sq = cv2.GaussianBlur(b * b, kernel, sigma) - mu_b_sq
    sigma_ab = cv2.GaussianBlur(a * b, kernel, sigma) - mu_ab

    numerator = (2 * mu_ab + c1) * (2 * sigma_ab + c2)
    denominator = (mu_a_sq + mu_b_sq + c1) * (sigma_a_sq + sigma_b_sq + c2)

    return float(np.mean(numerator / denominator))


def compare(decoded: np.ndarray, expected: np.ndarray) -> dict[str, float]:
    """Compare a decoded RGB image against an expected RGB image.

    The expected images differ in resolution from the decoder output (they are
    whatever the reference decoder produced), so the decoded image is resized
    to the expected geometry before comparison. Resizing the decode rather than
    the reference keeps the ground truth untouched.
    """
    exp_h, exp_w = expected.shape[:2]
    dec = cv2.resize(decoded, (exp_w, exp_h), interpolation=cv2.INTER_AREA)

    dec_gray = cv2.cvtColor(dec, cv2.COLOR_RGB2GRAY).astype(np.float64) / 255.0
    exp_gray = cv2.cvtColor(expected, cv2.COLOR_RGB2GRAY).astype(np.float64) / 255.0

    structural = ssim(dec_gray, exp_gray)

    mse = float(np.mean((dec_gray - exp_gray) ** 2))
    psnr = float("inf") if mse == 0 else float(10.0 * np.log10(1.0 / mse))

    return {"ssim": structural, "psnr_db": psnr, "mse": mse}


# ---------------------------------------------------------------------------
# Decode
# ---------------------------------------------------------------------------


def load_wav(path: Path) -> tuple[np.ndarray, int]:
    """Load a WAV file as mono float32 in [-1, 1]."""
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())

    if width == 2:
        data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif width == 4:
        data = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
    elif width == 1:
        data = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError(f"unsupported sample width: {width}")

    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)

    return data, rate


DECODERS: dict[str, Any] = {
    "ScottieS1": ScottieS1Decoder,
    "MartinM1": MartinM1Decoder,
}


def decode_file(audio_path: Path, mode: str) -> tuple[np.ndarray | None, dict[str, Any]]:
    """Decode one audio file to an RGB image, before any slant correction.

    Returns (image, diagnostics). Image is None if the decode produced nothing.
    """
    audio, rate = load_wav(audio_path)

    diagnostics: dict[str, Any] = {
        "sample_rate": rate,
        "duration_s": round(len(audio) / rate, 2),
    }

    detector = SyncPulseDetector(sample_rate=rate)
    detector.detect_in_buffer(audio)
    sync_positions = detector.get_sync_positions()
    diagnostics["sync_pulses"] = len(sync_positions)

    if not sync_positions:
        diagnostics["error"] = "no sync pulses detected"
        return None, diagnostics

    # Sync-interval statistics: the raw material for timing-based slant
    # correction. A perfectly matched pair of clocks gives a constant interval;
    # drift shows up as a trend across the image.
    if len(sync_positions) > 2:
        intervals = np.diff(np.array(sync_positions, dtype=np.float64))
        diagnostics["sync_interval_mean"] = round(float(np.mean(intervals)), 2)
        diagnostics["sync_interval_std"] = round(float(np.std(intervals)), 2)
        # Least-squares slope of interval vs. line number, in samples per line.
        if len(intervals) > 1:
            x = np.arange(len(intervals), dtype=np.float64)
            slope = float(np.polyfit(x, intervals, 1)[0])
            diagnostics["sync_interval_drift_slope"] = round(slope, 5)

    decoder_cls = DECODERS.get(mode)
    if decoder_cls is None:
        diagnostics["error"] = f"no decoder wired for mode {mode}"
        return None, diagnostics

    decoder = decoder_cls()

    def chunks() -> Any:
        yield audio

    lines = 0
    for _ in decoder.decode_stream(chunks(), sync_positions):
        lines += 1
    diagnostics["lines_decoded"] = lines

    image = decoder.get_image()
    if image is None:
        diagnostics["error"] = "decoder produced no image"
    return image, diagnostics


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------


@dataclass
class Case:
    """One audio file paired with its expected image."""

    name: str
    source: str
    audio: Path
    expected: Path
    mode: str


def discover_cases() -> list[Case]:
    """Pair reference audio with expected images across the three sources."""
    cases: list[Case] = []
    audio_root = REFERENCE_ROOT / "audio"
    image_root = REFERENCE_ROOT / "images"

    # MMSSTV: ground truth from the incumbent decoder, all Scottie S1.
    for wav in sorted((audio_root / "mmsstv").glob("*.wav")):
        expected = image_root / "mmsstv" / f"reference_mmsstv_{wav.stem}_expected.jpg"
        if expected.exists():
            cases.append(Case(wav.stem, "mmsstv", wav, expected, "ScottieS1"))

    # Essex Ham: mode is in the filename.
    for wav in sorted((audio_root / "essexham").glob("*.wav")):
        expected = image_root / "essexham" / f"{wav.stem}.png"
        if not expected.exists():
            continue
        mode = "MartinM1" if "martin" in wav.stem else "ScottieS1"
        cases.append(Case(wav.stem, "essexham", wav, expected, mode))

    # ARISS: real satellite passes, noisy. Scottie S1 / PD120 in practice;
    # only the S1 files have a wired decoder today.
    for wav in sorted((audio_root / "ariss").glob("*.wav")):
        expected = image_root / "ariss" / f"{wav.stem}.jpg"
        if expected.exists():
            cases.append(Case(wav.stem, "ariss", wav, expected, "ScottieS1"))

    return cases


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


@dataclass
class Result:
    name: str
    source: str
    mode: str
    ok: bool
    raw: dict[str, float] | None
    corrected: dict[str, float] | None
    hough_angle: float | None
    hough_confidence: float | None
    hough_lines: int | None
    delta_ssim: float | None
    diagnostics: dict[str, Any]


def run_case(case: Case, save_dir: Path | None) -> Result:
    """Decode one case and score it with and without Hough correction."""
    image, diagnostics = decode_file(case.audio, case.mode)

    if image is None:
        return Result(
            case.name, case.source, case.mode, False,
            None, None, None, None, None, None, diagnostics,
        )

    expected = cv2.imread(str(case.expected))
    if expected is None:
        diagnostics["error"] = f"could not read expected image: {case.expected}"
        return Result(
            case.name, case.source, case.mode, False,
            None, None, None, None, None, None, diagnostics,
        )
    expected = cv2.cvtColor(expected, cv2.COLOR_BGR2RGB)

    raw_scores = compare(image, expected)

    corrector = HoughSlantCorrector()
    correction = corrector.correct_slant(image)
    corrected_scores = compare(correction.corrected_image, expected)

    if save_dir is not None:
        save_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(
            str(save_dir / f"{case.name}_raw.png"),
            cv2.cvtColor(image, cv2.COLOR_RGB2BGR),
        )
        cv2.imwrite(
            str(save_dir / f"{case.name}_hough.png"),
            cv2.cvtColor(correction.corrected_image, cv2.COLOR_RGB2BGR),
        )

    return Result(
        name=case.name,
        source=case.source,
        mode=case.mode,
        ok=True,
        raw=raw_scores,
        corrected=corrected_scores,
        hough_angle=round(correction.slant_angle_degrees, 3),
        hough_confidence=round(correction.confidence, 3),
        hough_lines=correction.num_lines_detected,
        delta_ssim=round(corrected_scores["ssim"] - raw_scores["ssim"], 5),
        diagnostics=diagnostics,
    )


def report(results: list[Result]) -> None:
    """Print a per-file report. Per-file, not aggregate: with 13 files a mean
    would hide exactly the regression this harness exists to find."""
    print()
    print("=" * 98)
    print("DECODE QUALITY -- per file, SSIM against paired reference images")
    print("=" * 98)
    print(
        f"{'file':<38} {'source':<9} {'SSIM raw':>9} {'SSIM hough':>11} "
        f"{'delta':>9} {'angle':>8} {'conf':>6}"
    )
    print("-" * 98)

    for r in sorted(results, key=lambda x: (x.source, x.name)):
        if not r.ok:
            err = r.diagnostics.get("error", "failed")
            print(f"{r.name[:37]:<38} {r.source:<9} {'FAILED':>9}   {err}")
            continue

        assert r.raw is not None and r.corrected is not None
        flag = ""
        if r.delta_ssim is not None:
            if r.delta_ssim < -0.001:
                flag = "  <-- HOUGH HURT"
            elif r.delta_ssim > 0.001:
                flag = "  <-- hough helped"

        print(
            f"{r.name[:37]:<38} {r.source:<9} "
            f"{r.raw['ssim']:>9.4f} {r.corrected['ssim']:>11.4f} "
            f"{r.delta_ssim:>+9.4f} {r.hough_angle:>8.2f} {r.hough_confidence:>6.2f}"
            f"{flag}"
        )

    ok = [r for r in results if r.ok]
    print("-" * 98)
    print(f"decoded: {len(ok)}/{len(results)}")

    if ok:
        hurt = [r for r in ok if r.delta_ssim is not None and r.delta_ssim < -0.001]
        helped = [r for r in ok if r.delta_ssim is not None and r.delta_ssim > 0.001]
        neutral = len(ok) - len(hurt) - len(helped)
        print(f"hough helped: {len(helped)}   hurt: {len(hurt)}   no effect: {neutral}")
        if hurt:
            print()
            print("  Files where Hough correction LOWERED the score:")
            for r in hurt:
                print(
                    f"    {r.name}  delta={r.delta_ssim:+.4f}  "
                    f"angle={r.hough_angle}deg  conf={r.hough_confidence}  "
                    f"lines={r.hough_lines}"
                )

    print()
    print("Sync-interval drift (raw material for timing-based correction):")
    for r in sorted(ok, key=lambda x: (x.source, x.name)):
        d = r.diagnostics
        if "sync_interval_drift_slope" in d:
            print(
                f"  {r.name[:44]:<46} mean={d['sync_interval_mean']:>9.1f}  "
                f"std={d['sync_interval_std']:>8.1f}  "
                f"drift/line={d['sync_interval_drift_slope']:>+9.4f}"
            )
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    parser.add_argument("--save-dir", type=Path, help="write decoded images here")
    args = parser.parse_args()

    cases = discover_cases()
    if not cases:
        print("No reference cases found.", file=sys.stderr)
        return 1

    started = time.time()
    results = [run_case(c, args.save_dir) for c in cases]
    elapsed = time.time() - started

    if args.json:
        print(json.dumps({"elapsed_s": round(elapsed, 1),
                          "results": [asdict(r) for r in results]}, indent=2, default=str))
    else:
        report(results)
        print(f"({len(cases)} cases in {elapsed:.1f}s)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
