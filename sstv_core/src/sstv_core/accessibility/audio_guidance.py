"""Audio guidance tones with stereo positioning for accessibility.

Provides stereo sonification for blind operators by generating pilot tones
that pan left/right based on slant error, helping users adjust receiving
equipment without visual feedback.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .slant_detector import SlantErrorData

logger = logging.getLogger(__name__)


@dataclass
class GuidanceConfig:
    """Configuration for audio guidance system."""

    enabled: bool = True
    pilot_tone_freq: float = 1200.0  # Hz
    pilot_tone_volume: float = 0.15  # 0.0-1.0 (mix level)
    slant_threshold_degrees: float = 2.0  # Minimum slant to trigger panning
    max_pan_degrees: float = 10.0  # Slant angle for full L/R pan
    lock_chime_enabled: bool = True
    lock_chime_volume: float = 0.3

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "pilot_tone_freq": self.pilot_tone_freq,
            "pilot_tone_volume": self.pilot_tone_volume,
            "slant_threshold_degrees": self.slant_threshold_degrees,
            "max_pan_degrees": self.max_pan_degrees,
            "lock_chime_enabled": self.lock_chime_enabled,
            "lock_chime_volume": self.lock_chime_volume,
        }


class AudioGuidance:
    """Generates audio guidance tones with stereo positioning.

    Provides accessibility features for blind operators:
    - Pilot tone with stereo panning based on slant error
    - Lock chime when VIS code detected
    - Mixed with monitoring audio for real-time feedback

    Example:
        config = GuidanceConfig(enabled=True, pilot_tone_freq=1200.0)
        guidance = AudioGuidance(config=config, sample_rate=48000)

        # Generate pilot tone with slant-based panning
        slant_error = SlantErrorData(slant_degrees=3.5, ...)
        stereo_tone = guidance.generate_pilot_tone(duration_ms=100, slant_error=slant_error)

        # Mix with monitoring audio
        mixed = guidance.mix_with_monitoring(monitoring_audio, stereo_tone)
    """

    def __init__(self, config: GuidanceConfig, sample_rate: int = 48000) -> None:
        """Initialize audio guidance generator.

        Args:
            config: Guidance configuration
            sample_rate: Audio sample rate
        """
        self._config = config
        self._sample_rate = sample_rate
        self._phase = 0.0  # Phase accumulator for smooth continuous tone

    def generate_pilot_tone(
        self,
        duration_ms: float,
        slant_error: Optional[SlantErrorData] = None,
    ) -> np.ndarray:
        """Generate pilot tone with stereo panning based on slant error.

        Args:
            duration_ms: Duration of tone in milliseconds
            slant_error: Current slant error (None = center, no pan)

        Returns:
            Stereo audio (shape: [samples, 2]) with L/R panning
        """
        if not self._config.enabled:
            # Return silence
            num_samples = int(self._sample_rate * duration_ms / 1000)
            return np.zeros((num_samples, 2), dtype=np.float32)

        num_samples = int(self._sample_rate * duration_ms / 1000)

        # Handle zero duration edge case
        if num_samples == 0:
            return np.zeros((0, 2), dtype=np.float32)

        # Generate continuous sine wave (preserve phase)
        t = np.arange(num_samples) / self._sample_rate
        phase_increment = 2.0 * np.pi * self._config.pilot_tone_freq
        phases = self._phase + phase_increment * t

        # Update phase accumulator (keep in [0, 2π])
        self._phase = (phases[-1] + phase_increment / self._sample_rate) % (2.0 * np.pi)

        mono_tone = np.sin(phases).astype(np.float32) * self._config.pilot_tone_volume

        # Calculate stereo pan from slant error
        pan = self._calculate_pan(slant_error)

        # Apply constant-power panning
        # pan = -1.0 (full left), 0.0 (center), +1.0 (full right)
        pan_radians = (pan + 1.0) * np.pi / 4.0  # Map [-1,1] to [0, π/2]
        left_gain = np.cos(pan_radians)
        right_gain = np.sin(pan_radians)

        # Create stereo output
        stereo = np.zeros((num_samples, 2), dtype=np.float32)
        stereo[:, 0] = mono_tone * left_gain  # Left channel
        stereo[:, 1] = mono_tone * right_gain  # Right channel

        return stereo

    def generate_lock_chime(self) -> np.ndarray:
        """Generate lock chime (C-E-G major chord) for VIS detection.

        Returns:
            Stereo audio with lock chime chord
        """
        if not self._config.enabled or not self._config.lock_chime_enabled:
            return np.zeros((1, 2), dtype=np.float32)

        # C-E-G major chord (C4=261.63 Hz, E4=329.63 Hz, G4=392.00 Hz)
        chord_freqs = [261.63, 329.63, 392.00]
        duration_ms = 150  # Short pleasant chime

        num_samples = int(self._sample_rate * duration_ms / 1000)
        t = np.arange(num_samples) / self._sample_rate

        # Generate chord (sum of three sine waves)
        chord = np.zeros(num_samples, dtype=np.float32)
        for freq in chord_freqs:
            chord += np.sin(2.0 * np.pi * freq * t).astype(np.float32)

        # Normalize and apply volume
        chord = chord / len(chord_freqs) * self._config.lock_chime_volume

        # Apply envelope (fade in/out) for smooth chime
        envelope = np.ones(num_samples, dtype=np.float32)
        fade_samples = int(num_samples * 0.1)  # 10% fade in/out

        # Fade in
        envelope[:fade_samples] = np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)
        # Fade out
        envelope[-fade_samples:] = np.linspace(1.0, 0.0, fade_samples, dtype=np.float32)

        chord = chord * envelope

        # Convert to stereo (center position)
        stereo = np.column_stack([chord, chord])

        return stereo

    def mix_with_monitoring(
        self,
        monitoring_audio: np.ndarray,
        guidance_audio: np.ndarray,
    ) -> np.ndarray:
        """Mix guidance tones with monitoring audio.

        Args:
            monitoring_audio: Original SSTV monitoring audio (mono or stereo)
            guidance_audio: Generated guidance tones (stereo)

        Returns:
            Mixed stereo audio
        """
        # Ensure monitoring audio is stereo
        if monitoring_audio.ndim == 1:
            # Mono to stereo (duplicate to both channels)
            monitoring_stereo = np.column_stack([monitoring_audio, monitoring_audio])
        else:
            monitoring_stereo = monitoring_audio

        # Ensure same length (truncate to shorter)
        min_len = min(len(monitoring_stereo), len(guidance_audio))
        monitoring_stereo = monitoring_stereo[:min_len]
        guidance_audio = guidance_audio[:min_len]

        # Mix (simple addition, relying on configured volumes to avoid clipping)
        mixed = monitoring_stereo + guidance_audio

        # Soft clip to prevent harsh distortion
        mixed = np.clip(mixed, -1.0, 1.0)

        return mixed

    def reset_phase(self) -> None:
        """Reset pilot tone phase accumulator.

        Call this when starting a new decode session to ensure
        pilot tone starts with consistent phase.
        """
        self._phase = 0.0

    def _calculate_pan(self, slant_error: Optional[SlantErrorData]) -> float:
        """Calculate stereo pan from slant error.

        Args:
            slant_error: Current slant error measurement

        Returns:
            Pan value: -1.0 (full left) to +1.0 (full right), 0.0 (center)
        """
        if slant_error is None:
            return 0.0  # No slant data, center position

        slant_deg = slant_error.slant_degrees

        # Apply threshold (no panning for small slant)
        if abs(slant_deg) < self._config.slant_threshold_degrees:
            return 0.0

        # Map slant to pan range
        # Positive slant (image shifts right) → pan left (help user correct)
        # Negative slant (image shifts left) → pan right
        # This creates intuitive feedback: "sound moves opposite to drift"

        # Normalize to [-1, 1] range
        normalized = -slant_deg / self._config.max_pan_degrees  # Note negative sign

        # Clamp to valid range
        pan = max(-1.0, min(1.0, normalized))

        return pan

    @property
    def config(self) -> GuidanceConfig:
        """Get current configuration."""
        return self._config

    def update_config(self, new_config: GuidanceConfig) -> None:
        """Update configuration.

        Args:
            new_config: New guidance configuration
        """
        self._config = new_config
        # Reset phase if pilot tone frequency changed
        self.reset_phase()
