"""Accessibility features for SSTeVe SSTV platform.

This module provides accessibility features including:
- Slant error detection for image correction
- Audio guidance tones with stereo positioning
- Stereo sonification for blind operators
"""

from .audio_guidance import AudioGuidance, GuidanceConfig
from .slant_detector import SlantDetector, SlantErrorData

__all__ = [
    "AudioGuidance",
    "GuidanceConfig",
    "SlantDetector",
    "SlantErrorData",
]
