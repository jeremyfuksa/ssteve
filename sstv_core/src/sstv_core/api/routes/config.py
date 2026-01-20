"""
Configuration endpoints wired to the database and ConfigManager.

Endpoints:
- GET /config
- POST /config
- PATCH /config
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

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


def _build_manager_updates(values: Dict[str, Any]) -> Dict[str, Any]:
    updates: Dict[str, Any] = {}

    if "audio_input_device" in values:
        updates["audio_input_device_id"] = values["audio_input_device"]

    if "audio_output_device" in values:
        updates["audio_output_device_id"] = values["audio_output_device"]

    if "ptt_method" in values:
        method_str = values["ptt_method"]
        method, signal = _normalize_ptt_method(method_str)
        updates["ptt_method"] = method
        if signal:
            updates["ptt_serial_signal"] = signal

    if "ptt_serial_port" in values:
        updates["ptt_serial_port"] = values["ptt_serial_port"]

    if "ptt_pre_delay_ms" in values:
        updates["ptt_pre_delay_ms"] = values["ptt_pre_delay_ms"]

    if "ptt_post_delay_ms" in values:
        updates["ptt_post_delay_ms"] = values["ptt_post_delay_ms"]

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

    if "operating_mode" in values:
        updates["ui.operating_mode"] = values["operating_mode"]

    if "auto_detect_mode" in values:
        updates["decoder.auto_mode_detection_enabled"] = values["auto_detect_mode"]

    if "auto_afc" in values:
        updates["decoder.afc_enabled"] = values["auto_afc"]

    if "afc_range_hz" in values:
        updates["decoder.afc_range_hz"] = values["afc_range_hz"]

    if "auto_squelch" in values:
        updates["audio.auto_squelch"] = values["auto_squelch"]

    if "squelch_threshold_db" in values:
        updates["audio.squelch_threshold_db"] = values["squelch_threshold_db"]

    return updates


def _build_response(manager: ConfigManager) -> Configuration:
    advanced = manager.get_advanced_settings()
    decoder = advanced.decoder
    audio = advanced.audio
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

    return Configuration(
        audio_input_device=manager.get("audio_input_device_id"),
        audio_output_device=manager.get("audio_output_device_id"),
        ptt_method=method,
        ptt_serial_port=manager.get("ptt_serial_port"),
        ptt_pre_delay_ms=manager.get("ptt_pre_delay_ms") or 500,
        ptt_post_delay_ms=manager.get("ptt_post_delay_ms") or 200,
        default_transmit_mode=mode,
        image_library_path=manager.get("image_save_directory") or os.path.expanduser("~/sstv_images"),
        operating_mode=operating_mode,
        auto_detect_mode=decoder.auto_mode_detection_enabled,
        auto_afc=decoder.afc_enabled,
        afc_range_hz=decoder.afc_range_hz,
        auto_squelch=audio.auto_squelch,
        squelch_threshold_db=audio.squelch_threshold_db,
    )


def _validate_patch(manager: ConfigManager, patch_values: Dict[str, Any]) -> None:
    current = _build_response(manager).model_dump()
    merged = {**current, **patch_values}
    Configuration(**merged)


@router.get("", response_model=Configuration)
async def get_config(session: Session = Depends(get_db_session)) -> Configuration:
    """Return the current configuration stored in the database."""
    manager = _get_config_manager(session)
    return _build_response(manager)


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
    updates: Dict[str, Any],
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
