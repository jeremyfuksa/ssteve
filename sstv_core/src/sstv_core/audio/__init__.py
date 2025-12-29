"""Audio management for SSTeVe core engine.

Provides audio device enumeration, stream management, and ring buffers
for real-time audio I/O operations.

Modules:
    device_manager: Audio device enumeration and selection
    stream_manager: Audio input/output stream handling
    ring_buffer: Thread-safe ring buffer for audio samples
    ptt_controller: PTT (Push-To-Talk) control via Serial or VOX
"""

# Imports are deferred to avoid circular import issues
# Individual modules can be imported directly:
#   from sstv_core.audio.device_manager import AudioDeviceManager
#   from sstv_core.audio.stream_manager import AudioStreamManager
#   from sstv_core.audio.ring_buffer import AudioRingBuffer
#   from sstv_core.audio.ptt_controller import PTTController

__all__ = [
    "AudioDevice",
    "AudioDeviceManager",
    "AudioStreamManager",
    "AudioLevels",
    "AudioRingBuffer",
    "PTTController",
    "PTTMethod",
]


def __getattr__(name: str):
    """Lazy import for audio module components."""
    if name in ("AudioDevice", "AudioDeviceManager"):
        from sstv_core.audio.device_manager import AudioDevice, AudioDeviceManager
        return AudioDevice if name == "AudioDevice" else AudioDeviceManager
    elif name in ("AudioStreamManager", "AudioLevels"):
        from sstv_core.audio.stream_manager import AudioStreamManager, AudioLevels
        return AudioStreamManager if name == "AudioStreamManager" else AudioLevels
    elif name == "AudioRingBuffer":
        from sstv_core.audio.ring_buffer import AudioRingBuffer
        return AudioRingBuffer
    elif name in ("PTTController", "PTTMethod"):
        from sstv_core.audio.ptt_controller import PTTController, PTTMethod
        return PTTController if name == "PTTController" else PTTMethod
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
