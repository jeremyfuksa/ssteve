"""AFC and squelch: the config knobs must actually change decode behavior.

Until 2026-08-08 auto_afc/afc_range_hz/auto_squelch/squelch_threshold_db
were stored and served by /config but consumed by nothing.
"""

from __future__ import annotations

import numpy as np
import pytest

from sstv_core.decode.scottie_decoder import ScottieS1Config, ScottieS1Decoder
from sstv_core.decode.sync_detector import SyncPulseDetector
from sstv_core.encode.scottie_encoder import ScottieS1Encoder

SAMPLE_RATE = 48000


def shifted_transmission(offset_hz: float) -> tuple[np.ndarray, np.ndarray]:
    """A Scottie S1 gradient transmission with every tone shifted by
    offset_hz -- what a mistuned receiver hears."""
    encoder = ScottieS1Encoder()
    x = np.linspace(0, 255, 320)
    img = np.zeros((256, 320, 3), dtype=np.uint8)
    img[:, :, 0] = np.tile(x, (256, 1))
    img[:, :, 1] = np.tile(x, (256, 1))
    img[:, :, 2] = np.tile(x, (256, 1))
    audio = encoder.encode_image(img, include_vis=False).astype(np.float64)

    # Heterodyne shift via analytic signal: preserves the FM structure while
    # moving every instantaneous frequency by offset_hz.
    from scipy.signal import hilbert

    analytic = hilbert(audio)
    t = np.arange(len(audio)) / SAMPLE_RATE
    shifted = np.real(analytic * np.exp(2j * np.pi * offset_hz * t))
    return img, shifted.astype(np.float32)


def decode_with_mapping(audio: np.ndarray, freq_offset: float) -> np.ndarray:
    """Decode through the real sync+decoder pipeline with the video mapping
    shifted by freq_offset (0 = nominal mapping)."""
    detector = SyncPulseDetector(sample_rate=SAMPLE_RATE)
    detector.detect_in_buffer(audio)
    positions = detector.get_sync_positions(line_duration_ms=428.22)
    config = ScottieS1Config(sample_rate=SAMPLE_RATE)
    config.black_freq += freq_offset
    config.white_freq += freq_offset
    decoder = ScottieS1Decoder(config)
    for _ in decoder.decode_stream(iter([audio]), positions):
        pass
    image = decoder.get_image()
    assert image is not None
    return image


class TestAFCCorrection:
    def test_offset_signal_decodes_correctly_with_corrected_mapping(self):
        """+60 Hz shift: corrected mapping recovers the image, nominal
        mapping is measurably brighter (every frequency reads 60 Hz high)."""
        img, audio = shifted_transmission(60.0)
        corrected = decode_with_mapping(audio, 60.0).astype(np.float64)
        uncorrected = decode_with_mapping(audio, 0.0).astype(np.float64)

        original = img.astype(np.float64)
        corrected_err = np.abs(corrected[20:-20, 20:-20] - original[20:-20, 20:-20]).mean()
        uncorrected_err = np.abs(
            uncorrected[20:-20, 20:-20] - original[20:-20, 20:-20]
        ).mean()

        # 60 Hz over an 800 Hz span is ~19 luma counts of bias.
        assert corrected_err < uncorrected_err - 10, (
            f"corrected {corrected_err:.1f} vs uncorrected {uncorrected_err:.1f}"
        )

    def test_rx_manager_measures_sync_offset(self):
        """The pulse-frequency estimator recovers a known offset."""
        from types import SimpleNamespace

        from sstv_core.decode.rx_manager import RXManager

        rx = RXManager(stream_manager=SimpleNamespace(), sample_rate=SAMPLE_RATE)
        # 9 ms pulse at 1260 Hz embedded in mid-grey video (1900 Hz)
        pulse_len = int(0.009 * SAMPLE_RATE)
        t_pulse = np.arange(pulse_len) / SAMPLE_RATE
        t_video = np.arange(SAMPLE_RATE // 10) / SAMPLE_RATE
        stream = np.concatenate([
            0.5 * np.sin(2 * np.pi * 1900.0 * t_video),
            0.5 * np.sin(2 * np.pi * 1260.0 * t_pulse),
            0.5 * np.sin(2 * np.pi * 1900.0 * t_video),
        ]).astype(np.float32)
        pulse = SimpleNamespace(
            position_samples=len(t_video), duration_ms=9.0
        )
        offset = rx._measure_pulse_offset(stream, 0, pulse)
        assert offset is not None
        assert offset == pytest.approx(60.0, abs=5.0)

    def test_manual_override_exists(self):
        """auto_afc=False must be constructible -- Doppler work depends on
        the manual override staying available."""
        from types import SimpleNamespace

        from sstv_core.decode.rx_manager import RXManager

        rx = RXManager(
            stream_manager=SimpleNamespace(),
            auto_afc=False,
            auto_squelch=True,
            squelch_threshold_db=-30.0,
        )
        assert rx._auto_afc is False
        assert rx._auto_squelch is True
        assert rx._squelch_threshold_db == -30.0


class TestSquelchGate:
    def test_dsp_manager_reads_decode_config_defaults(self):
        """Without a database the documented defaults apply."""
        import asyncio

        from sstv_core.api.dsp_manager import DSPManager

        config = asyncio.run(DSPManager()._read_decode_config())
        assert config["auto_afc"] is True
        assert config["auto_squelch"] is True
        assert config["squelch_threshold_db"] == -40.0
