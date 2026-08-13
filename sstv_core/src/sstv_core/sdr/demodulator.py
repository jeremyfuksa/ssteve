"""USB demodulation: complex IQ in, real 48 kHz audio out.

The SDR path's only job is to hand the decoder the same 300-3000 Hz
audio a sound card would have produced. Nothing below this line knows
the signal arrived over a network.
"""

from __future__ import annotations

import numpy as np
from scipy import signal

TARGET_RATE = 48000


class USBDemodulator:
    """Upper-sideband demodulator with decimation to a fixed audio rate.

    Args:
        input_rate: IQ sample rate from the source, in Hz.
        output_rate: Audio rate to produce. The engine is 48 kHz end to end.
        bandwidth_hz: SSB passband width. Wider than a voice SSB filter on
            purpose -- see the note on the filter below.

    """

    def __init__(
        self,
        input_rate: int,
        output_rate: int = TARGET_RATE,
        bandwidth_hz: float = 3000.0,
    ) -> None:
        if input_rate % output_rate:
            raise ValueError(
                f"IQ rate {input_rate} Hz isn't a whole multiple of the "
                f"{output_rate} Hz audio rate."
            )
        self._input_rate = input_rate
        self._decimation = input_rate // output_rate
        # A complex bandpass over 0..bandwidth_hz, built by shifting a real
        # lowpass prototype up by half the bandwidth. Real taps would be
        # conjugate-symmetric and pass both sidebands equally -- that is DSB,
        # not USB. The complex taps are what reject the lower sideband.
        # Applied at the input rate, before decimation, so nothing above the
        # output Nyquist folds back in.
        #
        # The default width is 3000 Hz, not the classic 2400 Hz voice SSB
        # filter: SSTV maps brightness to frequency (1500 Hz black through
        # 2300 Hz white), so the whole video band needs flat response. At
        # 2400 Hz, 2300 Hz droops to 0.60 and whites come out dim -- which
        # reads as poor propagation rather than a filter artifact.
        num_taps = 257
        prototype = signal.firwin(
            num_taps,
            bandwidth_hz / 2.0,
            fs=input_rate,
            pass_zero="lowpass",  # noqa: S106 - scipy filter band, not a secret
        )
        centering = np.arange(num_taps) - (num_taps - 1) / 2
        self._taps: np.ndarray = (
            prototype
            * np.exp(2j * np.pi * (bandwidth_hz / 2.0) * centering / input_rate)
        ).astype(np.complex128)

        # The runtime hands us one network block at a time, so a continuous
        # signal arrives split across calls. Both the filter delay line and
        # the mixer phase have to survive between them: a fresh filter state
        # would ring in at every block head, and a mixer restarting at t=0
        # would step the local-oscillator phase at every seam.
        self._zi: np.ndarray = np.zeros(num_taps - 1, dtype=np.complex128)
        self._sample_index = 0

    @property
    def decimation(self) -> int:
        return self._decimation

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

        # Complex bandpass: keeps the upper sideband, rejects the lower.
        filtered, self._zi = signal.lfilter(self._taps, [1.0], iq, zi=self._zi)
        decimated = filtered[:: self._decimation]

        # Real part of the analytic signal is the demodulated audio.
        audio = np.real(decimated).astype(np.float32)

        # Clamp rather than normalize. Dividing each block by its own peak is
        # uncontrolled AGC: every block gets a different gain. SSTV maps
        # brightness to frequency, so block-varying gain distorts the image.
        # Clamping keeps relative amplitude intact across blocks and only
        # touches samples that are genuinely over unity.
        return np.asarray(np.clip(audio, -1.0, 1.0), dtype=np.float32)
