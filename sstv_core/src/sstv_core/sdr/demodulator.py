"""USB demodulation: complex IQ in, real 48 kHz audio out.

The SDR path's only job is to hand the decoder the same 300-3000 Hz
audio a sound card would have produced. Nothing below this line knows
the signal arrived over a network.
"""

from __future__ import annotations

from math import gcd

import numpy as np
from scipy import signal

TARGET_RATE = 48000

# The selective bandpass wants a low sample rate to be cheap and sharp, so the
# wideband front stage decimates down to at most this before it runs.
_MAX_INTERMEDIATE_RATE = 400_000

# Passband of the SSB filter. Wider than the classic 2400 Hz voice SSB filter:
# SSTV maps brightness to frequency (1500 Hz black through 2300 Hz white), so
# the whole video band needs flat response. At 2400 Hz, 2300 Hz droops to 0.60
# and whites come out dim -- which reads as poor propagation, not a filter.
_DEFAULT_BANDWIDTH_HZ = 3000.0


def _plan_stages(input_rate: int, output_rate: int) -> tuple[int, int, int, int]:
    """Pick the front decimation and the rational ratio that follows it.

    Returns ``(front, intermediate_rate, up, down)``. The front factor divides
    the input rate down to something the narrow filter can work at; ``up`` and
    ``down`` then carry that intermediate rate to the output rate exactly.

    A single-stage design cannot do this job: an FIR's transition width scales
    with its sample rate, so a filter selective enough to separate +1500 Hz
    from -1500 Hz at 6 MHz would need tens of thousands of taps. Decimating
    first makes the selective stage cheap.
    """
    candidates = []
    for front in range(1, max(1, input_rate // (4 * output_rate)) + 1):
        if input_rate % front:
            continue
        intermediate = input_rate // front
        if front > 1 and not (
            4 * output_rate <= intermediate <= _MAX_INTERMEDIATE_RATE
        ):
            continue
        divisor = gcd(intermediate, output_rate)
        candidates.append(
            (output_rate // divisor, intermediate, front, intermediate // divisor)
        )
    if not candidates:
        # Rates already at or below the target band: resample them directly.
        divisor = gcd(input_rate, output_rate)
        return 1, input_rate, output_rate // divisor, input_rate // divisor
    up, intermediate, front, down = min(candidates)
    return front, intermediate, up, down


class USBDemodulator:
    """Upper-sideband demodulator, resampling to a fixed audio rate.

    Any input rate is accepted, integer multiple of the output rate or not.
    SpyServer rates are ``max_rate >> stage``, which cannot supply a missing
    factor of 3 or 5, so several common SDRs (Airspy R2, SDRplay, the 2.048 MHz
    RTL-SDR mode) only reach 48 kHz through a fractional ratio.

    One instance handles one continuous stream. Every stage carries its state
    between calls, so feeding the stream in blocks of any size produces the
    same audio as feeding it whole. Do not share an instance across unrelated
    signals -- the filters hold history, and the seam would show.

    Args:
        input_rate: IQ sample rate from the source, in Hz.
        output_rate: Audio rate to produce. The engine is 48 kHz end to end.
        bandwidth_hz: SSB passband width.

    """

    def __init__(
        self,
        input_rate: int,
        output_rate: int = TARGET_RATE,
        bandwidth_hz: float = _DEFAULT_BANDWIDTH_HZ,
    ) -> None:
        if input_rate <= 0:
            raise ValueError(f"IQ rate must be positive, got {input_rate} Hz.")
        self._input_rate = input_rate
        self._output_rate = output_rate
        self._front, intermediate, self._up, self._down = _plan_stages(
            input_rate, output_rate
        )

        # Stage 1 -- wideband anti-alias ahead of the front decimation. Real
        # taps are fine here: this stage only has to keep the audio band clean
        # while throwing away the megahertz of spectrum around it.
        if self._front > 1:
            front_taps = 129
            self._front_taps: np.ndarray | None = signal.firwin(
                front_taps,
                0.45 * intermediate,
                fs=input_rate,
                pass_zero="lowpass",  # noqa: S106 - scipy filter band, not a secret
            ).astype(np.complex128)
            self._front_zi = np.zeros(front_taps - 1, dtype=np.complex128)
        else:
            self._front_taps = None

        # Stage 2 -- the complex bandpass that makes this USB. Real taps would
        # be conjugate-symmetric and pass both sidebands equally, which is DSB.
        # Built by shifting a real lowpass prototype up by half the bandwidth,
        # so the passband covers 0..bandwidth_hz on the positive side only.
        # It runs at the intermediate rate, where 257 taps is genuinely sharp.
        band_taps = 257
        prototype = signal.firwin(
            band_taps,
            bandwidth_hz / 2.0,
            fs=intermediate,
            pass_zero="lowpass",  # noqa: S106 - scipy filter band, not a secret
        )
        centering = np.arange(band_taps) - (band_taps - 1) / 2
        self._band_taps: np.ndarray = (
            prototype
            * np.exp(2j * np.pi * (bandwidth_hz / 2.0) * centering / intermediate)
        ).astype(np.complex128)
        self._band_zi = np.zeros(band_taps - 1, dtype=np.complex128)

        # Stage 3 -- rational resample from the intermediate rate to the output
        # rate: zero-stuff by `up`, filter, keep every `down`th sample.
        if (self._up, self._down) != (1, 1):
            resample_taps = 128 * self._up + 1
            self._resample_taps: np.ndarray | None = (
                signal.firwin(
                    resample_taps,
                    min(0.45 * output_rate, 0.45 * intermediate),
                    fs=intermediate * self._up,
                    pass_zero="lowpass",  # noqa: S106 - filter band, not a secret
                )
                * self._up
            ).astype(np.complex128)
            self._resample_zi = np.zeros(resample_taps - 1, dtype=np.complex128)
        else:
            self._resample_taps = None

        # Every decimating grid is anchored to the stream rather than to the
        # block, so a block length that is not a multiple of the stride cannot
        # restart it and emit duplicate samples. These count samples consumed
        # at the input of each decimating stage; the mixer counts separately.
        self._front_index = 0
        self._resample_index = 0
        self._sample_index = 0

    @property
    def decimation(self) -> int:
        """Whole-number input samples consumed per output sample.

        Exact when the rates divide evenly, which is the common case. For a
        fractional ratio it is the floor, so it is a rounded description of the
        rate reduction rather than a stride any stage actually uses.
        """
        return self._input_rate // self._output_rate

    def demodulate(self, iq: np.ndarray, offset_hz: float = 0.0) -> np.ndarray:
        """Demodulate one block of complex IQ to real audio."""
        if len(iq) == 0:
            return np.zeros(0, dtype=np.float32)

        # Shift the wanted signal down so the passband starts at DC. For USB
        # the audio sits just above the tuned frequency, so shifting by
        # offset_hz places that content at baseband. The time base continues
        # from the running sample count so the oscillator stays phase-
        # continuous across block boundaries.
        if offset_hz:
            t = (
                np.arange(self._sample_index, self._sample_index + len(iq))
                / self._input_rate
            )
            iq = iq * np.exp(-2j * np.pi * offset_hz * t)
        self._sample_index += len(iq)

        stream = iq.astype(np.complex128)

        if self._front_taps is not None:
            filtered, self._front_zi = signal.lfilter(
                self._front_taps, [1.0], stream, zi=self._front_zi
            )
            offset = (-self._front_index) % self._front
            self._front_index += len(stream)
            stream = filtered[offset :: self._front]
            if len(stream) == 0:
                return np.zeros(0, dtype=np.float32)

        stream, self._band_zi = signal.lfilter(
            self._band_taps, [1.0], stream, zi=self._band_zi
        )

        if self._resample_taps is not None:
            stuffed = np.zeros(len(stream) * self._up, dtype=np.complex128)
            stuffed[:: self._up] = stream
            filtered, self._resample_zi = signal.lfilter(
                self._resample_taps, [1.0], stuffed, zi=self._resample_zi
            )
            offset = (-(self._resample_index * self._up)) % self._down
            self._resample_index += len(stream)
            stream = filtered[offset :: self._down]

        # Real part of the analytic signal is the demodulated audio.
        audio = np.real(stream)

        # Clamp rather than normalize. Dividing each block by its own peak is
        # uncontrolled AGC: every block gets a different gain. SSTV maps
        # brightness to frequency, so block-varying gain distorts the image.
        # Clamping keeps relative amplitude intact across blocks and only
        # touches samples that are genuinely over unity.
        return np.asarray(np.clip(audio, -1.0, 1.0), dtype=np.float32)
