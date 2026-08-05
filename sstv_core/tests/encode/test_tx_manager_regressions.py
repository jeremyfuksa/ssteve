"""Regression tests for transmit mode selection and complete audio playback."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest

from sstv_core.audio.ptt_controller import PTTMethod
from sstv_core.encode.image_preprocessor import ImagePreprocessor
from sstv_core.encode.tx_manager import TXManager
from sstv_core.encode.vis_generator import SSTVMode, VISGenerator


class CallbackStream:
    """Consume callback audio synchronously like a small output device."""

    def __init__(self) -> None:
        self.blocks: list[np.ndarray] = []

    def start_output(self, device_index=None, callback=None) -> None:
        assert callback is not None
        for _ in range(8):
            self.blocks.append(callback(128))

    def stop_output(self) -> None:
        return None


@pytest.mark.asyncio
async def test_transmit_streams_the_complete_waveform(monkeypatch) -> None:
    """Playback must start at VIS and continue through the final image sample."""
    stream = CallbackStream()
    ptt = SimpleNamespace(
        method=PTTMethod.NONE,
        key_radio=AsyncMock(),
        unkey_radio=AsyncMock(),
        is_keyed=False,
    )
    manager = TXManager(stream_manager=stream, ptt_controller=ptt)

    encoder = SimpleNamespace(
        config=SimpleNamespace(width=2, height=2),
        encode_image=lambda image: np.arange(600, dtype=np.float32),
    )
    monkeypatch.setattr(manager, "_get_encoder", lambda mode: encoder)
    monkeypatch.setattr(
        ImagePreprocessor,
        "process",
        lambda self, source: SimpleNamespace(
            image=np.zeros((2, 2, 3), dtype=np.uint8),
            final_size=(2, 2),
        ),
    )
    monkeypatch.setattr(
        VISGenerator,
        "generate",
        lambda self, mode: np.full(200, -1.0, dtype=np.float32),
    )

    assert await manager.transmit("unused.png", SSTVMode.SCOTTIE_S1)

    played = np.concatenate(stream.blocks)
    expected = np.concatenate(
        (np.full(200, -1.0, dtype=np.float32), np.arange(600, dtype=np.float32))
    )
    np.testing.assert_array_equal(played[: len(expected)], expected)


def test_only_implemented_modes_select_encoders() -> None:
    manager = TXManager(stream_manager=SimpleNamespace())

    assert manager._get_encoder(SSTVMode.SCOTTIE_S1).__class__.__name__ == "ScottieS1Encoder"
    assert manager._get_encoder(SSTVMode.MARTIN_M1).__class__.__name__ == "MartinM1Encoder"
    assert manager._get_encoder(SSTVMode.ROBOT_36).__class__.__name__ == "Robot36Encoder"

    with pytest.raises(ValueError, match="Unsupported transmit mode"):
        manager._get_encoder(SSTVMode.PD_120)
