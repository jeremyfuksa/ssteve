"""SSTV encoding module for SSTeVe core engine.

Provides image preprocessing, VIS code generation, and mode-specific encoders.

Modules:
    image_preprocessor: Image resizing and color space conversion
    vis_generator: VIS code audio generation
    scottie_encoder: Scottie S1/S2/DX mode encoder
    martin_encoder: Martin M1/M2 mode encoder
    robot_encoder: Robot 36/72 mode encoder
    audio_transmitter: Audio stream output handling
    tx_manager: Complete transmission pipeline with PTT
"""

__all__ = [
    "AudioTransmitter",
    "ColorSpace",
    "EncoderProgress",
    "ImagePreprocessor",
    "MartinM1Encoder",
    "MartinM1EncoderConfig",
    "ModeResolution",
    "PreprocessResult",
    "ResizeMode",
    "Robot36Encoder",
    "Robot36EncoderConfig",
    "SSTVMode",
    "ScottieS1Encoder",
    "ScottieS1EncoderConfig",
    "TXManager",
    "TXProgress",
    "TXState",
    "TransmitProgress",
    "VISConfig",
    "VISGenerator",
]


def __getattr__(name: str):
    if name in (
        "ImagePreprocessor", "ModeResolution", "ResizeMode", "ColorSpace", "PreprocessResult"
    ):
        from sstv_core.encode.image_preprocessor import (
            ColorSpace,
            ImagePreprocessor,
            ModeResolution,
            PreprocessResult,
            ResizeMode,
        )
        mapping = {
            "ImagePreprocessor": ImagePreprocessor,
            "ModeResolution": ModeResolution,
            "ResizeMode": ResizeMode,
            "ColorSpace": ColorSpace,
            "PreprocessResult": PreprocessResult,
        }
        return mapping[name]
    elif name in ("VISGenerator", "VISConfig", "SSTVMode"):
        from sstv_core.encode.vis_generator import SSTVMode, VISConfig, VISGenerator
        mapping = {"VISGenerator": VISGenerator, "VISConfig": VISConfig, "SSTVMode": SSTVMode}
        return mapping[name]
    elif name in ("ScottieS1Encoder", "ScottieS1EncoderConfig", "EncoderProgress"):
        from sstv_core.encode.scottie_encoder import (
            EncoderProgress,
            ScottieS1Encoder,
            ScottieS1EncoderConfig,
        )
        mapping = {
            "ScottieS1Encoder": ScottieS1Encoder,
            "ScottieS1EncoderConfig": ScottieS1EncoderConfig,
            "EncoderProgress": EncoderProgress,
        }
        return mapping[name]
    elif name in ("MartinM1Encoder", "MartinM1EncoderConfig"):
        from sstv_core.encode.martin_encoder import MartinM1Encoder, MartinM1EncoderConfig
        return MartinM1Encoder if name == "MartinM1Encoder" else MartinM1EncoderConfig
    elif name in ("Robot36Encoder", "Robot36EncoderConfig"):
        from sstv_core.encode.robot_encoder import Robot36Encoder, Robot36EncoderConfig
        return Robot36Encoder if name == "Robot36Encoder" else Robot36EncoderConfig
    elif name in ("AudioTransmitter", "TransmitProgress"):
        from sstv_core.encode.audio_transmitter import AudioTransmitter, TransmitProgress
        return AudioTransmitter if name == "AudioTransmitter" else TransmitProgress
    elif name in ("TXManager", "TXState", "TXProgress"):
        from sstv_core.encode.tx_manager import TXManager, TXProgress, TXState
        mapping = {"TXManager": TXManager, "TXState": TXState, "TXProgress": TXProgress}
        return mapping[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
