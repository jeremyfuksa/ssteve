"""Configuration manager for SSTeVe core engine.

Provides a singleton ConfigManager class for loading, saving, and validating
application settings stored in the database Configuration table.

Thread-safe access to configuration with validation on set operations.
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# =============================================================================
# Validation Models (Pydantic)
# =============================================================================


class DecoderSettings(BaseModel):
    """Decoder-specific settings from advanced_settings_json."""

    vis_detection_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    sync_detection_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    afc_enabled: bool = True
    afc_range_hz: int = Field(default=100, ge=50, le=200)
    auto_mode_detection_enabled: bool = True
    slant_auto_correct: bool = True


class EncoderSettings(BaseModel):
    """Encoder-specific settings from advanced_settings_json."""

    pre_emphasis_enabled: bool = False
    color_space: str = Field(default="RGB", pattern=r"^(RGB|YUV)$")
    jpeg_quality: int = Field(default=85, ge=0, le=100)


class UISettings(BaseModel):
    """UI-specific settings from advanced_settings_json."""

    canvas_zoom: float = Field(default=1.0, ge=0.5, le=2.0)
    waterfall_fft_size: int = Field(default=1024, ge=512, le=2048)
    waterfall_visible: bool = True
    telemetry_panel_visible: bool = True
    operating_mode: str = Field(default="standard", pattern=r"^(standard|night_vision|sunlight)$")


class AudioAdvancedSettings(BaseModel):
    """Audio-specific advanced settings from advanced_settings_json."""

    buffer_size_samples: int = Field(default=1024, ge=512, le=2048)
    sample_rate_override: int | None = Field(default=None, ge=44100, le=48000)
    input_gain_override: float | None = Field(default=None, ge=0.0, le=2.0)
    auto_squelch: bool = Field(
        default=True,
        description="Enable automatic squelch calculation",
    )
    squelch_threshold_db: float = Field(
        default=-40.0,
        ge=-100.0,
        le=0.0,
        description="Manual squelch threshold (dB)",
    )


class AccessibilitySettings(BaseModel):
    """Accessibility feature settings from advanced_settings_json."""

    stereo_guidance_enabled: bool = False
    pilot_tone_freq: float = Field(default=1200.0, ge=200.0, le=3000.0)
    pilot_tone_volume: float = Field(default=0.15, ge=0.0, le=1.0)
    slant_threshold_degrees: float = Field(default=2.0, ge=0.1, le=10.0)
    max_pan_degrees: float = Field(default=10.0, ge=1.0, le=45.0)
    lock_chime_enabled: bool = True
    lock_chime_volume: float = Field(default=0.3, ge=0.0, le=1.0)
    verbose_cli_enabled: bool = False
    json_logging_enabled: bool = False


class ExperimentalSettings(BaseModel):
    """Experimental feature settings from advanced_settings_json."""

    ai_captions_enabled: bool = False
    smart_reply_auto_suggest: bool = True
    telemetry_export_enabled: bool = False


class AdvancedSettings(BaseModel):
    """Complete advanced settings structure (stored as JSON in DB)."""

    decoder: DecoderSettings = Field(default_factory=DecoderSettings)
    encoder: EncoderSettings = Field(default_factory=EncoderSettings)
    ui: UISettings = Field(default_factory=UISettings)
    audio: AudioAdvancedSettings = Field(default_factory=AudioAdvancedSettings)
    accessibility: AccessibilitySettings = Field(default_factory=AccessibilitySettings)
    experimental: ExperimentalSettings = Field(default_factory=ExperimentalSettings)


class ConfigValidation(BaseModel):
    """Validation model for main configuration fields."""

    # Audio device IDs - alphanumeric with basic punctuation, no path traversal
    audio_input_device_id: str | None = Field(default=None, max_length=255)
    audio_output_device_id: str | None = Field(default=None, max_length=255)

    # TX mode - restricted to known SSTV modes
    default_tx_mode: str = Field(
        default="ScottieS1",
        pattern=r"^(ScottieS[12]|ScottieDX|MartinM[12]|Robot(36|72)|PD(90|120|160|180|240)|Wraase(SC2-180))$",
    )

    # Storage paths - must be within user directory, no path traversal
    image_save_directory: str = Field(default="", max_length=1024)
    mmsstv_import_directory: str | None = Field(default=None, max_length=1024)

    # PTT settings
    ptt_method: str = Field(default="vox", pattern=r"^(none|serial|vox)$")
    ptt_serial_port: str | None = Field(default=None, max_length=100)
    ptt_serial_baud: int = Field(default=9600, ge=300, le=115200)
    ptt_serial_signal: str = Field(default="RTS", pattern=r"^(RTS|DTR)$")
    ptt_pre_delay_ms: int = Field(default=500, ge=0, le=5000)
    ptt_post_delay_ms: int = Field(default=200, ge=0, le=5000)
    vox_preamble_ms: int = Field(default=500, ge=0, le=5000)

    # Accessibility
    enable_stereo_guidance: bool = False
    pilot_tone_hz: int = Field(default=1200, ge=200, le=3000)
    enable_ai_captions: bool = False
    enable_verbose_cli: bool = False

    # Theme
    theme: str = Field(default="darkroom", pattern=r"^(darkroom|light|high_contrast)$")

    @field_validator("audio_input_device_id", "audio_output_device_id")
    @classmethod
    def validate_device_id(cls, v: str | None) -> str | None:
        """Validate device IDs don't contain path traversal characters."""
        if v is None:
            return v
        # Reject path traversal attempts
        if ".." in v or "/" in v or "\\" in v:
            msg = "Device ID cannot contain path characters (.., /, \\)"
            raise ValueError(msg)
        return v

    @field_validator("image_save_directory", "mmsstv_import_directory")
    @classmethod
    def validate_path(cls, v: str | None) -> str | None:
        """Validate paths are safe and within reasonable bounds."""
        if v is None or v == "":
            return v
        # Must be absolute path
        path = Path(v)
        if not path.is_absolute():
            msg = "Path must be absolute"
            raise ValueError(msg)
        # Check for path traversal in components
        for part in path.parts:
            if part == "..":
                msg = "Path cannot contain .."
                raise ValueError(msg)
        return v

    @field_validator("ptt_serial_port")
    @classmethod
    def validate_serial_port(cls, v: str | None) -> str | None:
        """Validate serial port format."""
        if v is None:
            return v
        # Linux: /dev/ttyUSB0, /dev/ttyACM0
        # macOS: /dev/cu.usbserial-xxxx
        # Windows: COM1-COM256
        linux_pattern = r"^/dev/tty(USB|ACM|S)\d+$"
        macos_pattern = r"^/dev/(cu|tty)\.[a-zA-Z0-9_-]+$"
        windows_pattern = r"^COM([1-9]|[1-9]\d|1\d{2}|2[0-4]\d|25[0-6])$"

        if not (
            re.match(linux_pattern, v)
            or re.match(macos_pattern, v)
            or re.match(windows_pattern, v)
        ):
            msg = f"Invalid serial port format: {v}"
            raise ValueError(msg)
        return v


# =============================================================================
# Configuration Manager
# =============================================================================


class ConfigManager:
    """Thread-safe configuration manager with validation.

    Provides CRUD operations for application configuration stored in the
    database's Configuration table (singleton pattern).

    Usage:
        from sstv_core.config import ConfigManager
        from sstv_core.database.models import init_database

        engine, session_factory = init_database()
        with session_factory() as session:
            config_mgr = ConfigManager(session)

            # Get a value
            mode = config_mgr.get("default_tx_mode")

            # Set a value (with validation)
            config_mgr.set("default_tx_mode", "MartinM1")

            # Get all config as dict
            all_config = config_mgr.to_dict()

            # Update multiple values
            config_mgr.update({
                "ptt_method": "serial",
                "ptt_serial_port": "/dev/ttyUSB0"
            })
    """

    _lock = threading.RLock()

    # Fields that map directly to Configuration model columns
    CORE_FIELDS = frozenset(
        {
            "audio_input_device_id",
            "audio_output_device_id",
            "default_tx_mode",
            "image_save_directory",
            "mmsstv_import_directory",
            "enable_auto_save",
            "ptt_method",
            "ptt_serial_port",
            "ptt_serial_baud",
            "ptt_serial_signal",
            "ptt_pre_delay_ms",
            "ptt_post_delay_ms",
            "vox_preamble_ms",
            "enable_stereo_guidance",
            "pilot_tone_hz",
            "enable_ai_captions",
            "enable_verbose_cli",
            "theme",
            "window_geometry",
            "window_state",
            "last_input_device",
            "last_output_device",
        }
    )

    def __init__(self, session: Session) -> None:
        """Initialize ConfigManager with a database session.

        Args:
            session: Active SQLAlchemy session for database operations.

        """
        self._session = session
        self._config = self._load_or_create()

    def _load_or_create(self) -> Any:
        """Load configuration from database or create with defaults.

        Returns:
            Configuration model instance.

        """
        from sstv_core.database.models import get_or_create_config

        return get_or_create_config(self._session)

    def reload(self) -> None:
        """Reload configuration from database.

        Use after external changes to the database.
        """
        with self._lock:
            self._session.expire(self._config)
            self._config = self._load_or_create()

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value.

        Args:
            key: Configuration field name (e.g., "default_tx_mode").
            default: Value to return if key doesn't exist.

        Returns:
            Configuration value or default.

        Raises:
            AttributeError: If key is not a valid configuration field.

        """
        with self._lock:
            if key in self.CORE_FIELDS:
                return getattr(self._config, key, default)
            # Check advanced settings
            return self._get_advanced_setting(key, default)

    def _get_advanced_setting(self, key: str, default: Any = None) -> Any:
        """Get a value from advanced_settings_json.

        Supports dot notation: "decoder.afc_enabled", "ui.canvas_zoom"

        Args:
            key: Dot-notation key (e.g., "decoder.vis_detection_threshold").
            default: Value to return if key doesn't exist.

        Returns:
            Setting value or default.

        """
        advanced = self.get_advanced_settings()
        parts = key.split(".")
        current = advanced.model_dump()

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default
        return current

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value with validation.

        Args:
            key: Configuration field name.
            value: New value to set.

        Raises:
            ValueError: If value fails validation.
            AttributeError: If key is not a valid configuration field.

        """
        with self._lock:
            if key in self.CORE_FIELDS:
                self._set_core_field(key, value)
            else:
                self._set_advanced_setting(key, value)

            self._session.commit()

    def _set_core_field(self, key: str, value: Any) -> None:
        """Set a core configuration field with validation.

        Args:
            key: Field name.
            value: New value.

        Raises:
            ValueError: If validation fails.

        """
        # Skip validation for non-validated fields
        if key in ("window_geometry", "window_state", "last_input_device", "last_output_device"):
            setattr(self._config, key, value)
            return

        # Validate using Pydantic model
        validation_data = self.to_dict()
        validation_data[key] = value

        # Filter to only validated fields
        validated_fields = {
            k: v
            for k, v in validation_data.items()
            if k in ConfigValidation.model_fields
        }

        # This will raise ValueError if validation fails
        ConfigValidation(**validated_fields)

        # If we get here, validation passed
        setattr(self._config, key, value)

    def _set_advanced_setting(self, key: str, value: Any) -> None:
        """Set a value in advanced_settings_json.

        Args:
            key: Dot-notation key (e.g., "decoder.afc_enabled").
            value: New value.

        Raises:
            ValueError: If validation fails.

        """
        advanced = self.get_advanced_settings()
        advanced_dict = advanced.model_dump()

        parts = key.split(".")
        current = advanced_dict
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]

        current[parts[-1]] = value

        # Validate with Pydantic
        validated = AdvancedSettings(**advanced_dict)

        # Save back to JSON
        self._config.advanced_settings_json = validated.model_dump_json()

    def update(self, values: dict[str, Any]) -> None:
        """Update multiple configuration values atomically.

        Args:
            values: Dict of key-value pairs to update.

        Raises:
            ValueError: If any value fails validation.

        """
        with self._lock:
            for key, value in values.items():
                if key in self.CORE_FIELDS:
                    self._set_core_field(key, value)
                else:
                    self._set_advanced_setting(key, value)

            self._session.commit()

    def to_dict(self) -> dict[str, Any]:
        """Get all configuration as a dictionary.

        Returns:
            Dict containing all configuration values.

        """
        with self._lock:
            result: dict[str, Any] = self._config.to_dict()
            return result

    def get_advanced_settings(self) -> AdvancedSettings:
        """Get advanced settings as a validated Pydantic model.

        Returns:
            AdvancedSettings instance with all advanced configuration.

        """
        with self._lock:
            json_str = self._config.advanced_settings_json
            if json_str:
                try:
                    data = json.loads(json_str)
                    return AdvancedSettings(**data)
                except (json.JSONDecodeError, ValueError):
                    # Return defaults on parse error
                    pass
            return AdvancedSettings()

    def set_advanced_settings(self, settings: AdvancedSettings) -> None:
        """Set all advanced settings from a validated model.

        Args:
            settings: AdvancedSettings instance.

        """
        with self._lock:
            self._config.advanced_settings_json = settings.model_dump_json()
            self._session.commit()

    def reset_to_defaults(self) -> None:
        """Reset all configuration to default values.

        Creates a new Configuration instance with defaults.
        """
        from sstv_core.database.models import Configuration

        with self._lock:
            # Delete existing config
            self._session.delete(self._config)
            self._session.commit()

            # Create new with defaults
            self._config = Configuration(id=1)
            self._session.add(self._config)
            self._session.commit()

    def validate_image_path(self, path: str) -> bool:
        """Validate that an image path is within the configured library.

        Args:
            path: Path to validate.

        Returns:
            True if path is valid and within library directory.

        """
        library_dir = self.get("image_save_directory")
        if not library_dir:
            return False

        try:
            path_obj = Path(path).resolve()
            library_path = Path(library_dir).resolve()
            return path_obj.is_relative_to(library_path)
        except (ValueError, OSError):
            return False

    def ensure_directories_exist(self) -> None:
        """Create configured directories if they don't exist.

        Creates image_save_directory and subdirectories.
        """
        with self._lock:
            image_dir = self.get("image_save_directory")
            if image_dir:
                path = Path(image_dir)
                path.mkdir(parents=True, exist_ok=True)
                (path / "received").mkdir(exist_ok=True)
                (path / "transmitted").mkdir(exist_ok=True)

    def get_guidance_config(self) -> Any:
        """Get accessibility guidance configuration.

        Returns:
            GuidanceConfig instance from accessibility settings.

        """
        from sstv_core.accessibility import GuidanceConfig

        advanced = self.get_advanced_settings()
        acc = advanced.accessibility

        return GuidanceConfig(
            enabled=acc.stereo_guidance_enabled,
            pilot_tone_freq=acc.pilot_tone_freq,
            pilot_tone_volume=acc.pilot_tone_volume,
            slant_threshold_degrees=acc.slant_threshold_degrees,
            max_pan_degrees=acc.max_pan_degrees,
            lock_chime_enabled=acc.lock_chime_enabled,
            lock_chime_volume=acc.lock_chime_volume,
        )
