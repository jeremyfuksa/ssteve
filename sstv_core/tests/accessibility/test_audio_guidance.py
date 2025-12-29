"""Tests for audio guidance system."""

import numpy as np
import pytest

from sstv_core.accessibility.audio_guidance import AudioGuidance, GuidanceConfig
from sstv_core.accessibility.slant_detector import SlantErrorData


class TestGuidanceConfig:
    """Tests for GuidanceConfig dataclass."""

    def test_default_configuration(self):
        """Default configuration has sensible values."""
        config = GuidanceConfig()

        assert config.enabled is True
        assert config.pilot_tone_freq == 1200.0
        assert 0.0 < config.pilot_tone_volume <= 1.0
        assert config.slant_threshold_degrees > 0
        assert config.lock_chime_enabled is True

    def test_to_dict(self):
        """GuidanceConfig converts to dict correctly."""
        config = GuidanceConfig(
            enabled=True,
            pilot_tone_freq=1500.0,
            pilot_tone_volume=0.2,
        )
        d = config.to_dict()

        assert d["enabled"] is True
        assert d["pilot_tone_freq"] == 1500.0
        assert d["pilot_tone_volume"] == 0.2


class TestAudioGuidance:
    """Tests for AudioGuidance."""

    def test_initialization(self):
        """AudioGuidance initializes correctly."""
        config = GuidanceConfig()
        guidance = AudioGuidance(config=config, sample_rate=48000)

        assert guidance.config == config

    def test_disabled_guidance_returns_silence(self):
        """Disabled guidance returns silent audio."""
        config = GuidanceConfig(enabled=False)
        guidance = AudioGuidance(config=config, sample_rate=48000)

        tone = guidance.generate_pilot_tone(duration_ms=100)

        assert tone.shape[1] == 2  # Stereo
        assert np.allclose(tone, 0.0)  # Silent

    def test_pilot_tone_generation_stereo(self):
        """Pilot tone generates stereo audio."""
        config = GuidanceConfig(enabled=True, pilot_tone_freq=1200.0)
        guidance = AudioGuidance(config=config, sample_rate=48000)

        tone = guidance.generate_pilot_tone(duration_ms=100)

        # Check shape (stereo)
        expected_samples = int(48000 * 0.1)  # 100ms at 48kHz
        assert tone.shape == (expected_samples, 2)

        # Check not silent
        assert np.max(np.abs(tone)) > 0.01

    def test_pilot_tone_center_with_no_slant(self):
        """Pilot tone is centered when no slant error."""
        config = GuidanceConfig(enabled=True, pilot_tone_volume=0.5)
        guidance = AudioGuidance(config=config, sample_rate=48000)

        tone = guidance.generate_pilot_tone(duration_ms=100, slant_error=None)

        # L and R channels should be equal (center pan)
        assert np.allclose(tone[:, 0], tone[:, 1], rtol=0.01)

    def test_pilot_tone_pans_left_on_positive_slant(self):
        """Pilot tone pans left when image drifts right (positive slant)."""
        config = GuidanceConfig(
            enabled=True,
            pilot_tone_volume=0.5,
            slant_threshold_degrees=2.0,
            max_pan_degrees=10.0,
        )
        guidance = AudioGuidance(config=config, sample_rate=48000)

        # Positive slant (image shifts right)
        slant = SlantErrorData(
            slant_degrees=5.0,  # Above threshold
            drift_pixels_per_line=0.5,
            cumulative_drift_pixels=128.0,
            confidence=0.9,
            measurement_lines=100,
        )

        tone = guidance.generate_pilot_tone(duration_ms=100, slant_error=slant)

        # Left channel should be louder than right
        left_rms = np.sqrt(np.mean(tone[:, 0] ** 2))
        right_rms = np.sqrt(np.mean(tone[:, 1] ** 2))

        assert left_rms > right_rms

    def test_pilot_tone_pans_right_on_negative_slant(self):
        """Pilot tone pans right when image drifts left (negative slant)."""
        config = GuidanceConfig(
            enabled=True,
            pilot_tone_volume=0.5,
            slant_threshold_degrees=2.0,
            max_pan_degrees=10.0,
        )
        guidance = AudioGuidance(config=config, sample_rate=48000)

        # Negative slant (image shifts left)
        slant = SlantErrorData(
            slant_degrees=-5.0,  # Above threshold (absolute value)
            drift_pixels_per_line=-0.5,
            cumulative_drift_pixels=-128.0,
            confidence=0.9,
            measurement_lines=100,
        )

        tone = guidance.generate_pilot_tone(duration_ms=100, slant_error=slant)

        # Right channel should be louder than left
        left_rms = np.sqrt(np.mean(tone[:, 0] ** 2))
        right_rms = np.sqrt(np.mean(tone[:, 1] ** 2))

        assert right_rms > left_rms

    def test_pilot_tone_no_pan_below_threshold(self):
        """Pilot tone stays centered when slant below threshold."""
        config = GuidanceConfig(
            enabled=True,
            slant_threshold_degrees=2.0,
        )
        guidance = AudioGuidance(config=config, sample_rate=48000)

        # Small slant (below threshold)
        slant = SlantErrorData(
            slant_degrees=1.0,  # Below 2.0° threshold
            drift_pixels_per_line=0.1,
            cumulative_drift_pixels=25.6,
            confidence=0.9,
            measurement_lines=100,
        )

        tone = guidance.generate_pilot_tone(duration_ms=100, slant_error=slant)

        # Should be centered (equal L/R)
        assert np.allclose(tone[:, 0], tone[:, 1], rtol=0.01)

    def test_pilot_tone_frequency_correct(self):
        """Pilot tone generates specified frequency."""
        config = GuidanceConfig(enabled=True, pilot_tone_freq=1200.0)
        guidance = AudioGuidance(config=config, sample_rate=48000)

        tone = guidance.generate_pilot_tone(duration_ms=200)  # Longer for FFT

        # FFT to check frequency
        fft = np.fft.rfft(tone[:, 0])  # Analyze left channel
        freqs = np.fft.rfftfreq(len(tone), 1 / 48000)

        # Find peak frequency
        peak_idx = np.argmax(np.abs(fft))
        peak_freq = freqs[peak_idx]

        # Should be close to 1200 Hz
        assert abs(peak_freq - 1200.0) < 10.0  # Within 10 Hz

    def test_pilot_tone_phase_continuity(self):
        """Pilot tone maintains phase continuity across calls."""
        config = GuidanceConfig(enabled=True, pilot_tone_freq=1200.0)
        guidance = AudioGuidance(config=config, sample_rate=48000)

        # Generate two consecutive segments
        tone1 = guidance.generate_pilot_tone(duration_ms=50)
        tone2 = guidance.generate_pilot_tone(duration_ms=50)

        # Check phase continuity: last sample of tone1 should connect to first of tone2
        # For continuous sine wave, the derivative should be smooth
        last_sample_tone1 = tone1[-1, 0]
        first_sample_tone2 = tone2[0, 0]

        # Samples should be reasonably close (smooth transition)
        # Not exact due to discrete sampling, but should be continuous
        assert abs(first_sample_tone2 - last_sample_tone1) < 0.3

    def test_lock_chime_generation(self):
        """Lock chime generates C-E-G chord."""
        config = GuidanceConfig(enabled=True, lock_chime_enabled=True)
        guidance = AudioGuidance(config=config, sample_rate=48000)

        chime = guidance.generate_lock_chime()

        # Should be stereo
        assert chime.shape[1] == 2

        # Should have content (not silent)
        assert np.max(np.abs(chime)) > 0.01

        # Should be relatively short (pleasant chime, not long tone)
        assert len(chime) < 48000 * 0.5  # Less than 500ms

    def test_lock_chime_disabled_returns_silence(self):
        """Disabled lock chime returns minimal silence."""
        config = GuidanceConfig(enabled=True, lock_chime_enabled=False)
        guidance = AudioGuidance(config=config, sample_rate=48000)

        chime = guidance.generate_lock_chime()

        # Should be minimal/silent
        assert len(chime) <= 2
        assert np.allclose(chime, 0.0)

    def test_lock_chime_has_envelope(self):
        """Lock chime has smooth fade in/out envelope."""
        config = GuidanceConfig(enabled=True, lock_chime_enabled=True)
        guidance = AudioGuidance(config=config, sample_rate=48000)

        chime = guidance.generate_lock_chime()

        # Start should be quiet (fade in)
        assert abs(chime[0, 0]) < abs(chime[len(chime) // 2, 0])

        # End should be quiet (fade out)
        assert abs(chime[-1, 0]) < abs(chime[len(chime) // 2, 0])

    def test_mix_with_monitoring_mono(self):
        """Mix guidance with mono monitoring audio."""
        config = GuidanceConfig(enabled=True, pilot_tone_volume=0.2)
        guidance = AudioGuidance(config=config, sample_rate=48000)

        # Create mono monitoring audio
        monitoring = np.random.randn(4800).astype(np.float32) * 0.1

        # Generate guidance tone
        guidance_tone = guidance.generate_pilot_tone(duration_ms=100)

        # Mix
        mixed = guidance.mix_with_monitoring(monitoring, guidance_tone)

        # Should be stereo
        assert mixed.shape[1] == 2

        # Should contain both signals
        assert np.max(np.abs(mixed)) > np.max(np.abs(monitoring))

    def test_mix_with_monitoring_stereo(self):
        """Mix guidance with stereo monitoring audio."""
        config = GuidanceConfig(enabled=True, pilot_tone_volume=0.2)
        guidance = AudioGuidance(config=config, sample_rate=48000)

        # Create stereo monitoring audio
        monitoring = np.random.randn(4800, 2).astype(np.float32) * 0.1

        # Generate guidance tone
        guidance_tone = guidance.generate_pilot_tone(duration_ms=100)

        # Mix
        mixed = guidance.mix_with_monitoring(monitoring, guidance_tone)

        # Should be stereo
        assert mixed.shape[1] == 2

        # Should be same length as inputs (or shorter if mismatched)
        assert len(mixed) <= len(monitoring)

    def test_mix_handles_length_mismatch(self):
        """Mix truncates to shorter of two signals."""
        config = GuidanceConfig(enabled=True)
        guidance = AudioGuidance(config=config, sample_rate=48000)

        # Different length signals
        monitoring = np.random.randn(4800).astype(np.float32) * 0.1
        guidance_tone = guidance.generate_pilot_tone(duration_ms=50)  # Shorter

        mixed = guidance.mix_with_monitoring(monitoring, guidance_tone)

        # Should match shorter signal
        assert len(mixed) == len(guidance_tone)

    def test_reset_phase(self):
        """Reset phase restarts pilot tone phase."""
        config = GuidanceConfig(enabled=True, pilot_tone_freq=1200.0)
        guidance = AudioGuidance(config=config, sample_rate=48000)

        # Generate some tone (advances phase)
        guidance.generate_pilot_tone(duration_ms=100)

        # Reset phase
        guidance.reset_phase()

        # Generate again (should start from zero phase)
        tone_after_reset = guidance.generate_pilot_tone(duration_ms=100)

        # First sample should be near zero (sine wave starts at zero phase)
        assert abs(tone_after_reset[0, 0]) < 0.1

    def test_update_config(self):
        """Update config changes guidance behavior."""
        config1 = GuidanceConfig(enabled=True, pilot_tone_freq=1200.0)
        guidance = AudioGuidance(config=config1, sample_rate=48000)

        # Update config
        config2 = GuidanceConfig(enabled=False)  # Disable
        guidance.update_config(config2)

        # Should now return silence
        tone = guidance.generate_pilot_tone(duration_ms=100)
        assert np.allclose(tone, 0.0)


class TestAudioGuidanceEdgeCases:
    """Edge case tests for audio guidance."""

    def test_extreme_slant_clamps_pan(self):
        """Extreme slant doesn't cause pan to exceed [-1, 1]."""
        config = GuidanceConfig(
            enabled=True,
            max_pan_degrees=10.0,
        )
        guidance = AudioGuidance(config=config, sample_rate=48000)

        # Extreme slant (beyond max_pan_degrees)
        slant = SlantErrorData(
            slant_degrees=50.0,  # Way beyond max
            drift_pixels_per_line=5.0,
            cumulative_drift_pixels=1280.0,
            confidence=0.9,
            measurement_lines=100,
        )

        tone = guidance.generate_pilot_tone(duration_ms=100, slant_error=slant)

        # Should still produce valid audio (no NaN, no excessive values)
        assert not np.isnan(tone).any()
        assert np.max(np.abs(tone)) <= 1.0

    def test_zero_duration_tone(self):
        """Zero duration tone returns empty array."""
        config = GuidanceConfig(enabled=True)
        guidance = AudioGuidance(config=config, sample_rate=48000)

        tone = guidance.generate_pilot_tone(duration_ms=0)

        assert tone.shape[0] == 0
        assert tone.shape[1] == 2  # Still stereo format

    def test_very_high_frequency(self):
        """Very high pilot tone frequency (near Nyquist) handled safely."""
        config = GuidanceConfig(enabled=True, pilot_tone_freq=20000.0)  # Near Nyquist
        guidance = AudioGuidance(config=config, sample_rate=48000)

        tone = guidance.generate_pilot_tone(duration_ms=100)

        # Should produce valid output (not aliased/NaN)
        assert not np.isnan(tone).any()
        assert np.max(np.abs(tone)) > 0
