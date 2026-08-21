"""Spectrum frames for the waterfall (#53).

PRODUCT.md calls a 300-3000 Hz waterfall non-negotiable, and frontend-contract
20.4 explains why: it is how the operator tunes. That makes it a display
the backend has to feed *before* a decode starts, not a decoration on one.

Two decisions are baked in here rather than left to the caller.

**The band is sliced at the producer.** At 48 kHz with 1024 bins, each bin
is 46.9 Hz and 300-3000 Hz is about 58 of the 512 real bins. Shipping all
512 at 15 frames a second would be roughly 200 KB/s of mostly-empty
spectrum above 3 kHz, for a display that cannot show it.

**Magnitudes are integer dBFS.** A waterfall renders four distinguishable
levels (20.4); sub-dB precision is not renderable and costs bandwidth to
carry. Integers also keep the event readable in a log, which matters for
the CLI's --json mode.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: The band the waterfall shows (frontend-contract 20.4). Everything outside is
#: real energy the display never draws, so it is dropped here rather than
#: sent and ignored.
SPECTRUM_MIN_HZ = 300.0
SPECTRUM_MAX_HZ = 3000.0

#: SSTV sync. Called out separately because 20.4 requires the pulse to read
#: differently from "a strong bin" -- an operator uses it to confirm they
#: are tuned, so the detection travels with the frame instead of being
#: re-derived from magnitudes by every client.
SYNC_HZ = 1200.0

#: How far either side of SYNC_HZ counts as sync, in Hz. Wide enough for a
#: mistuned signal and FFT leakage, narrow enough that the 1900 Hz centre
#: -- loud through every transmission -- never trips it.
SYNC_HALFWIDTH_HZ = 60.0

#: How far the sync bin must stand above the band's median before it counts.
#: Noise alone has no peak, so this is what separates "sync is present"
#: from "something is loud".
SYNC_MARGIN_DB = 12.0

#: Floor for the dB conversion. Silence is a real input -- a closed squelch,
#: a muted source -- and log10(0) is not a number the wire format can carry.
_FLOOR = 1e-12


@dataclass(frozen=True)
class SpectrumFrame:
    """One waterfall row.

    ``start_hz`` and ``bin_hz`` let a client label the axis without knowing
    the FFT size or sample rate, which is what keeps the contract stable
    when either changes.
    """

    start_hz: float
    bin_hz: float
    magnitudes_db: list[int]
    sync_detected: bool
    peak_hz: float | None
    peak_db: int | None


class SpectrumProducer:
    """Turns audio blocks into waterfall rows at a bounded rate.

    ``compute`` is the unpaced primitive: one buffer in, one frame out.
    ``feed`` adds the 10-20 Hz throttle from frontend-contract 20.4, because
    audio arrives in whatever blocks the source chooses -- a 48 kHz stream
    in 1024-sample chunks would otherwise produce 47 frames a second, and
    the pacing decision belongs with the producer rather than every caller.

    The throttle counts *audio* time, not wall-clock. A file re-decoded
    faster than real time still gets one row per ~66 ms of signal, so the
    waterfall's row spacing describes the recording rather than the speed
    of the machine reading it.
    """

    def __init__(
        self,
        sample_rate: int,
        fft_size: int = 1024,
        update_hz: float = 15.0,
    ) -> None:
        self._sample_rate = sample_rate
        self._fft_size = fft_size
        self._window = np.hanning(fft_size)
        self._samples_per_frame = (
            int(sample_rate / update_hz) if update_hz > 0 else 0
        )
        self._samples_since_emit = 0

        bin_hz = sample_rate / fft_size
        half = fft_size // 2
        freqs = np.arange(half) * bin_hz
        self._band = (freqs >= SPECTRUM_MIN_HZ) & (freqs <= SPECTRUM_MAX_HZ)
        self._band_freqs = freqs[self._band]
        self._bin_hz = bin_hz
        # Where sync sits inside the sliced band, not inside the full FFT.
        self._sync_mask = np.abs(self._band_freqs - SYNC_HZ) <= SYNC_HALFWIDTH_HZ

    @property
    def bin_hz(self) -> float:
        return self._bin_hz

    def compute(self, samples: np.ndarray) -> SpectrumFrame | None:
        """One frame from one buffer, or None if there is not enough audio.

        Returning None beats padding: a frame built from 100 samples would
        be a picture of the zero-padding, not of the band.
        """
        if len(samples) < self._fft_size or not self._band_freqs.size:
            return None

        block = np.asarray(samples[-self._fft_size :], dtype=np.float64)
        spectrum = np.abs(np.fft.rfft(block * self._window)[: self._fft_size // 2])
        magnitudes = spectrum[self._band] / (self._fft_size / 2)
        db = 20.0 * np.log10(np.maximum(magnitudes, _FLOOR))

        peak_index = int(np.argmax(db))
        peak_db = float(db[peak_index])
        median_db = float(np.median(db))

        sync_detected = False
        if self._sync_mask.any():
            sync_db = float(db[self._sync_mask].max())
            sync_detected = (
                sync_db - median_db >= SYNC_MARGIN_DB
                # The loudest thing in the band must BE the sync region, or
                # a stronger tone elsewhere is what the operator is hearing.
                and bool(self._sync_mask[peak_index])
            )

        return SpectrumFrame(
            start_hz=float(self._band_freqs[0]),
            bin_hz=self._bin_hz,
            magnitudes_db=[round(float(v)) for v in db],
            sync_detected=sync_detected,
            peak_hz=float(self._band_freqs[peak_index]),
            peak_db=round(peak_db),
        )

    def feed(self, samples: np.ndarray) -> SpectrumFrame | None:
        """``compute``, but at most ``update_hz`` frames per second of audio."""
        self._samples_since_emit += len(samples)
        if (
            self._samples_per_frame
            and self._samples_since_emit < self._samples_per_frame
        ):
            return None
        frame = self.compute(samples)
        if frame is not None:
            self._samples_since_emit = 0
        return frame
