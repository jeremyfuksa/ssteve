"""The spectrum producer behind the waterfall (#53).

PRODUCT.md calls a 300-3000 Hz waterfall non-negotiable, and it is how an
operator tunes -- so this has to produce frames before a decode starts,
not only during one. frontend-contract.md 20.4 sets the range, the 1900 Hz
centre, and a 10-20 Hz update rate.

The contract is deliberately narrow. Magnitudes are sliced to the SSTV
band at the producer and quantised to integer dBFS: at 48 kHz with 1024
bins, 300-3000 Hz is ~58 of 512 bins, so sending all of them would ship
mostly-empty spectrum above 3 kHz at 15 frames a second. Sub-dB precision
is not renderable on a waterfall either.
"""

from __future__ import annotations

import numpy as np
import pytest

from sstv_core.dsp.spectrum import (
    SPECTRUM_MAX_HZ,
    SPECTRUM_MIN_HZ,
    SYNC_HZ,
    SpectrumProducer,
)

RATE = 48_000


def _tone(hz: float, samples: int, amplitude: float = 0.5) -> np.ndarray:
    t = np.arange(samples) / RATE
    return (amplitude * np.sin(2 * np.pi * hz * t)).astype(np.float32)


def _noise(samples: int, amplitude: float = 0.001, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return (amplitude * rng.standard_normal(samples)).astype(np.float32)


class TestFrameShape:
    def test_a_frame_covers_the_sstv_band_and_no_more(self) -> None:
        producer = SpectrumProducer(sample_rate=RATE, fft_size=1024)
        frame = producer.compute(_noise(1024))

        assert frame is not None
        assert frame.start_hz >= SPECTRUM_MIN_HZ - frame.bin_hz
        end_hz = frame.start_hz + len(frame.magnitudes_db) * frame.bin_hz
        assert end_hz <= SPECTRUM_MAX_HZ + frame.bin_hz

    def test_magnitudes_are_integers(self) -> None:
        """Quantised on purpose: a waterfall cannot draw sub-dB steps."""
        producer = SpectrumProducer(sample_rate=RATE, fft_size=1024)
        frame = producer.compute(_noise(1024))

        assert frame is not None
        assert all(isinstance(v, int) for v in frame.magnitudes_db)

    def test_the_band_is_far_smaller_than_the_full_spectrum(self) -> None:
        """Why slicing happens at the producer rather than the frontend."""
        producer = SpectrumProducer(sample_rate=RATE, fft_size=1024)
        frame = producer.compute(_noise(1024))

        assert frame is not None
        assert len(frame.magnitudes_db) < 1024 // 2 // 4

    @pytest.mark.parametrize("fft_size", [512, 1024, 2048])
    def test_every_configured_fft_size_works(self, fft_size: int) -> None:
        """config caps waterfall_fft_size to 512-2048; all three must run."""
        producer = SpectrumProducer(sample_rate=RATE, fft_size=fft_size)
        frame = producer.compute(_noise(fft_size))

        assert frame is not None
        assert len(frame.magnitudes_db) > 0

    def test_a_short_buffer_yields_no_frame(self) -> None:
        """Better no frame than a frame padded out of nothing."""
        producer = SpectrumProducer(sample_rate=RATE, fft_size=1024)
        assert producer.compute(_noise(100)) is None


class TestItMeasuresTheRightThing:
    def test_a_tone_lands_in_its_own_bin(self) -> None:
        producer = SpectrumProducer(sample_rate=RATE, fft_size=2048)
        frame = producer.compute(_tone(1500.0, 2048))

        assert frame is not None
        assert frame.peak_hz == pytest.approx(1500.0, abs=frame.bin_hz)

    def test_a_louder_tone_reads_higher(self) -> None:
        producer = SpectrumProducer(sample_rate=RATE, fft_size=2048)
        quiet = producer.compute(_tone(1500.0, 2048, amplitude=0.01))
        loud = producer.compute(_tone(1500.0, 2048, amplitude=0.5))

        assert quiet is not None and loud is not None
        assert max(loud.magnitudes_db) > max(quiet.magnitudes_db) + 10

    def test_a_tone_outside_the_band_is_not_reported_as_a_peak(self) -> None:
        """8 kHz is real energy the waterfall does not show. It must not
        become the peak an operator is told to tune to."""
        producer = SpectrumProducer(sample_rate=RATE, fft_size=2048)
        frame = producer.compute(_tone(8000.0, 2048) + _noise(2048))

        assert frame is not None
        assert frame.peak_hz is None or frame.peak_hz <= SPECTRUM_MAX_HZ

    def test_silence_does_not_crash_on_log_of_zero(self) -> None:
        producer = SpectrumProducer(sample_rate=RATE, fft_size=1024)
        frame = producer.compute(np.zeros(1024, dtype=np.float32))

        assert frame is not None
        assert all(np.isfinite(v) for v in frame.magnitudes_db)


class TestSyncIsItsOwnSignal:
    """frontend-contract 20.4: the 1200 Hz sync pulse "must not read as just a
    strong bin". The event therefore carries the detection -- leaving the
    frontend to infer it from magnitudes is what that line rules out.
    """

    def test_a_sync_tone_is_flagged(self) -> None:
        producer = SpectrumProducer(sample_rate=RATE, fft_size=2048)
        frame = producer.compute(_tone(SYNC_HZ, 2048) + _noise(2048))

        assert frame is not None
        assert frame.sync_detected is True

    def test_noise_alone_is_not_sync(self) -> None:
        producer = SpectrumProducer(sample_rate=RATE, fft_size=2048)
        frame = producer.compute(_noise(2048, amplitude=0.05))

        assert frame is not None
        assert frame.sync_detected is False

    def test_a_tone_elsewhere_in_the_band_is_not_sync(self) -> None:
        """1900 Hz is the SSTV centre and is loud constantly. Reading it as
        sync would light the indicator through every transmission."""
        producer = SpectrumProducer(sample_rate=RATE, fft_size=2048)
        frame = producer.compute(_tone(1900.0, 2048) + _noise(2048))

        assert frame is not None
        assert frame.sync_detected is False


class TestUpdateRate:
    """10-20 Hz per frontend-contract 20.4. The producer decides, not the
    caller: audio arrives in whatever blocks the source hands over, and a
    48 kHz stream in 1024-sample chunks would otherwise emit 47 frames a
    second."""

    def test_frames_are_throttled_to_the_spec_rate(self) -> None:
        producer = SpectrumProducer(sample_rate=RATE, fft_size=1024, update_hz=15.0)
        emitted = sum(
            1
            for _ in range(47)  # ~1 s of 1024-sample blocks at 48 kHz
            if producer.feed(_noise(1024)) is not None
        )

        assert 10 <= emitted <= 20, f"emitted {emitted} frames in ~1 s, want 10-20"

    def test_the_throttle_counts_audio_not_wall_clock(self) -> None:
        """A file scanned faster than real time must not thin the waterfall.

        Wall-clock pacing would tie row spacing to how fast the machine
        reads the file: the 47 blocks below represent one second of audio
        but take about a millisecond to feed, and a monotonic-clock
        throttle emitted exactly 1 frame for them.
        """
        producer = SpectrumProducer(sample_rate=RATE, fft_size=1024, update_hz=15.0)
        blocks = [_noise(1024, seed=i) for i in range(47)]

        emitted = sum(1 for block in blocks if producer.feed(block) is not None)

        assert emitted >= 10, (
            f"{emitted} frames for one second of audio -- the throttle is "
            "pacing on wall-clock, so row spacing depends on CPU speed"
        )

    def test_compute_is_not_throttled(self) -> None:
        """feed() paces the stream; compute() is the unpaced primitive the
        tests above use, and must stay that way."""
        producer = SpectrumProducer(sample_rate=RATE, fft_size=1024, update_hz=15.0)
        assert producer.compute(_noise(1024)) is not None
        assert producer.compute(_noise(1024)) is not None
