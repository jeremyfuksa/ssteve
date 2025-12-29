"""
Device enumeration endpoints.

Handles:
- GET /devices/audio - List available audio devices
- GET /devices/serial - List available serial ports (for PTT)
"""

from typing import List

from fastapi import APIRouter

from sstv_core.api.models import AudioDevice, SerialPort


router = APIRouter(prefix="/devices", tags=["devices"])


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
    # TODO: Implement actual audio device enumeration using sounddevice
    # For now, return mock data for API development
    return [
        AudioDevice(
            device_id="0",
            name="Built-in Audio",
            channels=2,
            sample_rate=48000,
            is_default=True,
        ),
        AudioDevice(
            device_id="1",
            name="USB Audio Device",
            channels=2,
            sample_rate=48000,
            is_default=False,
        ),
    ]


@router.get("/serial", response_model=List[SerialPort])
async def list_serial_ports() -> List[SerialPort]:
    """
    List available serial ports for PTT control.

    Returns all serial ports detected by the system, including:
    - Port identifier (e.g., COM3, /dev/ttyUSB0)
    - Description and manufacturer (if available)

    Used for PTT serial port selection in the UI.
    """
    # TODO: Implement actual serial port enumeration using pyserial
    # For now, return mock data for API development
    return [
        SerialPort(
            port="/dev/ttyUSB0",
            description="USB Serial Device",
            manufacturer="FTDI",
        ),
        SerialPort(
            port="/dev/ttyUSB1",
            description="Arduino Uno",
            manufacturer="Arduino",
        ),
    ]
