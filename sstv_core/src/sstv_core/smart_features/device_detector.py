"""Smart Device Configuration - Auto-detect and configure common SSTV hardware.

This module detects popular SSTV interfaces (Digirig, SignaLink, RigBlaster) and
provides recommended settings for PTT control, audio routing, and timing parameters.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

try:
    from serial.tools import list_ports
except Exception:
    list_ports = None


@dataclass
class DeviceProfile:
    """Configuration profile for a recognized device."""

    name: str
    device_type: str  # "audio_interface", "serial_ptt", "vox"
    manufacturer: str

    # PTT settings
    ptt_method: str  # "serial", "vox", "none"
    ptt_serial_signal: Optional[str] = None  # "RTS" or "DTR"
    ptt_pre_delay_ms: int = 500
    ptt_post_delay_ms: int = 200
    vox_preamble_ms: int = 500

    # Audio settings
    recommended_input_device: Optional[str] = None
    recommended_output_device: Optional[str] = None

    # Identification patterns
    usb_vid: Optional[int] = None
    usb_pid: Optional[int] = None
    device_name_pattern: Optional[str] = None  # For audio device name matching

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "name": self.name,
            "device_type": self.device_type,
            "manufacturer": self.manufacturer,
            "ptt_method": self.ptt_method,
            "ptt_serial_signal": self.ptt_serial_signal,
            "ptt_pre_delay_ms": self.ptt_pre_delay_ms,
            "ptt_post_delay_ms": self.ptt_post_delay_ms,
            "vox_preamble_ms": self.vox_preamble_ms,
            "recommended_input_device": self.recommended_input_device,
            "recommended_output_device": self.recommended_output_device,
        }


# Known device profiles
DEVICE_PROFILES = [
    DeviceProfile(
        name="Digirig Mobile",
        device_type="serial_ptt",
        manufacturer="Digirig",
        ptt_method="serial",
        ptt_serial_signal="RTS",
        ptt_pre_delay_ms=500,
        ptt_post_delay_ms=200,
        usb_vid=0x0403,  # FTDI chipset
        usb_pid=0x6015,  # FT231X USB-Serial
    ),
    DeviceProfile(
        name="SignaLink USB",
        device_type="vox",
        manufacturer="Tigertronics",
        ptt_method="vox",
        vox_preamble_ms=500,
        device_name_pattern="SignaLink",  # Match audio device name
    ),
    DeviceProfile(
        name="RigBlaster",
        device_type="serial_ptt",
        manufacturer="West Mountain Radio",
        ptt_method="serial",
        ptt_serial_signal="DTR",
        ptt_pre_delay_ms=500,
        ptt_post_delay_ms=200,
        usb_vid=0x067B,  # Prolific chipset
    ),
    DeviceProfile(
        name="Easy Digi",
        device_type="vox",
        manufacturer="MFJ",
        ptt_method="vox",
        vox_preamble_ms=500,
        device_name_pattern="Easy Digi",
    ),
]


def detect_serial_devices() -> List[Dict]:
    """Detect connected serial devices.

    Returns:
        List of serial port info dictionaries
    """
    if list_ports is None:
        return []

    ports = []
    for port in list_ports.comports():
        port_info = {
            "port": port.device,
            "description": port.description,
            "manufacturer": port.manufacturer or "Unknown",
            "vid": port.vid,
            "pid": port.pid,
        }
        ports.append(port_info)
    return ports


def detect_hardware_device(serial_ports: Optional[List[Dict]] = None) -> Optional[DeviceProfile]:
    """Detect known SSTV hardware based on USB VID/PID.

    Args:
        serial_ports: Optional list of serial ports (will auto-detect if None)

    Returns:
        DeviceProfile if known device detected, None otherwise
    """
    if serial_ports is None:
        serial_ports = detect_serial_devices()

    for port in serial_ports:
        vid = port.get("vid")
        pid = port.get("pid")

        if vid is None:
            continue

        # Check against known device profiles
        for profile in DEVICE_PROFILES:
            if profile.usb_vid is None:
                continue

            # Match VID (and PID if specified)
            if profile.usb_vid == vid:
                if profile.usb_pid is None or profile.usb_pid == pid:
                    # Found matching device
                    matched_profile = DeviceProfile(
                        name=profile.name,
                        device_type=profile.device_type,
                        manufacturer=profile.manufacturer,
                        ptt_method=profile.ptt_method,
                        ptt_serial_signal=profile.ptt_serial_signal,
                        ptt_pre_delay_ms=profile.ptt_pre_delay_ms,
                        ptt_post_delay_ms=profile.ptt_post_delay_ms,
                        vox_preamble_ms=profile.vox_preamble_ms,
                        usb_vid=vid,
                        usb_pid=pid,
                    )
                    # Store the actual serial port
                    matched_profile.recommended_input_device = port["port"]
                    return matched_profile

    return None


def detect_audio_device_profile(device_name: str) -> Optional[DeviceProfile]:
    """Detect known SSTV hardware based on audio device name.

    Args:
        device_name: Audio device name string

    Returns:
        DeviceProfile if known device detected, None otherwise
    """
    device_name_lower = device_name.lower()

    for profile in DEVICE_PROFILES:
        if profile.device_name_pattern is None:
            continue

        pattern_lower = profile.device_name_pattern.lower()
        if pattern_lower in device_name_lower:
            return profile

    return None


def get_recommended_settings(profile: DeviceProfile) -> Dict:
    """Get recommended configuration settings for a device profile.

    Args:
        profile: Device profile to generate settings for

    Returns:
        Dictionary of configuration key-value pairs
    """
    settings = {
        "ptt_method": profile.ptt_method,
        "ptt_pre_delay_ms": profile.ptt_pre_delay_ms,
        "ptt_post_delay_ms": profile.ptt_post_delay_ms,
    }

    if profile.ptt_method == "serial":
        settings["ptt_serial_signal"] = profile.ptt_serial_signal
        if profile.recommended_input_device:
            settings["ptt_serial_port"] = profile.recommended_input_device

    elif profile.ptt_method == "vox":
        settings["vox_preamble_ms"] = profile.vox_preamble_ms

    if profile.recommended_input_device:
        settings["audio_input_device_id"] = profile.recommended_input_device

    if profile.recommended_output_device:
        settings["audio_output_device_id"] = profile.recommended_output_device

    return settings


def generate_detection_message(profile: DeviceProfile) -> str:
    """Generate user-friendly detection message in SSTeVe voice.

    Args:
        profile: Detected device profile

    Returns:
        Message for UI display
    """
    return f"Oh hey, I see you've got a {profile.name}! I know how to set that up - want me to do it?"


def generate_settings_preview(current_settings: Dict, recommended_settings: Dict) -> Dict:
    """Generate a preview of settings changes.

    Args:
        current_settings: Current configuration values
        recommended_settings: Recommended configuration values

    Returns:
        Dictionary showing what will change: {field: {"old": value, "new": value}}
    """
    preview = {}

    for key, new_value in recommended_settings.items():
        old_value = current_settings.get(key)
        if old_value != new_value:
            preview[key] = {
                "old": old_value,
                "new": new_value,
            }

    return preview
