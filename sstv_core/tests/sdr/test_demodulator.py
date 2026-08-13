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
        # A fresh demodulator per tone: the filter deliberately retains its
        # delay line across calls so a blocked stream stays continuous. Reusing
        # one instance for two unrelated signals would measure the previous
        # tone's tail decaying through the filter, not sideband rejection.
        upper = USBDemodulator(input_rate=rate).demodulate(_tone_iq(1500.0, rate))
        lower = USBDemodulator(input_rate=rate).demodulate(_tone_iq(-1500.0, rate))
        assert np.max(np.abs(lower)) < np.max(np.abs(upper)) * 0.25

    def test_out_of_passband_tone_is_filtered_out(self):
        rate = 192_000
        # Fresh instance per tone, for the same reason as the sideband test
        # above: retained filter state would carry the in-band tone into the
        # out-of-band measurement.
        inband = USBDemodulator(input_rate=rate).demodulate(_tone_iq(1500.0, rate))
        outband = USBDemodulator(input_rate=rate).demodulate(_tone_iq(20_000.0, rate))
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


class TestBlockContinuity:
    """The runtime calls demodulate() once per network block.

    A continuous signal arrives as a sequence of blocks, so the filter state
    and the mixer phase both have to survive across calls. Demodulating in
    blocks must match demodulating the same samples whole.
    """

    def _blocked(
        self,
        demod: USBDemodulator,
        iq: np.ndarray,
        block: int,
        offset_hz: float = 0.0,
    ) -> np.ndarray:
        return np.concatenate(
            [
                demod.demodulate(iq[i : i + block], offset_hz=offset_hz)
                for i in range(0, len(iq), block)
            ]
        )

    def test_blocked_input_matches_whole_input(self):
        """Filter state must carry across calls, or every block head is garbage."""
        rate = 192_000
        iq = _tone_iq(1500.0, rate, duration=0.5)

        whole = USBDemodulator(input_rate=rate).demodulate(iq)
        blocked = self._blocked(USBDemodulator(input_rate=rate), iq, 1024)

        assert len(blocked) == len(whole)
        rms = float(np.sqrt(np.mean(whole**2)))
        error = float(np.sqrt(np.mean((whole - blocked) ** 2)))
        assert error < rms * 0.01

    def test_offset_stays_phase_continuous_across_blocks(self):
        """The local oscillator must not restart its phase on each block.

        The block size matters: at 1024 samples the 1500 Hz oscillator
        advances exactly 8.0 cycles, so a phase reset would be invisible.
        996 samples is 7.78 cycles, which makes a reset show up.
        """
        rate = 192_000
        iq = _tone_iq(3000.0, rate, duration=0.25)

        whole = USBDemodulator(input_rate=rate).demodulate(iq, offset_hz=1500.0)
        blocked = self._blocked(
            USBDemodulator(input_rate=rate), iq, 996, offset_hz=1500.0
        )

        assert np.max(np.abs(whole - blocked)) < 0.01

    @pytest.mark.parametrize("block", [777, 999, 1024, 3])
    def test_block_size_need_not_divide_the_decimation_factor(self, block: int):
        """SpyServer blocks carry no guarantee of being a multiple of 4.

        The decimation grid is anchored to the stream, so a block that ends
        mid-stride must not restart it -- that would emit extra samples and
        desynchronize the audio.
        """
        rate = 192_000
        iq = _tone_iq(1500.0, rate, duration=0.25)

        whole = USBDemodulator(input_rate=rate).demodulate(iq)
        blocked = self._blocked(USBDemodulator(input_rate=rate), iq, block)

        assert len(blocked) == len(whole)
        rms = float(np.sqrt(np.mean(whole**2)))
        error = float(np.sqrt(np.mean((whole - blocked) ** 2)))
        assert error < rms * 0.01

    def test_blocked_offset_tone_still_lands_on_frequency(self):
        """A seam-free block stream resolves to the same audio tone."""
        rate = 192_000
        iq = _tone_iq(3000.0, rate, duration=0.5)
        blocked = self._blocked(
            USBDemodulator(input_rate=rate), iq, 1024, offset_hz=1500.0
        )
        assert _dominant_freq(blocked, TARGET_RATE) == pytest.approx(1500.0, abs=30.0)

    def test_uneven_block_sizes_stay_continuous(self):
        """Network blocks do not arrive in tidy powers of two."""
        rate = 192_000
        iq = _tone_iq(1500.0, rate, duration=0.25)

        whole = USBDemodulator(input_rate=rate).demodulate(iq)
        demod = USBDemodulator(input_rate=rate)
        sizes = (700, 1300, 480, 2048, 960)
        chunks = []
        start = 0
        step = 0
        while start < len(iq):
            size = sizes[step % len(sizes)]
            chunks.append(demod.demodulate(iq[start : start + size]))
            start += size
            step += 1
        blocked = np.concatenate(chunks)

        n = min(len(whole), len(blocked))
        rms = float(np.sqrt(np.mean(whole[:n] ** 2)))
        error = float(np.sqrt(np.mean((whole[:n] - blocked[:n]) ** 2)))
        assert error < rms * 0.01
