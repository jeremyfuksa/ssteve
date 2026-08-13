"""SSTV over the SDR path, end to end, with no server and no radio.

Takes a real Scottie S1 recording, modulates it up as USB IQ, and feeds it
through SpyServerSource into the real RXManager. If this passes, the SDR
path produces audio the decoder actually accepts -- protocol, demodulator,
client seam, ring buffer, VIS detection, sync detection and scanline decode
all in one line.

Every other SpyServerSource test drives a fake client with synthetic tones.
This is the only committed test that puts a real transmission through it and
checks the picture that comes out.

Two things about this test are load-bearing and easy to "clean up" into a
test that no longer works:

PACING. The feeder throttles on ring-buffer occupancy, not on wall clock.
It has to. CorrelationVISDetector matches against a rolling window of
65,520 samples (1.365 s at 48 kHz), and it only ever sees what RXManager
pops. Let the feeder run free and the backlog exceeds that window, so the
VIS header is already scrolled out of the correlation buffer by the time
the detector looks at it -- measured here: a HIGH_WATER of 65,536 decodes
nothing at all, while 32,768 decodes cleanly. A network source that stalls
and then bursts produces exactly that backlog, which is why the source
documents the same hazard.

GROUP DELAY. The demodulator's filter chain delays the audio by a constant,
so the decoded picture sits about 20 px right of a direct-from-file decode.
That is a fixed offset, not damage, and the comparison below corrects for
it before measuring. Comparing raw pixels scores ~0.51 on a picture that is
plainly the same bear.
"""

from __future__ import annotations

import asyncio
import wave
from math import gcd
from pathlib import Path

import numpy as np
import pytest
from scipy import signal as sp_signal

from sstv_core.decode.rx_manager import RXManager
from sstv_core.sdr.source import SpyServerSource
from sstv_core.sdr.spyserver.client import SpyServerError

REFERENCE = (
    Path(__file__).resolve().parents[1]
    / "reference"
    / "audio"
    / "mmsstv"
    / "scottie_s1_bear_je3hht.wav"
)

# IQ rate. 96 kHz is a real SpyServer stage rate and, unlike the engine's own
# 48 kHz, it makes the demodulator actually decimate and resample rather than
# pass audio straight through -- which is the part worth regression-testing.
IQ_RATE = 96_000

# Feeder high-water mark, in demodulated 48 kHz samples. Must stay well under
# CorrelationVISDetector's 65,520-sample window; see the PACING note above.
# Raising this makes the test faster right up until it makes it fail.
HIGH_WATER_SAMPLES = 32_768

# Demodulated samples delivered per pump.
PUMP_AUDIO_SAMPLES = 8_192

# The recording is 115.08 s of one Scottie S1 frame. Trimming to a whole 115 s
# costs nothing (the transmission ends at 113.6 s) and cuts scipy.signal.hilbert
# from 4.7 s to 0.3 s -- the ragged length lands on a bad FFT size.
TRIM_SECONDS = 115


def _load_reference() -> tuple[np.ndarray, int]:
    with wave.open(str(REFERENCE), "rb") as wav:
        rate = wav.getframerate()
        channels = wav.getnchannels()
        frames = wav.readframes(wav.getnframes())
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return audio[: rate * TRIM_SECONDS], rate


def _audio_to_usb_iq(audio: np.ndarray, audio_rate: int, iq_rate: int) -> np.ndarray:
    """Modulate real audio up into complex IQ as an upper-sideband signal.

    The analytic signal (audio + j*hilbert(audio)) has energy only on the
    positive-frequency side, which is exactly what USB means.

    The resample ratio is the reduced rational one. This reference is 11025 Hz
    and the IQ rate is 96000, so the integer ratio some callers reach for
    (iq_rate // audio_rate) is 8 and would silently produce an 88.2 kHz stream
    labelled 96 kHz -- a 9% rate error, which slants the picture.
    """
    divisor = gcd(iq_rate, audio_rate)
    upsampled = sp_signal.resample_poly(
        audio, iq_rate // divisor, audio_rate // divisor
    )
    return np.asarray(sp_signal.hilbert(upsampled), dtype=np.complex64)


class ScriptedClient:
    """Feeds prepared IQ to the source the way a server would.

    Conforms to sstv_core.sdr.source._Client: sample_rate, dropped_frames and
    stream_error are read-only properties, because that is how the real
    SpyServerClient exposes them.
    """

    def __init__(self, iq: np.ndarray, sample_rate: int) -> None:
        self._sample_rate = sample_rate
        self._iq = iq
        self._on_iq: object | None = None
        self.offset = 0
        self.closed = False

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def dropped_frames(self) -> int:
        return 0

    @property
    def stream_error(self) -> SpyServerError | None:
        return None

    def connect(self) -> None:
        pass

    def tune(self, frequency_hz: int) -> None:
        pass

    def start_streaming(self, on_iq, gain: int = 0) -> None:
        self._on_iq = on_iq

    def stop_streaming(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True

    def pump(self, samples: int) -> int:
        """Deliver one block; returns how many IQ samples were sent."""
        chunk = self._iq[self.offset : self.offset + samples]
        if len(chunk) == 0 or self._on_iq is None:
            return 0
        self._on_iq(chunk)  # type: ignore[operator]
        self.offset += len(chunk)
        return len(chunk)


def _best_aligned_correlation(
    decoded: np.ndarray, control: np.ndarray
) -> tuple[float, int]:
    """Correlation of two pictures after removing a constant pixel shift.

    Returns (correlation, dx). The demodulator's group delay shifts the whole
    picture sideways by a fixed amount; searching it out is the difference
    between measuring fidelity and measuring alignment.
    """
    best_corr = -1.0
    best_dx = 0
    for dx in range(-30, 31):
        shifted = np.roll(decoded, -dx, axis=1)
        # Crop the columns the roll wrapped, plus the edge rows that carry
        # sync-timing slop in any decode.
        a = control[10:-10, 32:-32].astype(np.float64).ravel()
        b = shifted[10:-10, 32:-32].astype(np.float64).ravel()
        corr = float(np.corrcoef(a, b)[0, 1])
        if corr > best_corr:
            best_corr = corr
            best_dx = dx
    return best_corr, best_dx


@pytest.mark.integration
async def test_scottie_s1_decodes_through_the_sdr_path(tmp_path):
    """A real Scottie S1 transmission survives modulation and the SDR path."""
    audio, audio_rate = _load_reference()
    iq = _audio_to_usb_iq(audio, audio_rate, IQ_RATE)

    client = ScriptedClient(iq, IQ_RATE)
    source = SpyServerSource("fake.test", frequency_hz=14_230_000, client=client)
    # RXManager.receive() calls start_input() itself; starting it here too
    # would build a second ring buffer and throw the first one away.
    rx = RXManager(stream_manager=source, save_directory=tmp_path)

    iq_per_pump = PUMP_AUDIO_SAMPLES * (IQ_RATE // 48_000)
    exhausted = asyncio.Event()

    async def feeder() -> None:
        while True:
            buffer = source.get_input_buffer()
            if buffer is not None and len(buffer) < HIGH_WATER_SAMPLES:
                if client.pump(iq_per_pump) == 0:
                    exhausted.set()
                    return
            # sleep(0) yields to RXManager without adding wall-clock delay:
            # the throttle is buffer occupancy, not time.
            await asyncio.sleep(0)

    feed_task = asyncio.create_task(feeder())
    try:
        result = await asyncio.wait_for(
            rx.receive(timeout_sec=45.0, save_image=True), timeout=300
        )
    finally:
        feed_task.cancel()
        source.stop_input()

    assert result is not None, "the SDR path decoded nothing"
    assert Path(result).exists()

    from PIL import Image

    # Read with PIL, not cv2: ImageSaver writes RGB through PIL, and cv2.imread
    # would hand back BGR. Comparing that to the control's RGB scores 0.71 on a
    # picture that is actually a 0.96 match -- a channel swap wearing the
    # costume of a broken signal path.
    decoded = np.asarray(Image.open(result).convert("RGB"))
    assert decoded.shape[0] >= 200 and decoded.shape[1] >= 300
    # A real decode has structure; a failed one is flat.
    assert float(decoded.std()) > 20.0

    # The picture has to be the right picture, not merely a textured one.
    # Control is the same file decoded straight from disk at its native rate,
    # so this measures what the SDR path costs and nothing else.
    control = _decode_reference_directly(audio, audio_rate)
    corr, dx = _best_aligned_correlation(decoded, control)
    assert corr >= 0.90, (
        f"SDR decode correlates {corr:.4f} (shift {dx} px) with the direct "
        "decode of the same recording -- the SDR path is degrading the audio"
    )


def _decode_reference_directly(audio: np.ndarray, audio_rate: int) -> np.ndarray:
    """Decode the same recording from memory, bypassing the SDR path entirely.

    The control arm. Uses the decoder stack directly at the file's native rate,
    which is what `sstv-decode --file` does.
    """
    from sstv_core.decode.correlation_vis_detector import (
        CorrelationVISConfig,
        CorrelationVISDetector,
    )
    from sstv_core.decode.scottie_decoder import ScottieS1Config, ScottieS1Decoder
    from sstv_core.decode.sync_detector import SyncPulseDetector

    detector = CorrelationVISDetector(CorrelationVISConfig(sample_rate=audio_rate))
    found = None
    for start in range(0, min(len(audio), audio_rate * 5), 4096):
        found = detector.process_samples(audio[start : start + 4096])
        if found is not None:
            break
    assert found is not None, "the control decode could not find the VIS header"
    assert found.mode.name == "SCOTTIE_S1"

    config = ScottieS1Config(sample_rate=audio_rate)
    sync = SyncPulseDetector(sample_rate=audio_rate)
    sync.detect_in_buffer(audio)
    line_ms = 1000.0 * config.total_line_samples / audio_rate
    positions = sync.get_sync_positions(line_duration_ms=line_ms)
    assert positions, "the control decode found no sync pulses"

    decoder = ScottieS1Decoder(config)
    for _ in decoder.decode_stream(iter([audio]), positions):
        pass
    image = decoder.get_image()
    assert image is not None, "the control decode produced no image"
    return np.asarray(image)
