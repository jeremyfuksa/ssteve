"""`decode --record`: keeping the night, not just the pictures.

Recording turns a decode session into an overnight listen -- the audio is
kept so it can be re-decoded when a decoder improves, and it comes off the
same demodulated stream the decoder reads rather than a second radio path.

The lifetimes are the part that broke in practice, twice, and that unit
tests of AudioRecorder could not see. RXManager calls stop_input() from its
own finally after every decoded image, so a recorder torn down there dies
partway through the night and the session reports nothing. Recording is
session-scoped: stop_input() leaves it alone and close_recording() ends it.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
from types import SimpleNamespace

import pytest

# importlib, not `import sstv_core.cli.main as cli_main`: the package does
# `from .main import main`, so the plain import binds the function and not
# the module. test_cli_spyserver hit this first.
cli_main = importlib.import_module("sstv_core.cli.main")


def _args(**overrides: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "mode": None,
        "device": None,
        "file": None,
        "scan": False,
        "record": None,
        "spyserver": "radio.local",
        "band": None,
        "frequency": None,
        "gain": None,
        "timeout": 5,
        "output": None,
        "monitor_stream": None,
        "verbose": False,
        "json": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class _FakeRecorder:
    """Stands in for AudioRecorder, and remembers whether it was stopped."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.duration_sec = 42.0
        self.dropped_blocks = 3
        self.stopped = False


class _FakeSource:
    """A SpyServerSource that detaches its recorder on stop, as the real one does."""

    sample_rate = 48000

    def __init__(self, record_path: str | None = None, **kwargs: object) -> None:
        self.stream_failure = None
        self.dropped_frames = 0
        self.resolved_gain = 6
        self.max_gain = 8
        self.audio_recorder = _FakeRecorder(record_path) if record_path else None

    def start_input(self, device_index=None, callback=None, buffer_size=480000) -> None:
        pass

    def stop_input(self) -> None:
        # Deliberately leaves the recorder alone, as the real source does:
        # RXManager calls this after every image, and a recording spans the
        # whole session.
        pass

    def close_recording(self):
        """End the recording and hand it back, as the real source does."""
        recorder = self.audio_recorder
        self.audio_recorder = None
        if recorder is not None:
            recorder.stopped = True
        return recorder

    def get_input_buffer(self):
        from sstv_core.audio.ring_buffer import AudioRingBuffer

        return AudioRingBuffer(max_samples=48000)

    def get_input_levels(self):
        return SimpleNamespace(rms=0.01, peak=0.04, is_clipping=False)


@pytest.fixture
def captured_events(monkeypatch):
    events: list[tuple[str, dict]] = []
    real = cli_main.log_event

    def spy(event_type: str, **kwargs: object) -> None:
        events.append((event_type, kwargs))
        real(event_type, **kwargs)

    monkeypatch.setattr(cli_main, "log_event", spy)
    return events


@pytest.fixture
def fake_source(monkeypatch):
    import sstv_core.sdr.source as source_module

    built: dict = {}

    def factory(*args: object, **kwargs: object) -> _FakeSource:
        source = _FakeSource(**kwargs)  # type: ignore[arg-type]
        built["kwargs"] = kwargs
        built["source"] = source
        built["recorder"] = source.audio_recorder
        return source

    monkeypatch.setattr(source_module, "SpyServerSource", factory)
    return built


def test_record_path_reaches_the_source(fake_source, captured_events, tmp_path) -> None:
    """--record is handed to the source, which is what opens the file."""
    target = tmp_path / "tonight.wav"

    cli_main._decode_spyserver(_args(record=str(target), timeout=1))

    assert fake_source["kwargs"]["record_path"] == str(target)


def test_session_reports_what_it_recorded(
    fake_source, captured_events, tmp_path
) -> None:
    """The recording is reported after the session, with its real duration.

    Regression: the CLI read `audio_recorder` after stop_input(), which
    detaches it, so this event never fired on a real run.
    """
    target = tmp_path / "tonight.wav"

    cli_main._decode_spyserver(_args(record=str(target), timeout=1))

    saved = [kwargs for name, kwargs in captured_events if name == "recording_saved"]
    assert saved, "the session never reported its recording"
    assert saved[0]["output_path"] == str(target)
    assert saved[0]["duration_sec"] == 42.0
    assert saved[0]["dropped_blocks"] == 3


def test_the_recording_is_closed_before_it_is_reported(
    fake_source, captured_events, tmp_path
) -> None:
    """stop() has run by the time the duration is read.

    wave writes its length fields on close, so a duration read from a file
    still open is a number nothing else agrees with.
    """
    cli_main._decode_spyserver(_args(record=str(tmp_path / "x.wav"), timeout=1))

    recorder = fake_source["recorder"]
    assert recorder.stopped
    saved = [kwargs for name, kwargs in captured_events if name == "recording_saved"]
    assert saved


def test_stopping_input_does_not_end_the_recording(
    fake_source, captured_events, tmp_path
) -> None:
    """A decode finishing mid-session must not close the night's recording.

    RXManager calls stop_input() from its own finally after every image. A
    recorder torn down there would leave an overnight session holding only
    the audio up to its first picture.
    """
    source = _FakeSource(record_path=str(tmp_path / "night.wav"))
    recorder = source.audio_recorder

    source.stop_input()

    assert source.audio_recorder is recorder
    assert recorder is not None and not recorder.stopped


def test_no_record_flag_reports_nothing(fake_source, captured_events) -> None:
    """A plain decode says nothing about recordings."""
    cli_main._decode_spyserver(_args(timeout=1))

    assert not [name for name, _ in captured_events if name == "recording_saved"]
    assert fake_source["kwargs"]["record_path"] is None


def test_recording_switches_decoding_to_continuous() -> None:
    """--record stops the session quitting at the first picture.

    An overnight recording that ended at the first transmission would keep
    a few minutes of a whole night.
    """
    source = inspect.getsource(cli_main._decode_spyserver)

    assert "continuous = record_path is not None" in source
    assert "deadline" in source
