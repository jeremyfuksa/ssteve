"""SSTV encoding module for SSTeVe core engine.

Provides image preprocessing, VIS code generation, and mode-specific encoders.

Modules:
    image_preprocessor: Image resizing and color space conversion
    vis_generator: VIS code audio generation
    scottie_encoder: Scottie S1/S2/DX mode encoder
    audio_transmitter: Audio stream output handling
    tx_manager: Complete transmission pipeline with PTT
"""

__all__ = [
    "ImagePreprocessor",
    "ModeResolution",
    "ResizeMode",
    "ColorSpace",
    "PreprocessResult",
    "VISGenerator",
    "VISConfig",
    "SSTVMode",
    "ScottieS1Encoder",
    "ScottieS1EncoderConfig",
    "EncoderProgress",
    "AudioTransmitter",
    "TransmitProgress",
    "TXManager",
    "TXState",
    "TXProgress",
]


def __getattr__(name: str):
    if name in ("ImagePreprocessor", "ModeResolution", "ResizeMode", "ColorSpace", "PreprocessResult"):
        from sstv_core.encode.image_preprocessor import (
            ImagePreprocessor, ModeResolution, ResizeMode, ColorSpace, PreprocessResult
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
        from sstv_core.encode.vis_generator import VISGenerator, VISConfig, SSTVMode
        mapping = {"VISGenerator": VISGenerator, "VISConfig": VISConfig, "SSTVMode": SSTVMode}
        return mapping[name]
    elif name in ("ScottieS1Encoder", "ScottieS1EncoderConfig", "EncoderProgress"):
        from sstv_core.encode.scottie_encoder import ScottieS1Encoder, ScottieS1EncoderConfig, EncoderProgress
        mapping = {
            "ScottieS1Encoder": ScottieS1Encoder,
            "ScottieS1EncoderConfig": ScottieS1EncoderConfig,
            "EncoderProgress": EncoderProgress,
        }
        return mapping[name]
    elif name in ("AudioTransmitter", "TransmitProgress"):
        from sstv_core.encode.audio_transmitter import AudioTransmitter, TransmitProgress
        return AudioTransmitter if name == "AudioTransmitter" else TransmitProgress
    elif name in ("TXManager", "TXState", "TXProgress"):
        from sstv_core.encode.tx_manager import TXManager, TXState, TXProgress
        mapping = {"TXManager": TXManager, "TXState": TXState, "TXProgress": TXProgress}
        return mapping[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
