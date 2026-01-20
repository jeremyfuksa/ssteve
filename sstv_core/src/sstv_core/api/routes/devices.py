"""
Device enumeration endpoints.

Handles:
- GET /devices/audio - List available audio devices
- GET /devices/serial - List available serial ports (for PTT)
- GET /devices/detect - Auto-detect connected hardware
- POST /devices/apply_settings - Apply recommended device settings
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel

from sstv_core.api.models import (
    AudioDevice,
    SerialPort,
)
from sstv_core.smart_features.device_detector import (
    detect_hardware_device,
    get_recommended_settings,
    generate_detection_message,
    generate_settings_preview,
)
from sstv_core.config.manager import config_manager

_SSTV_SAMPLE_RATE = 48000


def _pick_sample_rate(sample_rates: list[int]) -> int:
    if _SSTV_SAMPLE_RATE in sample_rates:
        return _SSTV_SAMPLE_RATE
    return sample_rates[0] if sample_rates else _SSTV_SAMPLE_RATE


@router.get("/detect", response_model=DeviceDetectionResponse)
async def detect_devices() -> DeviceDetectionResponse:
    """
    Auto-detect connected SSTV hardware and provide recommended settings.

    Analyzes serial ports and audio devices to identify known hardware
    like Digirig, SignaLink, RigBlaster. Returns recommended configuration
    settings for PTT control, audio routing, and timing parameters.

    Returns:
        - Detected device profile (if any)
        - User-friendly detection message
        - Recommended configuration settings
        - Preview of what will change

    Raises:
        503 Service Unavailable: If device enumeration fails
    """
    try:
        # Detect hardware
        detected_profile = detect_hardware_device()

        # Get current configuration
        current_config = config_manager.get_all()

        # Generate detection message
        detection_message = generate_detection_message(detected_profile) if detected_profile else None

        # Get recommended settings
        recommended_settings = get_recommended_settings(detected_profile) if detected_profile else {}

        # Generate settings preview
        settings_preview = generate_settings_preview(current_config, recommended_settings)

        # Build response
        return DeviceDetectionResponse(
            detected_profile=detected_profile.name if detected_profile else None,
            detection_message=detection_message,
            recommended_settings=recommended_settings,
            settings_preview=settings_preview,
        )

    except Exception as e:
        # Log error and return 503
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "DEVICE_DETECTION_ERROR",
                "message": f"Failed to detect devices: {str(e)}",
            },
        ) from e


@router.post("/apply_settings", response_model=ApplySettingsResponse)
async def apply_device_settings(request: ApplySettingsRequest) -> ApplySettingsResponse:
    """
    Apply recommended or custom device settings.

    Accepts a partial configuration update with PTT, audio, and timing
    parameters. Validates settings and updates the global configuration.

    Returns:
        - Updated configuration after applying settings
        - List of fields that were updated

    Raises:
        400 Bad Request: If settings are invalid
        404 Not Found: If referenced devices don't exist
    """
    try:
        # Build settings to apply
        updates = {}

        # PTT settings
        if request.ptt_method is not None:
            updates["ptt_method"] = request.ptt_method
        if request.ptt_serial_signal is not None:
            updates["ptt_serial_signal"] = request.ptt_serial_signal
        if request.ptt_pre_delay_ms is not None:
            updates["ptt_pre_delay_ms"] = request.ptt_pre_delay_ms
        if request.ptt_post_delay_ms is not None:
            updates["ptt_post_delay_ms"] = request.ptt_post_delay_ms
        if request.vox_preamble_ms is not None:
            updates["vox_preamble_ms"] = request.vox_preamble_ms

        # Audio device settings
        if request.audio_input_device_id is not None:
            updates["audio_input_device_id"] = request.audio_input_device_id
        if request.audio_output_device_id is not None:
            updates["audio_output_device_id"] = request.audio_output_device_id

        # If profile_name provided, use device profile defaults
        if request.profile_name is not None:
            # Apply profile-based settings
            detected_profile = detect_hardware_device()
            if detected_profile and detected_profile.name == request.profile_name:
                profile_settings = get_recommended_settings(detected_profile)
                # Merge profile settings (profile doesn't override explicit settings)
                for key, value in profile_settings.items():
                    if key not in updates:  # Don't override explicit settings
                        updates[key] = value

        if not updates:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "NO_SETTINGS_TO_APPLY",
                    "message": "No settings provided to update. Please provide at least one setting.",
                    "suggested_action": "Include PTT method, audio device IDs, or device profile name",
                },
            )

        # Apply updates to configuration
        config_manager.update_many(updates)

        # Save to database
        config_manager.save()

        # Build response
        applied_fields = list(updates.keys())

        # Get updated configuration
        updated_config = config_manager.get_all()

        return ApplySettingsResponse(
            updated_configuration=updated_config,
            applied_fields=applied_fields,
        )

    except ValueError as e:
        # Validation error (e.g., invalid device ID)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "VALIDATION_ERROR",
                "message": str(e),
                "suggested_action": "Check your settings values and try again",
            },
        ) from e
    except Exception as e:
        # Log error and return 500
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "SETTINGS_UPDATE_ERROR",
                "message": f"Failed to apply settings: {str(e)}",
                "recoverable": False,
            },
        ) from e


@router.get("/audio", response_model=List[AudioDevice])
async def list_audio_devices() -> List[AudioDevice]:
    """
    List available audio input/output devices.

    Returns all audio devices detected by the system, including:
    - Device ID (OS-specific identifier)
    - Human-readable name
    - Channel count and sample rate
    - Default device indicator

    Used for device selection in the UI.
    """
    try:
        from sstv_core.smart_features.device_detector import (
    detect_hardware_device,
    get_recommended_settings,
    generate_detection_message,
    generate_settings_preview,
)

        manager = AudioDeviceManager()
        devices = manager.list_all_devices()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "DEVICE_FAILURE",
                "message": f"Can't list audio devices - {e}",
                "recoverable": True,
                "suggested_action": "Check your audio connections and try again",
            },
        ) from e

    response: List[AudioDevice] = []
    for device in devices:
        response.append(
            AudioDevice(
                device_id=device.id,
                name=device.name,
                channels=device.channels,
                sample_rate=_pick_sample_rate(device.sample_rates),
                is_default=device.is_default,
            )
        )

    return response


@router.get("/serial", response_model=List[SerialPort])
async def list_serial_ports() -> List[SerialPort]:
    """
    List available serial ports for PTT control.

    Returns all serial ports detected by the system, including:
    - Port identifier (e.g., COM3, /dev/ttyUSB0)
    - Description and manufacturer (if available)

    Used for PTT serial port selection in the UI.
    """
    if list_ports is None:
        return []

    try:
        ports = list_ports.comports()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "DEVICE_FAILURE",
                "message": f"Can't list serial ports - {e}",
                "recoverable": True,
                "suggested_action": "Check serial device connections and try again",
            },
        ) from e

    response: List[SerialPort] = []
    for port in ports:
        response.append(
            SerialPort(
                port=port.device,
                description=port.description or "",
                manufacturer=port.manufacturer,
            )
        )
    return response
