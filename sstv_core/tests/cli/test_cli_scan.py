"""`decode --file --scan` over recordings longer than one transmission.

`--file` on its own reads the first five seconds looking for a VIS header,
which is right for a WAV holding a single transmission and useless for a band
recording: a ten-hour capture reported "no VIS header" while holding ten
transmissions. `--scan` is the other shape of input.
"""

from __future__ import annotations

import argparse
import wave
from pathlib import Path

import numpy as np
import pytest

from sstv_core.cli.main import _decode_file, _find_leader_candidates

REFERENCE = Path(__file__).resolve().parents[1] / "reference" / "audio"
ROBOT36 = REFERENCE / "robot36" / "07_lx95.wav"


def _args(**overrides: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "file": str(ROBOT36),
        "scan": False,
        "mode": None,
        "output": None,
        "verbose": False,
        "json": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _write_wav(path: Path, audio: np.ndarray, rate: int = 48000) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes((np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16).tobytes())


def _tone(freq: float, seconds: float, rate: int = 48000) -> np.ndarray:
    t = np.arange(int(rate * seconds)) / rate
    return np.sin(2 * np.pi * freq * t).astype(np.float32)


def test_scan_decodes_a_transmission_that_is_not_at_the_start(tmp_path: Path) -> None:
    """A transmission preceded by minutes of noise still gets decoded.

    This is the case plain --file cannot reach: the VIS header sits well past
    the five-second window it searches.
    """
    with wave.open(str(ROBOT36), "rb") as handle:
        rate = handle.getframerate()
        transmission = np.frombuffer(
            handle.readframes(handle.getnframes()), dtype=np.int16
        ).astype(np.float32) / 32768.0

    rng = np.random.default_rng(1234)
    lead_in = rng.normal(0, 0.02, int(90 * rate)).astype(np.float32)
    recording = tmp_path / "band.wav"
    _write_wav(recording, np.concatenate([lead_in, transmission]), rate)

    out = tmp_path / "out"
    assert _decode_file(_args(file=str(recording), scan=True, output=str(out))) == 0

    images = sorted(tmp_path.glob("out_*.png"))
    assert len(images) == 1
    # Named for the second it starts at, so the image can be traced back to
    # its place in the recording.
    assert "robot_36" in images[0].name


def test_plain_file_misses_that_same_transmission(tmp_path: Path) -> None:
    """Without --scan the same recording reports no VIS header.

    Documents the boundary deliberately: --file is a single-transmission
    tool, and the fix was to add --scan rather than change what --file does.
    """
    with wave.open(str(ROBOT36), "rb") as handle:
        rate = handle.getframerate()
        transmission = np.frombuffer(
            handle.readframes(handle.getnframes()), dtype=np.int16
        ).astype(np.float32) / 32768.0

    rng = np.random.default_rng(1234)
    lead_in = rng.normal(0, 0.02, int(90 * rate)).astype(np.float32)
    recording = tmp_path / "band.wav"
    _write_wav(recording, np.concatenate([lead_in, transmission]), rate)

    assert _decode_file(_args(file=str(recording), scan=False)) == 2


def test_scan_reports_when_a_recording_holds_nothing(tmp_path: Path) -> None:
    """Noise alone exits 2, not 0."""
    rng = np.random.default_rng(7)
    quiet = tmp_path / "quiet.wav"
    _write_wav(quiet, rng.normal(0, 0.02, 48000 * 20).astype(np.float32))

    assert _decode_file(_args(file=str(quiet), scan=True)) == 2


def test_leader_prefilter_finds_a_sustained_1900hz_tone(tmp_path: Path) -> None:
    """The cheap pre-filter fires on a VIS leader and ignores noise.

    The pre-filter is what makes scanning hours of audio affordable, so its
    two failure modes both matter: missing a real leader loses a
    transmission, and firing on noise sends the expensive detector chasing
    nothing.
    """
    rate = 48000
    rng = np.random.default_rng(99)
    audio = np.concatenate(
        [
            rng.normal(0, 0.02, rate * 2).astype(np.float32),
            _tone(1900.0, 0.3, rate),
            rng.normal(0, 0.02, rate * 2).astype(np.float32),
        ]
    )
    path = tmp_path / "leader.wav"
    _write_wav(path, audio, rate)

    with wave.open(str(path), "rb") as handle:
        found = _find_leader_candidates(handle, rate, 1)

    assert len(found) == 1
    assert found[0] == pytest.approx(2.0, abs=0.2)


def test_leader_prefilter_ignores_noise(tmp_path: Path) -> None:
    """Band noise on its own produces no candidates."""
    rate = 48000
    rng = np.random.default_rng(5)
    path = tmp_path / "noise.wav"
    _write_wav(path, rng.normal(0, 0.05, rate * 30).astype(np.float32), rate)

    with wave.open(str(path), "rb") as handle:
        assert _find_leader_candidates(handle, rate, 1) == []


def test_scan_does_not_read_the_whole_file_at_once(tmp_path: Path) -> None:
    """Scanning streams, so recording length is not bounded by memory.

    The capture that prompted this was 8.6GB; reading it whole is what the
    old path did.
    """
    rate = 48000
    rng = np.random.default_rng(3)
    long_recording = tmp_path / "long.wav"
    _write_wav(long_recording, rng.normal(0, 0.02, rate * 600).astype(np.float32), rate)

    reads: list[int] = []
    real_readframes = wave.Wave_read.readframes

    def counting_readframes(self: wave.Wave_read, n: int) -> bytes:
        reads.append(n)
        return real_readframes(self, n)

    wave.Wave_read.readframes = counting_readframes  # type: ignore[method-assign]
    try:
        _decode_file(_args(file=str(long_recording), scan=True))
    finally:
        wave.Wave_read.readframes = real_readframes  # type: ignore[method-assign]

    assert reads, "scan read nothing"
    assert max(reads) < rate * 600
