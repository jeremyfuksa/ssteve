"""SSTV decoding module for SSTeVe core engine.

Provides VIS code detection, sync pulse detection, and mode-specific decoders.

Modules:
    vis_detector: VIS code detection using Goertzel filtering
    sync_detector: Sync pulse detection and mode timing analysis
    scottie_decoder: Scottie S1/S2/DX mode decoder
    martin_decoder: Martin M1/M2 mode decoder
    robot_decoder: Robot 36/72 mode decoder
    image_saver: Auto-save functionality for decoded images
"""

__all__ = [
    "DecodeProgress",
    "GoertzelFilter",
    "ImageSaveError",
    "ImageSaver",
    "MartinM1Config",
    "MartinM1Decoder",
    "ModeTimingEstimate",
    "Robot36Config",
    "Robot36Decoder",
    "SSTVMode",
    "ScanlineData",
    "ScottieS1Config",
    "ScottieS1Decoder",
    "SyncPulseDetector",
    "SyncPulseResult",
    "VISDetectionResult",
    "VISDetector",
]


def __getattr__(name: str):
    """Lazy import for decode module components."""
    if name in ("VISDetector", "VISDetectionResult", "SSTVMode", "GoertzelFilter"):
        from sstv_core.decode.vis_detector import (
            GoertzelFilter,
            SSTVMode,
            VISDetectionResult,
            VISDetector,
        )
        mapping = {
            "VISDetector": VISDetector,
            "VISDetectionResult": VISDetectionResult,
            "SSTVMode": SSTVMode,
            "GoertzelFilter": GoertzelFilter,
        }
        return mapping[name]
    elif name in ("SyncPulseDetector", "SyncPulseResult", "ModeTimingEstimate"):
        from sstv_core.decode.sync_detector import (
            ModeTimingEstimate,
            SyncPulseDetector,
            SyncPulseResult,
        )
        mapping = {
            "SyncPulseDetector": SyncPulseDetector,
            "SyncPulseResult": SyncPulseResult,
            "ModeTimingEstimate": ModeTimingEstimate,
        }
        return mapping[name]
    elif name in ("ScottieS1Decoder", "ScottieS1Config", "ScanlineData", "DecodeProgress"):
        from sstv_core.decode.scottie_decoder import (
            DecodeProgress,
            ScanlineData,
            ScottieS1Config,
            ScottieS1Decoder,
        )
        mapping = {
            "ScottieS1Decoder": ScottieS1Decoder,
            "ScottieS1Config": ScottieS1Config,
            "ScanlineData": ScanlineData,
            "DecodeProgress": DecodeProgress,
        }
        return mapping[name]
    elif name in ("MartinM1Decoder", "MartinM1Config"):
        from sstv_core.decode.martin_decoder import MartinM1Config, MartinM1Decoder
        return MartinM1Decoder if name == "MartinM1Decoder" else MartinM1Config
    elif name in ("Robot36Decoder", "Robot36Config"):
        from sstv_core.decode.robot_decoder import Robot36Config, Robot36Decoder
        return Robot36Decoder if name == "Robot36Decoder" else Robot36Config
    elif name in ("ImageSaver", "ImageSaveError"):
        from sstv_core.decode.image_saver import ImageSaveError, ImageSaver
        return ImageSaver if name == "ImageSaver" else ImageSaveError
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
