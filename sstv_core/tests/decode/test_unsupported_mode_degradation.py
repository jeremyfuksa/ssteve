"""VIS-recognized modes without a decoder must degrade, not hard-fail.

The correlation VIS detector identifies 11 modes; only three have decoders.
Until 2026-08-08 the other eight raised ValueError("Unsupported mode:
SSTVMode.ROBOT_72") -- the enum repr, in an ERROR-state session, with no
suggested_action and nothing to distinguish it from a genuine decode break.
Robot 72 and PD120 are both common on the air, so this was the edge case a
beta operator was most likely to hit.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import numpy as np
import pytest

from sstv_core.audio.ring_buffer import AudioRingBuffer
from sstv_core.decode.rx_manager import RXManager, RXState
from sstv_core.encode.vis_generator import SSTVMode, VISGenerator

SAMPLE_RATE = 48000


def _fake_stream(buffer: AudioRingBuffer):
    class FakeStream:
        def start_input(self, device_index=None):
            pass

        def stop_input(self):
            pass

        def get_input_buffer(self):
            return buffer

        def get_input_levels(self):
            return SimpleNamespace(rms=0.3, peak=0.5, is_clipping=False)

    return FakeStream()


async def _receive_transmission(audio: np.ndarray, tmp_path):
    """Feed `audio` through a real RXManager as a live device would."""
    buffer = AudioRingBuffer(max_samples=SAMPLE_RATE * 20)
    progress: list = []

    rx = RXManager(
        stream_manager=_fake_stream(buffer),
        sample_rate=SAMPLE_RATE,
        save_directory=tmp_path,
    )
    rx.set_progress_callback(progress.append)

    async def feeder():
        offset = 0
        chunk = SAMPLE_RATE // 4
        while offset < len(audio):
            # Never run far ahead of the consumer: a big backlog would scroll
            # the VIS header out of the correlation window.
            if len(buffer) < SAMPLE_RATE // 2:
                buffer.add(audio[offset : offset + chunk])
                offset += chunk
            await asyncio.sleep(0.001)

    feed_task = asyncio.create_task(feeder())
    try:
        result = await asyncio.wait_for(
            rx.receive(timeout_sec=20.0, save_image=True), timeout=120
        )
    finally:
        feed_task.cancel()

    return rx, result, progress


class TestModeNaming:
    """Every VIS-detectable mode needs a public name, decoder or not."""

    def test_all_vis_detectable_modes_have_public_names(self):
        from sstv_core.decode.correlation_vis_detector import CorrelationVISDetector

        missing = [
            mode.name
            for mode in CorrelationVISDetector.SUPPORTED_MODES
            if mode.name not in RXManager.MODE_NAMES
        ]
        assert not missing, f"VIS can detect these but cannot name them: {missing}"

    def test_undecodable_mode_name_is_not_an_enum_repr(self):
        """_mode_name previously fell through to str(mode) for these."""
        name = RXManager._mode_name(SSTVMode.ROBOT_72)
        assert name == "Robot72"
        assert "SSTVMode" not in name

    def test_decodable_modes_are_a_subset_of_named_modes(self):
        assert set(RXManager.DECODABLE_MODES) <= set(RXManager.MODE_NAMES.values())


class TestGracefulDegradation:
    @pytest.mark.asyncio
    async def test_robot72_stops_cleanly_instead_of_erroring(self, tmp_path):
        """A real Robot 72 header must end the session STOPPED, not ERROR."""
        vis = VISGenerator(sample_rate=SAMPLE_RATE).generate(SSTVMode.ROBOT_72)
        # Enough trailing signal that the manager reaches decoder selection.
        tail = np.zeros(SAMPLE_RATE * 2, dtype=np.float32)
        audio = np.concatenate([vis, tail]).astype(np.float32)

        rx, result, progress = await _receive_transmission(audio, tmp_path)

        assert result is None, "nothing decodable should have been produced"
        assert rx.get_unsupported_mode() == "Robot72"
        assert rx._state != RXState.ERROR, (
            "a known-but-undecodable mode is a clean stop, not a failure"
        )

        messages = [p.message for p in progress]
        assert any("Robot72" in m for m in messages), messages
        assert not any("SSTVMode." in m for m in messages), (
            f"enum repr leaked to the operator: {messages}"
        )
        # SSTeVe error voice: first person, contractions, names the limit.
        final = messages[-1]
        assert "I heard" in final and "can't decode it yet" in final, final
        assert "ScottieS1" in final, "message should name what I can decode"

    @pytest.mark.asyncio
    async def test_supported_mode_is_unaffected(self, tmp_path):
        """The degradation path must not fire for a decodable mode."""
        from sstv_core.encode.robot_encoder import Robot36Encoder

        x = np.linspace(0, 255, 320)
        img = np.zeros((240, 320, 3), dtype=np.uint8)
        img[:, :] = x[None, :, None]
        audio = Robot36Encoder().encode_image(img, include_vis=True)

        rx, result, _ = await _receive_transmission(audio, tmp_path)

        assert result is not None, "Robot36 should still decode"
        assert rx.get_unsupported_mode() is None
