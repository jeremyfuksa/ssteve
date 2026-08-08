"""CLI honesty tests: --file auto-detect, real encode, working entry points.

The 2026-08-07 audit found the CLI decoded every file as ScottieS1 while its
help text promised auto-detection, and that `encode` emitted a fully
fabricated success event stream without touching an encoder. These tests
exercise the CLI as a subprocess-free caller: cmd handlers via main(argv).
"""

from __future__ import annotations

import json
import wave
from pathlib import Path

import numpy as np
import pytest

from sstv_core.cli.main import main
from sstv_core.encode.martin_encoder import MartinM1Encoder


def _write_wav(path: Path, audio: np.ndarray, rate: int) -> None:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm.tobytes())


def _gradient_card(width: int, height: int) -> np.ndarray:
    x = np.linspace(0, 255, width)
    y = np.linspace(0, 255, height)
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:, :, 0] = np.tile(x, (height, 1)).astype(np.uint8)
    img[:, :, 1] = np.tile(y[:, None], (1, width)).astype(np.uint8)
    img[:, :, 2] = ((x[None, :] + y[:, None]) / 2).astype(np.uint8)
    return img


@pytest.fixture
def martin_wav(tmp_path: Path) -> tuple[Path, np.ndarray]:
    enc = MartinM1Encoder()
    img = _gradient_card(enc.config.width, enc.config.height)
    audio = enc.encode_image(img, include_vis=True)
    wav = tmp_path / "martin.wav"
    _write_wav(wav, audio, enc.config.sample_rate)
    return wav, img


def test_file_decode_autodetects_martin_from_vis(martin_wav, tmp_path):
    """No --mode: the VIS header, not a hardcoded default, picks the decoder."""
    wav, img = martin_wav
    out = tmp_path / "decoded.png"
    rc = main(["decode", "--file", str(wav), "--output", str(out)])
    assert rc == 0
    assert out.exists()

    import cv2

    decoded = cv2.cvtColor(cv2.imread(str(out)), cv2.COLOR_BGR2RGB).astype(np.float64)
    o = img[10:-10, 10:-10].astype(np.float64)
    d = decoded[10:-10, 10:-10]
    # Decoded-as-ScottieS1 audio scores ~0.15 here; a correct Martin decode
    # scores >0.95. Channel order is part of what this asserts.
    for ch in range(3):
        corr = float(np.corrcoef(o[:, :, ch].ravel(), d[:, :, ch].ravel())[0, 1])
        assert corr >= 0.95, f"channel {ch} corr {corr:.3f}"


def test_file_decode_without_vis_fails_honestly(tmp_path):
    """Noise with no VIS header: an honest error, not a ScottieS1 guess."""
    rng = np.random.default_rng(1)
    wav = tmp_path / "noise.wav"
    _write_wav(wav, rng.normal(0, 0.1, 48000 * 3).astype(np.float32), 48000)
    rc = main(["decode", "--file", str(wav)])
    assert rc != 0


def test_encode_writes_real_wav_that_roundtrips(tmp_path):
    """encode --output produces audio the decoder actually accepts."""
    import cv2

    img = _gradient_card(320, 256)
    src = tmp_path / "card.png"
    cv2.imwrite(str(src), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))

    wav = tmp_path / "out.wav"
    rc = main(["encode", "--image", str(src), "--mode", "MartinM1", "--output", str(wav)])
    assert rc == 0
    assert wav.exists()

    with wave.open(str(wav), "rb") as handle:
        duration = handle.getnframes() / handle.getframerate()
    # Martin M1 nominal ~115s image + ~0.9s VIS header.
    assert 110 < duration < 121

    out = tmp_path / "back.png"
    rc = main(["decode", "--file", str(wav), "--output", str(out)])
    assert rc == 0
    decoded = cv2.cvtColor(cv2.imread(str(out)), cv2.COLOR_BGR2RGB).astype(np.float64)
    o = img[10:-10, 10:-10].astype(np.float64)
    d = decoded[10:-10, 10:-10]
    for ch in range(3):
        corr = float(np.corrcoef(o[:, :, ch].ravel(), d[:, :, ch].ravel())[0, 1])
        assert corr >= 0.95, f"channel {ch} corr {corr:.3f}"


def test_encode_without_output_or_device_fails(tmp_path, capsys):
    """No destination: an error event and nonzero exit, never fake success."""
    import cv2

    src = tmp_path / "card.png"
    cv2.imwrite(str(src), np.zeros((10, 10, 3), dtype=np.uint8))
    rc = main(["--json", "encode", "--image", str(src)])
    assert rc != 0
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip().startswith("{")]
    assert not any(e.get("event") == "transmit_complete" for e in events)


def test_console_script_entry_points_exist():
    """pyproject's sstv-decode/sstv-encode targets are real callables."""
    from sstv_core import cli

    assert callable(cli.decode)
    assert callable(cli.encode)
