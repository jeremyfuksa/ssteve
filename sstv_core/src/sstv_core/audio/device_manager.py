"""Audio device enumeration and management for SSTeVe."""

from __future__ import annotations

import logging
import platform
import re
import threading
from dataclasses import dataclass, field
from typing import Any, ClassVar

import sounddevice as sd

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AudioDevice:
    """Represents an audio device with its capabilities."""

    id: str
    name: str
    hostapi: str
    channels: int
    sample_rates: list[int] = field(default_factory=list)
    is_input: bool = False
    is_output: bool = False
    is_default: bool = False
    raw_info: dict = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "hostapi": self.hostapi,
                "channels": self.channels, "sample_rates": self.sample_rates,
                "is_input": self.is_input, "is_output": self.is_output,
                "is_default": self.is_default}


class AudioDeviceError(Exception):
    pass


class AudioDeviceManager:
    """Manages audio device enumeration and selection."""

    STANDARD_SAMPLE_RATES: ClassVar[list[int]] = [8000, 11025, 16000, 22050, 44100, 48000, 96000]
    SSTV_SAMPLE_RATE = 48000

    def __init__(
        self,
        probe_sample_rates: bool = False,
    ) -> None:
        self._lock = threading.RLock()
        self._probe_sample_rates = probe_sample_rates
        self._devices: list[AudioDevice] = []
        self._input_devices: list[AudioDevice] = []
        self._output_devices: list[AudioDevice] = []
        self._device_map: dict[str, AudioDevice] = {}
        self._default_input_id: str | None = None
        self._default_output_id: str | None = None
        self._hostapis: list = []
        self.refresh()

    def refresh(self) -> None:
        with self._lock:
            self._enumerate_devices()

    def _enumerate_devices(self) -> None:
        try:
            hostapis_result = sd.query_hostapis()
            self._hostapis = (
                list(hostapis_result)
                if isinstance(hostapis_result, (list, tuple))
                else hostapis_result
            )
            devices_info = sd.query_devices()
            default_input, default_output = sd.default.device
            self._devices, self._input_devices, self._output_devices = [], [], []
            self._device_map = {}
            self._default_input_id = self._default_output_id = None
            if isinstance(devices_info, dict):
                devices_info = [devices_info]
            for idx, info in enumerate(devices_info):
                device = self._create_device(idx, info, default_input, default_output)
                if device is None:
                    continue
                self._devices.append(device)
                self._device_map[device.id] = device
                if device.is_input:
                    self._input_devices.append(device)
                    if device.is_default:
                        self._default_input_id = device.id
                if device.is_output:
                    self._output_devices.append(device)
                    if device.is_default:
                        self._default_output_id = device.id
        except sd.PortAudioError as e:
            if not self._devices:
                raise AudioDeviceError(f"Can't find any audio devices: {e}") from e

    def _create_device(self, idx, info, default_input, default_output):
        name = info.get("name", f"Device {idx}")
        max_in = info.get("max_input_channels", 0)
        max_out = info.get("max_output_channels", 0)
        if max_in == 0 and max_out == 0:
            return None
        hostapi_idx = info.get("hostapi", 0)
        hostapi_name = (
            self._hostapis[hostapi_idx].get("name", "Unknown")
            if hostapi_idx < len(self._hostapis)
            else "Unknown"
        )
        device_id = self._generate_device_id(idx, name, hostapi_name)
        is_input, is_output = max_in > 0, max_out > 0
        is_default = (idx == default_input and is_input) or (idx == default_output and is_output)
        sample_rates = (
            self._probe_device_sample_rates(idx, is_input)
            if self._probe_sample_rates
            else [int(info.get("default_samplerate", 48000))]
        )
        return AudioDevice(id=device_id, name=self._clean_device_name(name), hostapi=hostapi_name,
                           channels=max_in if is_input else max_out, sample_rates=sample_rates,
                           is_input=is_input, is_output=is_output, is_default=is_default,
                           raw_info=dict(info))

    def _generate_device_id(self, idx, name, hostapi):
        p = platform.system().lower()
        if p == "linux":
            m = re.search(r"(hw:\d+,\d+)", name)
            if m:
                return m.group(1)
        elif p == "darwin":
            pattern = r'[^a-zA-Z0-9]'
            cleaned = re.sub(pattern, '_', name)
            return f"ca_{cleaned}"
        elif p == "windows":
            return f"{'wasapi' if 'WASAPI' in hostapi else 'ds'}_{idx}"
        return str(idx)

    def _clean_device_name(self, name):
        name = re.sub(r"^(HDA Intel PCH:|ALSA:)", "", name)
        name = re.sub(r"\s*\(hw:\d+,\d+\)\s*$", "", name).strip()
        return (name[:57] + "...") if len(name) > 60 else (name or "Unknown Device")

    def _probe_device_sample_rates(self, device_idx, is_input):
        supported = []
        for rate in self.STANDARD_SAMPLE_RATES:
            try:
                check = sd.check_input_settings if is_input else sd.check_output_settings
                check(device=device_idx, samplerate=rate)
                supported.append(rate)
            except sd.PortAudioError:
                pass
        return supported

    def list_all_devices(self):
        with self._lock:
            return list(self._devices)

    def list_input_devices(self):
        with self._lock:
            return list(self._input_devices)

    def list_output_devices(self):
        with self._lock:
            return list(self._output_devices)

    def get_device(self, device_id):
        with self._lock:
            return self._device_map.get(device_id)

    def get_device_index(self, device_id):
        with self._lock:
            device = self._device_map.get(device_id)
            if device and device.raw_info:
                try:
                    all_devices = sd.query_devices()
                    if isinstance(all_devices, dict):
                        all_devices = [all_devices]
                    for idx, info in enumerate(all_devices):
                        if info.get("name") == device.raw_info.get("name"):
                            return idx
                except sd.PortAudioError:
                    pass
            return None

    def get_default_input_device(self):
        with self._lock:
            if self._default_input_id:
                return self._device_map.get(self._default_input_id)
            return self._input_devices[0] if self._input_devices else None

    def get_default_output_device(self):
        with self._lock:
            if self._default_output_id:
                return self._device_map.get(self._default_output_id)
            return self._output_devices[0] if self._output_devices else None

    def validate_device(self, device_id, require_input=False, require_output=False):
        with self._lock:
            device = self._device_map.get(device_id)
            if not device:
                return False
            if require_input and not device.is_input:
                return False
            if require_output and not device.is_output:
                return False
            return True

    def to_api_response(self):
        with self._lock:
            return {
                "inputs": [d.to_dict() for d in self._input_devices],
                "outputs": [d.to_dict() for d in self._output_devices],
            }
