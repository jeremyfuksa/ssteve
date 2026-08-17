"""Device enumeration endpoints.

Handles:
- GET /devices/audio - List available audio devices
- GET /devices/serial - List available serial ports (for PTT)
- GET /devices/detect - Auto-detect connected hardware
- POST /devices/apply_settings - Apply recommended device settings
"""


from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from sstv_core.api.main import get_db_session
from sstv_core.api.models import (
    ApplySettingsRequest,
    ApplySettingsResponse,
    AudioDevice,
    DeviceDetectionResponse,
    SerialPort,
)
from sstv_core.config import ConfigManager

router = APIRouter(prefix="/devices", tags=["devices"])


def _get_config_manager(session: Session = Depends(get_db_session)) -> ConfigManager:
    """Get config manager with database session."""
    return ConfigManager(session)

# Import device detector if available
try:
    from sstv_core.smart_features import device_detector
    _device_detector_available = True
except ImportError:
    _device_detector_available = False

try:
    from serial.tools import list_ports
except Exception:  # pragma: no cover - depends on optional pyserial
    list_ports = None


_SSTV_SAMPLE_RATE = 48000


def _pick_sample_rate(sample_rates: list[int]) -> int:
    if _SSTV_SAMPLE_RATE in sample_rates:
        return _SSTV_SAMPLE_RATE
    return sample_rates[0] if sample_rates else _SSTV_SAMPLE_RATE


@router.get("/detect", response_model=DeviceDetectionResponse)
async def detect_devices(
    config_manager: ConfigManager = Depends(_get_config_manager),
) -> DeviceDetectionResponse:
    """Auto-detect connected SSTV hardware and provide recommended settings.

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
        if _device_detector_available:
            detected_profile = device_detector.detect_hardware_device()
            # Get recommended settings from detected profile
            recommended_settings = (
                device_detector.get_recommended_settings(detected_profile)
                if detected_profile
                else {}
            )
        else:
            detected_profile = None
            recommended_settings = {}

        # Get current configuration
        current_config = config_manager.to_dict()

        # Generate detection message
        detection_message = (
            device_detector.generate_detection_message(detected_profile)
            if detected_profile
            else None
        )

        # Generate settings preview
        settings_preview = device_detector.generate_settings_preview(
            current_config,
            recommended_settings,
        )

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
                "message": f"Failed to detect devices: {e!s}",
            },
        ) from e


@router.post("/apply_settings", response_model=ApplySettingsResponse)
async def apply_device_settings(
    request: ApplySettingsRequest,
    config_manager: ConfigManager = Depends(_get_config_manager),
) -> ApplySettingsResponse:
    """Apply recommended or custom device settings.

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
        updates: dict[str, Any] = {}

        # PTT settings. Normalize the public spellings serial_rts/serial_dtr
        # into stored method + signal, same as the /config routes -- writing
        # the raw string used to fail ConfigManager's pattern and 400 the
        # documented values.
        if request.ptt_method is not None:
            from sstv_core.api.routes.config import _normalize_ptt_method

            method, signal = _normalize_ptt_method(request.ptt_method)
            updates["ptt_method"] = method
            if signal:
                updates["ptt_serial_signal"] = signal
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
        if request.profile_name is not None and _device_detector_available:
            # Apply profile-based settings
            detected_profile = device_detector.detect_hardware_device()
            if detected_profile and detected_profile.name == request.profile_name:
                profile_settings = device_detector.get_recommended_settings(detected_profile)
                # Merge profile settings (profile doesn't override explicit settings)
                for key, value in profile_settings.items():
                    if key not in updates:  # Don't override explicit settings
                        updates[key] = value

        if not updates:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "NO_SETTINGS_TO_APPLY",
                    "message": "No settings provided to update. "
                    "Please provide at least one setting.",
                    "suggested_action": "Include PTT method, audio device IDs, "
                    "or device profile name",
                },
            )

        # Apply updates to configuration
        config_manager.update(updates)

        # Build response
        applied_fields = list(updates.keys())

        # Get updated configuration
        updated_config = config_manager.to_dict()

        return ApplySettingsResponse(
            updated_configuration=updated_config,
            applied_fields=applied_fields,
        )

    except HTTPException:
        raise
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
                "message": f"Failed to apply settings: {e!s}",
                "recoverable": False,
            },
        ) from e


@router.get("/audio", response_model=list[AudioDevice])
async def list_audio_devices() -> list[AudioDevice]:
    """List available audio input/output devices.

    Returns all audio devices detected by the system, including:
    - Device ID (OS-specific identifier)
    - Human-readable name
    - Channel count and sample rate
    - Default device indicator

    Used for device selection in the UI.
    """
    try:
        from sstv_core.audio.device_manager import AudioDeviceManager

        device_manager = AudioDeviceManager()
        devices = device_manager.list_all_devices()

        return [
            AudioDevice(
                device_id=str(device.id),
                name=device.name,
                channels=device.channels,
                sample_rate=_pick_sample_rate(device.sample_rates),
                # device_manager probes every supported rate; serving only
                # the pick left a client unable to offer the alternatives.
                sample_rates=sorted(device.sample_rates),
                is_input=device.is_input,
                is_output=device.is_output,
                is_default=device.is_default,
            )
            for device in devices
        ]

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "DEVICE_ENUMERATION_FAILED",
                "message": f"Failed to enumerate audio devices: {e!s}",
                "suggested_action": "Check audio driver installation and permissions",
            },
        ) from e
@router.get("/serial", response_model=list[SerialPort])
async def list_serial_ports() -> list[SerialPort]:
    """List available serial ports for PTT control.

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

    response: list[SerialPort] = []
    for port in ports:
        response.append(
            SerialPort(
                port=port.device,
                description=port.description or "",
                manufacturer=port.manufacturer,
            )
        )
    return response
