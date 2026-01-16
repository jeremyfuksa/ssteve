"""Smart Features - Automation and assistance features for SSTeVe.

This module contains smart automation features that reduce friction:
- Smart Reply: Auto-populated proof-of-reception templates
- Smart Mode Detection: Detect mode from sync timing when VIS fails
- Smart Device Configuration: Auto-detect and configure common hardware
- Smart QSO Logging: One-click QSO logging with auto-populated fields
"""

from .template_engine import TemplateEngine, render_smart_reply_template
from .mode_detector import detect_mode_from_sync_timing
from .field_populator import populate_smart_reply_fields
from .device_detector import detect_hardware_device, get_recommended_settings

__all__ = [
    "TemplateEngine",
    "render_smart_reply_template",
    "detect_mode_from_sync_timing",
    "populate_smart_reply_fields",
    "detect_hardware_device",
    "get_recommended_settings",
]
