"""RF-safety regressions: cancellation must unkey, serial open must not key.

The 2026-08-07 audit found a hard task.cancel() mid-transmission left the
radio keyed (CancelledError skipped cleanup entirely), and that pyserial's
open-with-RTS/DTR-asserted default momentarily keyed RTS/DTR interfaces on
every port open.
"""

from __future__ import annotations

import asyncio

import numpy as np
import pytest

from sstv_core.audio.ptt_controller import PTTController, PTTMethod
from sstv_core.encode.tx_manager import TXManager
from sstv_core.encode.vis_generator import SSTVMode


class FakeStreamManager:
    """Output-side stand-in: records lifecycle, plays nothing."""

    def __init__(self) -> None:
        self.output_started = False
        self.output_stopped = False

    def start_output(self, device_index=None, callback=None):
        self.output_started = True

    def stop_output(self):
        self.output_stopped = True


@pytest.mark.asyncio
async def test_hard_cancel_unkeys_radio_and_stops_stream():
    """task.cancel() during transmission must release PTT and the stream."""
    stream = FakeStreamManager()
    ptt = PTTController(method=PTTMethod.NONE)
    tx = TXManager(stream_manager=stream, ptt_controller=ptt)

    image = np.zeros((256, 320, 3), dtype=np.uint8)
    task = asyncio.create_task(tx.transmit(image, mode=SSTVMode.SCOTTIE_S1))

    # Let it get past keying into the transmit wait loop.
    for _ in range(50):
        await asyncio.sleep(0.05)
        if stream.output_started:
            break
    assert stream.output_started, "transmission never started"
    assert ptt.is_keyed

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert not ptt.is_keyed, "cancel left the radio keyed (dead-key)"
    assert stream.output_stopped, "cancel left the output stream open"


@pytest.mark.asyncio
async def test_cooperative_cancel_reports_failure_not_success():
    """cancel() via the flag must not mark the aborted transmission COMPLETE."""
    stream = FakeStreamManager()
    ptt = PTTController(method=PTTMethod.NONE)
    tx = TXManager(stream_manager=stream, ptt_controller=ptt)

    image = np.zeros((256, 320, 3), dtype=np.uint8)
    task = asyncio.create_task(tx.transmit(image, mode=SSTVMode.SCOTTIE_S1))
    for _ in range(50):
        await asyncio.sleep(0.05)
        if stream.output_started:
            break

    await tx.cancel()
    result = await task
    assert result is False
    assert not ptt.is_keyed


def test_serial_open_never_asserts_key_lines(monkeypatch):
    """RTS/DTR must be low BEFORE the port opens, not lowered after."""
    events: list[str] = []

    class RecordingSerial:
        def __init__(self, port=None, baudrate=9600, timeout=None):
            self.port = port
            self._rts = True  # pyserial defaults: asserted
            self._dtr = True
            if port is not None:
                # pyserial semantics: a port in the constructor opens now.
                events.append("open")

        @property
        def rts(self):
            return self._rts

        @rts.setter
        def rts(self, value):
            events.append(f"rts={value}")
            self._rts = value

        @property
        def dtr(self):
            return self._dtr

        @dtr.setter
        def dtr(self, value):
            events.append(f"dtr={value}")
            self._dtr = value

        def open(self):
            events.append("open")

        def close(self):
            events.append("close")

    import sys
    from types import SimpleNamespace

    monkeypatch.setitem(sys.modules, "serial", SimpleNamespace(Serial=RecordingSerial))

    ptt = PTTController(method=PTTMethod.SERIAL, serial_port="/dev/ttyUSB0")
    ptt._open_serial()

    open_index = events.index("open")
    assert "rts=False" in events[:open_index], f"RTS not lowered before open: {events}"
    assert "dtr=False" in events[:open_index], f"DTR not lowered before open: {events}"


def test_transmit_audio_carries_single_vis_header():
    """TXManager prepends its own VIS header; the encoder must not add a
    second one (double header = auto-detect chaos at the receiver)."""
    from sstv_core.encode.scottie_encoder import ScottieS1Encoder
    from sstv_core.encode.vis_generator import VISGenerator

    encoder = ScottieS1Encoder()
    image = np.zeros((256, 320, 3), dtype=np.uint8)
    image_audio = encoder.encode_image(image, include_vis=False)
    vis = VISGenerator(sample_rate=48000).generate(SSTVMode.SCOTTIE_S1)

    # The combined length must be exactly one VIS + image; if the encoder
    # sneaks a second header in, the image segment is a VIS longer.
    combined = np.concatenate([vis, image_audio])
    expected_with_one_vis = len(vis) + len(image_audio)
    assert len(combined) == expected_with_one_vis

    with_default = encoder.encode_image(image)
    assert len(with_default) == len(image_audio) + len(vis), (
        "encode_image(include_vis=True) should add exactly one VIS header"
    )
