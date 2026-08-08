"""Playback adapter for accessibility audio guidance.

AudioGuidance generates the cues (pilot tone, lock chime); this module
actually plays them on the local output device during decode lifecycle
events. Kept separate so the DSP layer depends on a two-method surface and
tests can substitute it without touching sounddevice.

Wired 2026-08-08 -- the generator was real, tested code that nothing
invoked (eyes-free operation is a stated operating situation in
PRODUCT.md).
"""

from __future__ import annotations

import logging

import numpy as np

from sstv_core.accessibility.audio_guidance import AudioGuidance, GuidanceConfig

logger = logging.getLogger(__name__)


class GuidancePlayer:
    """Plays guidance cues on the default local output device.

    Local speaker output is independent of the radio-side half-duplex
    constraint: guiding the operator's ears while receiving is the point.
    Every play call is fire-and-forget and swallows device errors -- a
    missing speaker must never fail a decode.
    """

    def __init__(self, config: GuidanceConfig, sample_rate: int = 48000) -> None:
        self._guidance = AudioGuidance(config=config, sample_rate=sample_rate)
        self._sample_rate = sample_rate

    @property
    def enabled(self) -> bool:
        return self._guidance.config.enabled

    def play_lock_chime(self) -> None:
        """VIS detected: signal lock. The C-E-G chime."""
        self._play(self._guidance.generate_lock_chime())

    def play_complete_chime(self) -> None:
        """Decode complete: the lock chime twice, a distinct pattern."""
        chime = self._guidance.generate_lock_chime()
        gap = np.zeros((self._sample_rate // 10, 2), dtype=np.float32)
        self._play(np.concatenate([chime, gap, chime]))

    def _play(self, stereo: np.ndarray) -> None:
        if not self.enabled or len(stereo) <= 1:
            return
        try:
            import sounddevice as sd

            sd.play(stereo, samplerate=self._sample_rate, blocking=False)
        except Exception as exc:
            # Guidance is an aid, never a dependency.
            logger.warning("Guidance playback failed: %s", exc)
