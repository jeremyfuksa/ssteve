"""USB demodulation: IQ in, 48 kHz real audio out.

USB means the upper sideband survives and the lower is rejected. A tone
at +1500 Hz from center must land at 1500 Hz in the audio; a tone at
-1500 Hz must be suppressed.
"""

from __future__ import annotations

import numpy as np
import pytest

from sstv_core.sdr.demodulator import TARGET_RATE, USBDemodulator


def _tone_iq(offset_hz: float, rate: int, duration: float = 0.25) -> np.ndarray:
    """A complex exponential at offset_hz from center."""
    t = np.arange(int(rate * duration)) / rate
    return np.exp(2j * np.pi * offset_hz * t).astype(np.complex64)


def _dominant_freq(audio: np.ndarray, rate: int) -> float:
    spectrum = np.abs(np.fft.rfft(audio * np.hanning(len(audio))))
    return float(np.fft.rfftfreq(len(audio), 1 / rate)[int(np.argmax(spectrum))])


class TestUSBDemodulation:
    def test_upper_sideband_tone_lands_at_its_audio_frequency(self):
        rate = 192_000
        demod = USBDemodulator(input_rate=rate)
        audio = demod.demodulate(_tone_iq(1500.0, rate))
        assert _dominant_freq(audio, TARGET_RATE) == pytest.approx(1500.0, abs=30.0)

    def test_output_is_float32_at_the_target_rate(self):
        rate = 192_000
        demod = USBDemodulator(input_rate=rate)
        audio = demod.demodulate(_tone_iq(1000.0, rate, duration=1.0))
        assert audio.dtype == np.float32
        assert len(audio) == pytest.approx(TARGET_RATE, rel=0.02)

    def test_lower_sideband_is_rejected(self):
        """The property that makes this USB rather than DSB."""
        rate = 192_000
        demod = USBDemodulator(input_rate=rate)
        upper = demod.demodulate(_tone_iq(1500.0, rate))
        lower = demod.demodulate(_tone_iq(-1500.0, rate))
        assert np.max(np.abs(lower)) < np.max(np.abs(upper)) * 0.25

    def test_out_of_passband_tone_is_filtered_out(self):
        rate = 192_000
        demod = USBDemodulator(input_rate=rate)
        inband = demod.demodulate(_tone_iq(1500.0, rate))
        outband = demod.demodulate(_tone_iq(20_000.0, rate))
        assert np.max(np.abs(outband)) < np.max(np.abs(inband)) * 0.25

    def test_offset_shifts_the_tuned_frequency(self):
        rate = 192_000
        demod = USBDemodulator(input_rate=rate)
        audio = demod.demodulate(_tone_iq(3000.0, rate), offset_hz=1500.0)
        assert _dominant_freq(audio, TARGET_RATE) == pytest.approx(1500.0, abs=30.0)

    def test_strong_input_does_not_clip(self):
        rate = 192_000
        demod = USBDemodulator(input_rate=rate)
        audio = demod.demodulate(_tone_iq(1500.0, rate) * 50.0)
        assert np.max(np.abs(audio)) <= 1.0

    def test_empty_input_yields_empty_output(self):
        demod = USBDemodulator(input_rate=192_000)
        assert len(demod.demodulate(np.zeros(0, dtype=np.complex64))) == 0

    def test_non_integer_decimation_is_rejected(self):
        with pytest.raises(ValueError, match="multiple"):
            USBDemodulator(input_rate=100_000)

    def test_decimation_factor_is_reported(self):
        assert USBDemodulator(input_rate=192_000).decimation == 4
