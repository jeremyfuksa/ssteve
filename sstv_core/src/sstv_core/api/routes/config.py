"""Configuration endpoints wired to the database and ConfigManager.

Endpoints:
- GET /config
- POST /config
- PATCH /config
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from sstv_core.api.main import get_db_session
from sstv_core.api.models import Configuration, OperatingConditionMode, PTTMethod, SSTVMode
from sstv_core.config import ConfigManager

router = APIRouter(prefix="/config", tags=["config"])


def _get_config_manager(session: Session) -> ConfigManager:
    return ConfigManager(session)


def _normalize_ptt_method(value: str | PTTMethod) -> tuple[str, str | None]:
    if isinstance(value, str):
        try:
            value_enum = PTTMethod(value)
        except ValueError as exc:
            raise ValueError(f"Unknown PTT method '{value}'") from exc
    else:
        value_enum = value

    if value_enum == PTTMethod.SERIAL_RTS:
        return "serial", "RTS"
    if value_enum == PTTMethod.SERIAL_DTR:
        return "serial", "DTR"
    return value_enum.value, None


# One table, both directions.
#
# This used to be two hand-written functions: a chain of `if key in values`
# for writes and a hand-built Configuration(...) for reads. Adding a setting
# meant editing both, in opposite directions, and forgetting either half
# produced a silently unreachable field. That is exactly how nine
# accessibility settings -- including the stereo_guidance_enabled that PR #44
# shipped -- ended up stored but unsettable (#60).
#
# API field name -> ConfigManager key (dot-notation for AdvancedSettings).
_FIELD_TO_MANAGER_KEY: dict[str, str] = {
    "audio_input_device": "audio_input_device_id",
    "audio_output_device": "audio_output_device_id",
    "ptt_serial_port": "ptt_serial_port",
    "ptt_pre_delay_ms": "ptt_pre_delay_ms",
    "ptt_post_delay_ms": "ptt_post_delay_ms",
    "ptt_serial_baud": "ptt_serial_baud",
    "ptt_serial_signal": "ptt_serial_signal",
    "vox_preamble_ms": "vox_preamble_ms",
    "mmsstv_import_directory": "mmsstv_import_directory",
    # Decoder
    "auto_detect_mode": "decoder.auto_mode_detection_enabled",
    "auto_afc": "decoder.afc_enabled",
    "afc_range_hz": "decoder.afc_range_hz",
    "vis_detection_threshold": "decoder.vis_detection_threshold",
    "sync_detection_threshold": "decoder.sync_detection_threshold",
    "slant_auto_correct": "decoder.slant_auto_correct",
    # Encoder
    "pre_emphasis_enabled": "encoder.pre_emphasis_enabled",
    "color_space": "encoder.color_space",
    "jpeg_quality": "encoder.jpeg_quality",
    "enable_fskid_tx": "encoder.enable_fskid_tx",
    # UI
    "operating_mode": "ui.operating_mode",
    "waterfall_fft_size": "ui.waterfall_fft_size",
    "waterfall_visible": "ui.waterfall_visible",
    "canvas_zoom": "ui.canvas_zoom",
    "telemetry_panel_visible": "ui.telemetry_panel_visible",
    # Audio
    "auto_squelch": "audio.auto_squelch",
    "squelch_threshold_db": "audio.squelch_threshold_db",
    "buffer_size_samples": "audio.buffer_size_samples",
    "input_gain_override": "audio.input_gain_override",
    # Accessibility
    "stereo_guidance_enabled": "accessibility.stereo_guidance_enabled",
    "pilot_tone_freq": "accessibility.pilot_tone_freq",
    "pilot_tone_volume": "accessibility.pilot_tone_volume",
    "slant_threshold_degrees": "accessibility.slant_threshold_degrees",
    "max_pan_degrees": "accessibility.max_pan_degrees",
    "lock_chime_enabled": "accessibility.lock_chime_enabled",
    "lock_chime_volume": "accessibility.lock_chime_volume",
    "verbose_cli_enabled": "accessibility.verbose_cli_enabled",
    "json_logging_enabled": "accessibility.json_logging_enabled",
}

# Handled by conversion code rather than the table: ptt_method splits into
# method+signal, the mode is an enum, and the library path is expanded and
# resolved before storage.
_CONVERTED_FIELDS = frozenset(
    {"ptt_method", "default_transmit_mode", "image_library_path"}
)

# Stored as a plain string and written through the table, but returned as an
# enum, so the read loop skips it and the response builder converts it.
_ENUM_CONVERTED_ON_READ = frozenset({"operating_mode"})


def _build_manager_updates(values: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, Any] = {}

    for field, manager_key in _FIELD_TO_MANAGER_KEY.items():
        if field in values:
            updates[manager_key] = values[field]

    if "ptt_method" in values:
        method, signal = _normalize_ptt_method(values["ptt_method"])
        updates["ptt_method"] = method
        # An explicit ptt_serial_signal in the same payload wins: the caller
        # said RTS/DTR directly rather than implying it via the method.
        if signal and "ptt_serial_signal" not in values:
            updates["ptt_serial_signal"] = signal

    if "default_transmit_mode" in values:
        mode = values["default_transmit_mode"]
        updates["default_tx_mode"] = mode.value if isinstance(mode, SSTVMode) else mode

    if "image_library_path" in values:
        expanded = Path(values["image_library_path"]).expanduser()
        try:
            resolved = expanded.resolve()
        except OSError:
            resolved = expanded
        updates["image_save_directory"] = str(resolved)

    return updates


def _read_manager_value(manager: ConfigManager, advanced: Any, manager_key: str) -> Any:
    """Read one manager key, dot-notation or flat."""
    if "." in manager_key:
        section, field = manager_key.split(".", 1)
        return getattr(getattr(advanced, section), field)
    return manager.get(manager_key)


def _build_response(manager: ConfigManager) -> Configuration:
    advanced = manager.get_advanced_settings()
    ui = advanced.ui

    ptt_method = manager.get("ptt_method") or "none"
    if ptt_method == "serial":
        signal = manager.get("ptt_serial_signal") or "RTS"
        method = PTTMethod.SERIAL_DTR if signal.upper() == "DTR" else PTTMethod.SERIAL_RTS
    else:
        try:
            method = PTTMethod(ptt_method)
        except ValueError:
            method = PTTMethod.NONE

    try:
        mode_value = manager.get("default_tx_mode") or SSTVMode.MARTIN_M1.value
        mode = SSTVMode(mode_value)
    except ValueError:
        mode = SSTVMode.MARTIN_M1

    operating_mode_value = ui.operating_mode or OperatingConditionMode.STANDARD.value
    if operating_mode_value:
        try:
            operating_mode = OperatingConditionMode(operating_mode_value)
        except ValueError:
            operating_mode = OperatingConditionMode.STANDARD

    # Every table-driven field, read through the same mapping that writes
    # them. A None from a flat key means "never set" -- drop it so the
    # model default applies rather than pushing None into a non-optional
    # field. AdvancedSettings values are always present (Pydantic defaults).
    fields: dict[str, Any] = {}
    for field, manager_key in _FIELD_TO_MANAGER_KEY.items():
        if field in _ENUM_CONVERTED_ON_READ:
            continue
        value = _read_manager_value(manager, advanced, manager_key)
        if value is not None:
            fields[field] = value

    # Genuinely nullable: null means "automatic", not "unset".
    fields["input_gain_override"] = advanced.audio.input_gain_override
    fields["mmsstv_import_directory"] = manager.get("mmsstv_import_directory")

    return Configuration(
        **fields,
        ptt_method=method,
        default_transmit_mode=mode,
        image_library_path=(
            manager.get("image_save_directory") or os.path.expanduser("~/sstv_images")
        ),
        operating_mode=operating_mode,
    )


def _validate_patch(manager: ConfigManager, patch_values: dict[str, Any]) -> None:
    current = _build_response(manager).model_dump()
    merged = {**current, **patch_values}
    Configuration(**merged)


@router.get("", response_model=Configuration)
async def get_config(session: Session = Depends(get_db_session)) -> Configuration:
    """Return the current configuration stored in the database."""
    manager = _get_config_manager(session)
    return _build_response(manager)


@router.get("/schema")
async def get_config_schema() -> dict[str, Any]:
    """Return the JSON Schema for Configuration.

    backend-spec.md:504 promised GET /config returns the "full schema" and
    there was no way to introspect one, so a client had to hardcode the
    field list -- and go stale the moment a setting was added. This serves
    Pydantic's own schema: types, ranges, defaults, and descriptions, all
    generated from the model rather than restated.
    """
    return Configuration.model_json_schema()


@router.post("", response_model=Configuration)
async def update_config(
    config: Configuration,
    session: Session = Depends(get_db_session),
) -> Configuration:
    """Replace the entire configuration."""
    manager = _get_config_manager(session)
    manager.reset_to_defaults()
    updates = _build_manager_updates(config.model_dump())

    try:
        manager.update(updates)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "VALIDATION_ERROR",
                "message": str(exc),
                "suggested_action": "Review the configuration values and try again",
            },
        ) from exc

    manager.ensure_directories_exist()
    return _build_response(manager)


@router.patch("", response_model=Configuration)
async def patch_config(
    updates: dict[str, Any],
    session: Session = Depends(get_db_session),
) -> Configuration:
    """Update specific configuration fields."""
    manager = _get_config_manager(session)

    try:
        _validate_patch(manager, updates)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "VALIDATION_ERROR",
                "message": str(exc),
                "suggested_action": "Fix the invalid fields and try again",
            },
        ) from exc

    try:
        manager.update(_build_manager_updates(updates))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "VALIDATION_ERROR",
                "message": str(exc),
                "suggested_action": "Review the configuration values and try again",
            },
        ) from exc

    manager.ensure_directories_exist()
    return _build_response(manager)
