"""CLI live-device decode: really wired to the RX pipeline.

Two layers: the CLI glue (device resolution, event logging, --output move,
exit codes) against a stubbed RXManager, and the full pipeline against a
fake stream manager that feeds a real Robot36 transmission through the
real ring buffer.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from sstv_core.audio.ring_buffer import AudioRingBuffer
from sstv_core.cli.main import main

SAMPLE_RATE = 48000


class TestCLIGlue:
    def _run(self, monkeypatch, tmp_path, receive_result):
        import sstv_core.decode.rx_manager as rx_module

        class StubRX:
            def __init__(self, *args, **kwargs):
                pass

            def set_progress_callback(self, cb):
                pass

            async def receive(self, **kwargs):
                return receive_result

        monkeypatch.setattr(rx_module, "RXManager", StubRX)

        import sstv_core.audio.device_manager as dm

        class StubDeviceManager:
            def __init__(self, *a, **k):
                pass

            def list_all_devices(self):
                return [
                    SimpleNamespace(
                        id="ca_Test", name="Test", is_default=True, is_input=True
                    )
                ]

            def get_device_index(self, device_id):
                return 0

        monkeypatch.setattr(dm, "AudioDeviceManager", StubDeviceManager)

        out = tmp_path / "live.png"
        rc = main(
            ["decode", "--device", "ca_Test", "--timeout", "5",
             "--output", str(out)]
        )
        return rc, out

    def test_successful_decode_moves_image_to_output(self, monkeypatch, tmp_path):
        saved = tmp_path / "saved" / "rx.png"
        saved.parent.mkdir()
        saved.write_bytes(b"png")
        rc, out = self._run(monkeypatch, tmp_path, saved)
        assert rc == 0
        assert out.exists()

    def test_timeout_is_exit_2_not_fake_success(self, monkeypatch, tmp_path):
        rc, out = self._run(monkeypatch, tmp_path, None)
        assert rc == 2
        assert not out.exists()


class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_live_decode_of_fed_robot36_stream(self, tmp_path):
        """A real RXManager decodes a real Robot36 transmission arriving
        through the real ring buffer, as a live device would deliver it."""
        from sstv_core.decode.rx_manager import RXManager
        from sstv_core.encode.robot_encoder import Robot36Encoder

        encoder = Robot36Encoder()
        x = np.linspace(0, 255, 320)
        img = np.zeros((240, 320, 3), dtype=np.uint8)
        img[:, :] = x[None, :, None]
        audio = encoder.encode_image(img, include_vis=True)

        buffer = AudioRingBuffer(max_samples=SAMPLE_RATE * 10)

        class FakeStream:
            def start_input(self, device_index=None):
                pass

            def stop_input(self):
                pass

            def get_input_buffer(self):
                return buffer

            def get_input_levels(self):
                return SimpleNamespace(rms=0.3, peak=0.5, is_clipping=False)

        async def feeder():
            offset = 0
            chunk = SAMPLE_RATE // 4
            while offset < len(audio):
                # Faster than real time, but never far ahead of the
                # consumer: big backlogs would scroll the VIS header out of
                # the correlation window, which paced live audio never does.
                if len(buffer) < SAMPLE_RATE // 2:
                    buffer.add(audio[offset : offset + chunk])
                    offset += chunk
                await asyncio.sleep(0.001)

        rx = RXManager(
            stream_manager=FakeStream(),
            sample_rate=SAMPLE_RATE,
            save_directory=tmp_path,
        )
        feed_task = asyncio.create_task(feeder())
        try:
            result = await asyncio.wait_for(
                rx.receive(timeout_sec=30.0, save_image=True), timeout=120
            )
        finally:
            feed_task.cancel()

        assert result is not None, "live pipeline decoded nothing"
        assert Path(result).exists()

        import cv2

        decoded = cv2.cvtColor(cv2.imread(str(result)), cv2.COLOR_BGR2RGB)
        o = img[10:-10, 10:-10].astype(float)
        d = decoded[10:-10, 10:-10].astype(float)
        corr = float(np.corrcoef(o.ravel(), d.ravel())[0, 1])
        assert corr >= 0.9, f"decoded correlation {corr:.3f}"
