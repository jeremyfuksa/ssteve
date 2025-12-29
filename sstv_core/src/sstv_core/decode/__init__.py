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
    "VISDetector",
    "VISDetectionResult",
    "SSTVMode",
    "SyncPulseDetector",
    "SyncPulseResult",
    "ModeTimingEstimate",
    "ScottieS1Decoder",
    "ScottieS1Config",
    "MartinM1Decoder",
    "MartinM1Config",
    "Robot36Decoder",
    "Robot36Config",
    "ScanlineData",
    "DecodeProgress",
    "ImageSaver",
    "ImageSaveError",
    "GoertzelFilter",
]


def __getattr__(name: str):
    """Lazy import for decode module components."""
    if name in ("VISDetector", "VISDetectionResult", "SSTVMode", "GoertzelFilter"):
        from sstv_core.decode.vis_detector import (
            VISDetector, VISDetectionResult, SSTVMode, GoertzelFilter
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
            SyncPulseDetector, SyncPulseResult, ModeTimingEstimate
        )
        mapping = {
            "SyncPulseDetector": SyncPulseDetector,
            "SyncPulseResult": SyncPulseResult,
            "ModeTimingEstimate": ModeTimingEstimate,
        }
        return mapping[name]
    elif name in ("ScottieS1Decoder", "ScottieS1Config", "ScanlineData", "DecodeProgress"):
        from sstv_core.decode.scottie_decoder import (
            ScottieS1Decoder, ScottieS1Config, ScanlineData, DecodeProgress
        )
        mapping = {
            "ScottieS1Decoder": ScottieS1Decoder,
            "ScottieS1Config": ScottieS1Config,
            "ScanlineData": ScanlineData,
            "DecodeProgress": DecodeProgress,
        }
        return mapping[name]
    elif name in ("MartinM1Decoder", "MartinM1Config"):
        from sstv_core.decode.martin_decoder import MartinM1Decoder, MartinM1Config
        return MartinM1Decoder if name == "MartinM1Decoder" else MartinM1Config
    elif name in ("Robot36Decoder", "Robot36Config"):
        from sstv_core.decode.robot_decoder import Robot36Decoder, Robot36Config
        return Robot36Decoder if name == "Robot36Decoder" else Robot36Config
    elif name in ("ImageSaver", "ImageSaveError"):
        from sstv_core.decode.image_saver import ImageSaver, ImageSaveError
        return ImageSaver if name == "ImageSaver" else ImageSaveError
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
