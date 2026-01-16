"""
Device enumeration endpoints.

Handles:
- GET /devices/audio - List available audio devices
- GET /devices/serial - List available serial ports (for PTT)
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, status

from sstv_core.api.models import AudioDevice, SerialPort

try:
    from serial.tools import list_ports
except Exception:  # pragma: no cover - depends on optional pyserial
    list_ports = None


router = APIRouter(prefix="/devices", tags=["devices"])

_SSTV_SAMPLE_RATE = 48000


def _pick_sample_rate(sample_rates: list[int]) -> int:
    if _SSTV_SAMPLE_RATE in sample_rates:
        return _SSTV_SAMPLE_RATE
    return sample_rates[0] if sample_rates else _SSTV_SAMPLE_RATE


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
        from sstv_core.audio.device_manager import AudioDeviceManager, AudioDeviceError

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
