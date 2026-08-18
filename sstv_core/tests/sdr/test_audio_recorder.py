"""AudioRecorder: writing a night of audio without costing an image.

The recorder takes audio from the SpyServer receive thread, which is the
thread that keeps the stream alive. Everything here is about that thread
never waiting and never seeing an exception, and about the file on disk
being readable afterwards.
"""

from __future__ import annotations

import time
import wave
from pathlib import Path

import numpy as np

from sstv_core.sdr.audio_recorder import AudioRecorder


def _drain(recorder: AudioRecorder, expected_frames: int, timeout: float = 5.0) -> None:
    """Wait for the writer thread to catch up, or give up and let the assert talk."""
    deadline = time.monotonic() + timeout
    while recorder.frames_written < expected_frames and time.monotonic() < deadline:
        time.sleep(0.01)


def test_writes_a_readable_wav(tmp_path: Path) -> None:
    """What comes back off disk is a real 16-bit mono WAV at the right rate."""
    path = tmp_path / "session.wav"
    recorder = AudioRecorder(path, 48000)
    recorder.start()

    tone = np.sin(2 * np.pi * 1000 * np.arange(48000) / 48000).astype(np.float32)
    recorder.write(tone)
    _drain(recorder, len(tone))
    recorder.stop()

    with wave.open(str(path), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2
        assert handle.getframerate() == 48000
        assert handle.getnframes() == len(tone)


def test_recorded_audio_survives_the_round_trip(tmp_path: Path) -> None:
    """The samples read back match what went in, within int16 resolution."""
    path = tmp_path / "tone.wav"
    recorder = AudioRecorder(path, 48000)
    recorder.start()

    tone = (0.5 * np.sin(2 * np.pi * 1000 * np.arange(4800) / 48000)).astype(np.float32)
    recorder.write(tone)
    _drain(recorder, len(tone))
    recorder.stop()

    with wave.open(str(path), "rb") as handle:
        raw = handle.readframes(handle.getnframes())
    read_back = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32767.0

    assert np.max(np.abs(read_back - tone)) < 1e-3


def test_write_before_start_is_ignored(tmp_path: Path) -> None:
    """Audio arriving before start() is dropped, not an error.

    The receive thread must never see an exception from here.
    """
    recorder = AudioRecorder(tmp_path / "unused.wav", 48000)

    recorder.write(np.zeros(128, dtype=np.float32))

    assert recorder.frames_written == 0
    assert not (tmp_path / "unused.wav").exists()


def test_write_after_stop_is_ignored(tmp_path: Path) -> None:
    """Late audio from a thread still winding down does not raise."""
    path = tmp_path / "closed.wav"
    recorder = AudioRecorder(path, 48000)
    recorder.start()
    recorder.write(np.zeros(128, dtype=np.float32))
    _drain(recorder, 128)
    recorder.stop()
    written = recorder.frames_written

    recorder.write(np.ones(128, dtype=np.float32))

    assert recorder.frames_written == written


def test_empty_block_is_ignored(tmp_path: Path) -> None:
    """A demodulator that produced nothing this pass is not an error."""
    recorder = AudioRecorder(tmp_path / "empty.wav", 48000)
    recorder.start()

    recorder.write(np.array([], dtype=np.float32))
    recorder.stop()

    assert recorder.frames_written == 0


def test_a_bad_block_never_reaches_the_caller(tmp_path: Path) -> None:
    """Anything unconvertible is swallowed, because the caller is the radio.

    A recording bug that propagated here would take down the stream that
    keeps the decode alive.
    """
    recorder = AudioRecorder(tmp_path / "bad.wav", 48000)
    recorder.start()

    recorder.write("not audio")  # type: ignore[arg-type]

    recorder.stop()


def test_stop_is_idempotent(tmp_path: Path) -> None:
    """Stopping twice is what happens when teardown paths overlap."""
    recorder = AudioRecorder(tmp_path / "twice.wav", 48000)
    recorder.start()
    recorder.write(np.zeros(256, dtype=np.float32))
    _drain(recorder, 256)

    recorder.stop()
    recorder.stop()

    with wave.open(str(tmp_path / "twice.wav"), "rb") as handle:
        assert handle.getnframes() == 256


def test_duration_reports_what_was_written(tmp_path: Path) -> None:
    """The CLI reports this at the end of a session, so it has to be real."""
    recorder = AudioRecorder(tmp_path / "dur.wav", 48000)
    recorder.start()

    recorder.write(np.zeros(48000 * 2, dtype=np.float32))
    _drain(recorder, 48000 * 2)
    recorder.stop()

    assert abs(recorder.duration_sec - 2.0) < 0.01


def test_creates_the_parent_directory(tmp_path: Path) -> None:
    """A path into a directory that does not exist yet still records."""
    path = tmp_path / "sessions" / "tonight" / "band.wav"
    recorder = AudioRecorder(path, 48000)

    recorder.start()
    recorder.write(np.zeros(128, dtype=np.float32))
    _drain(recorder, 128)
    recorder.stop()

    assert path.exists()


def test_clipping_does_not_wrap(tmp_path: Path) -> None:
    """Audio outside [-1, 1] clips rather than wrapping to the other rail.

    A hot gain that wrapped would turn loud audio into noise that looks like
    a signal, which is worse than a clipped recording.
    """
    path = tmp_path / "hot.wav"
    recorder = AudioRecorder(path, 48000)
    recorder.start()

    recorder.write(np.array([2.0, -2.0, 0.0], dtype=np.float32))
    _drain(recorder, 3)
    recorder.stop()

    with wave.open(str(path), "rb") as handle:
        raw = handle.readframes(handle.getnframes())
    samples = np.frombuffer(raw, dtype="<i2")

    assert samples[0] > 32000
    assert samples[1] < -32000
