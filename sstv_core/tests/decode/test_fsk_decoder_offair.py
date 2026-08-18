"""FSKID decoding against real off-air MMSSTV transmissions.

Every other FSKID test builds its signal from SSTeVe's own FSKIDGenerator or
a local tone helper, so encoder and decoder can agree with each other while
both disagree with the air. These two clips are cut from a 20m SpyServer
capture (14.230 MHz, 2026-08-16) and are the only FSKID fixtures that came
off a radio.

They caught two real bugs:

* the start marker is the literal $2A of the spec frame
  "$2A C1 ... CN $01 XSUM" -- the $20 subtraction applies to the callsign
  characters Cx only, not the markers;
* symbols go out LSB-first. The published spec (fskid.txt) diagrams B5
  first, but MMSSTV transmits B0 first, and the XOR checksum only closes
  on these recordings when the decoder reads them that way.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import pytest

from sstv_core.decode.fsk_decoder import FSKIDDecoder

AUDIO_DIR = Path(__file__).resolve().parents[1] / "reference" / "audio" / "fskid"

# (fixture filename, callsign the station actually sent)
OFF_AIR = [
    ("xe2mam_fskid.wav", "XE2MAM"),
    ("va2pgb_fskid.wav", "VA2PGB"),
]


def _load(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        rate = w.getframerate()
        channels = w.getnchannels()
        frames = w.readframes(w.getnframes())
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return audio, rate


@pytest.mark.parametrize(("filename", "expected"), OFF_AIR)
def test_decodes_real_mmsstv_fskid(filename: str, expected: str) -> None:
    """A real MMSSTV FSKID burst yields its callsign with a valid checksum.

    Each clip starts on its preamble. decode() walks the buffer in fixed
    22 ms windows from sample 0, so a burst that starts mid-window can be
    missed -- shifting these clips by as little as 50 ms is enough to lose
    them. See test_decode_tolerates_start_offsets for the size of that
    window and the caller-side workaround.
    """
    audio, rate = _load(AUDIO_DIR / filename)

    result = FSKIDDecoder(sample_rate=rate).decode(audio)

    assert result is not None, f"no FSKID found in {filename}"
    assert result.callsign == expected
    assert result.checksum_valid is True


@pytest.mark.parametrize(("filename", "expected"), OFF_AIR)
def test_decode_tolerates_start_offsets(filename: str, expected: str) -> None:
    """Most start offsets recover the callsign, but not all of them.

    Documents a real limitation: decode() does not hunt for bit phase, so a
    caller handing it an arbitrary slice of tail audio has to retry at a few
    offsets. Recording the behaviour here means a future change that adds
    self-synchronisation shows up as this assertion getting stronger.
    """
    audio, rate = _load(AUDIO_DIR / filename)

    valid = 0
    attempts = 0
    for offset_sec in np.arange(0.0, 1.0, 0.02):
        start = int(offset_sec * rate)
        if start >= len(audio):
            break
        attempts += 1
        result = FSKIDDecoder(sample_rate=rate).decode(audio[start:])
        if result is not None and result.checksum_valid:
            assert result.callsign == expected
            valid += 1

    assert valid > 0, "no start offset decoded the burst"
    # Comfortably met in practice (~40-70%); the floor guards a regression
    # that would leave only a single lucky alignment working.
    assert valid >= attempts * 0.15


def test_start_marker_is_the_literal_2a() -> None:
    """The frame marker is $2A, not $2A put through the character mapping.

    Guards the first of the two off-air bugs directly, so a regression is
    reported as "wrong marker" rather than as a silent decode failure.
    """
    assert FSKIDDecoder.START_MARKER == 0x2A


def test_symbols_are_read_lsb_first() -> None:
    """Bit 0 of a symbol arrives first.

    0x2A is 101010 in binary; sent LSB-first the decoder receives
    [0, 1, 0, 1, 0, 1] and must reassemble the original value.
    """
    decoder = FSKIDDecoder(sample_rate=48000)

    assert decoder._bits_to_symbol([0, 1, 0, 1, 0, 1]) == 0x2A
    assert decoder._bits_to_symbol([1, 0, 0, 0, 0, 0]) == 0x01
