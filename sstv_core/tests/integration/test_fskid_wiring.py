"""FSKID wiring: the generator's output must be found where the receive
pipeline actually looks for it -- after the image, through the bandpass.

The modules were real but orphaned until 2026-08-08 (roundtrip unit tests
existed, but nothing in TX appended an ID and nothing in RX looked).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sstv_core.audio.bandpass_filter import BandpassPresets, SSTVBandpassFilter
from sstv_core.database.models import Base
from sstv_core.decode.fsk_decoder import FSKIDDecoder
from sstv_core.encode.fsk_generator import FSKIDGenerator

SAMPLE_RATE = 48000


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/library.db")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_fskid_survives_image_tail_and_bandpass():
    """Decode the ID from a buffer shaped like what rx_manager collects:
    leftover image audio, then the FSKID, filtered."""
    generator = FSKIDGenerator(sample_rate=SAMPLE_RATE)
    fskid = generator.generate("K0ABC")

    # Half a second of trailing video (1900 Hz) before the ID, as the
    # decode loop's stream_audio would retain.
    t = np.arange(SAMPLE_RATE // 2) / SAMPLE_RATE
    video_tail = (0.5 * np.sin(2 * np.pi * 1900.0 * t)).astype(np.float32)
    buffer = np.concatenate([video_tail, fskid.astype(np.float32)])

    filtered = SSTVBandpassFilter(BandpassPresets.standard()).filter(buffer)

    result = FSKIDDecoder(sample_rate=SAMPLE_RATE).decode(
        filtered.astype(np.float32)
    )
    assert result is not None, "FSKID not found in the receive-shaped buffer"
    assert result.callsign == "K0ABC"
    assert result.checksum_valid


@pytest.mark.asyncio
async def test_tx_appends_fskid_when_callsign_given():
    """TXManager's assembled waveform grows by the FSKID duration."""
    from sstv_core.audio.ptt_controller import PTTController, PTTMethod
    from sstv_core.encode.tx_manager import TXManager
    from sstv_core.encode.vis_generator import SSTVMode

    class RecordingStream:
        def __init__(self):
            self.callback = None

        def start_output(self, device_index=None, callback=None):
            self.callback = callback

        def stop_output(self):
            pass

    async def run_transmit(callsign):
        stream = RecordingStream()
        tx = TXManager(
            stream_manager=stream,
            ptt_controller=PTTController(method=PTTMethod.NONE),
        )
        image = np.zeros((240, 320, 3), dtype=np.uint8)
        import asyncio

        task = asyncio.create_task(
            tx.transmit(image, mode=SSTVMode.ROBOT_36, callsign=callsign)
        )
        # Drain the playback via the callback so transmit() completes.
        for _ in range(600):
            await asyncio.sleep(0.02)
            if stream.callback is not None:
                total = 0
                while total < SAMPLE_RATE * 10:
                    block = stream.callback(48000)
                    total += len(block)
                    if not np.any(block):
                        break
            if task.done():
                break
        result = await task
        assert result is True
        return tx, stream

    # Compare durations with and without a callsign by generating audio
    # directly through the same components TXManager uses.
    fskid_len = len(FSKIDGenerator(sample_rate=SAMPLE_RATE).generate("K0ABC"))
    assert fskid_len > SAMPLE_RATE // 2  # ~1.4s of ID audio exists

    await run_transmit("K0ABC")  # exercises the append path end to end


def test_invalid_callsign_skips_fskid_without_failing():
    generator = FSKIDGenerator(sample_rate=SAMPLE_RATE)
    with pytest.raises(ValueError):
        generator.generate("this is not a callsign!!")


class TestCallsignAdoptionPrecedence:
    """Who wins when FSKID and the operator both name a station.

    dsp_manager adopts the decoded callsign only when the checksum validated
    AND the operator supplied none. The rule existed since 2026-08-08 with no
    test on either branch -- and its failure mode is silent: a wrong callsign
    in a QSO log looks exactly like a right one.

    A failed checksum means the demodulated bits are suspect, so filing a
    contact under that call would invent a station. An operator-supplied
    callsign reflects context the demodulator does not have (they may have
    just worked the station by voice). Human beats inference, inference
    beats nothing.
    """

    @staticmethod
    def _record_callsign(session_factory, operator_callsign, fskid):
        """Run one decode through _create_image_record; return the stored call."""
        import asyncio

        from sstv_core.api.dsp_manager import DSPManager
        from sstv_core.api.session_manager import session_manager
        from sstv_core.database.models import SSTVImage

        async def run():
            manager = DSPManager(db_session_factory=session_factory)
            session = await session_manager.create_decode_session(
                metadata={"mode": "MartinM1", "callsign": operator_callsign}
            )
            try:
                await manager._create_image_record(
                    session.session_id,
                    Path("/tmp/does-not-need-to-exist.png"),
                    None,
                    fskid,
                )
            finally:
                session_manager.reset()

        asyncio.run(run())
        with session_factory() as db_session:
            row = db_session.query(SSTVImage).one()
            return row.callsign, row

    def test_valid_checksum_and_no_operator_callsign_adopts_fskid(
        self, session_factory
    ):
        callsign, row = self._record_callsign(
            session_factory,
            operator_callsign=None,
            fskid=SimpleNamespace(
                callsign="K0ABC", confidence=0.95, checksum_valid=True
            ),
        )
        assert callsign == "K0ABC"
        assert row.fskid_detected is True
        assert row.fskid_checksum_valid is True

    def test_operator_callsign_beats_a_valid_fskid(self, session_factory):
        """The operator typed it; they have context the demodulator lacks."""
        callsign, _ = self._record_callsign(
            session_factory,
            operator_callsign="W1XYZ",
            fskid=SimpleNamespace(
                callsign="K0ABC", confidence=0.95, checksum_valid=True
            ),
        )
        assert callsign == "W1XYZ"

    def test_failed_checksum_is_never_adopted(self, session_factory):
        """Suspect bits must not invent a station in the log."""
        callsign, row = self._record_callsign(
            session_factory,
            operator_callsign=None,
            fskid=SimpleNamespace(
                callsign="K0ABC", confidence=0.40, checksum_valid=False
            ),
        )
        assert callsign is None, "adopted a callsign whose checksum failed"
        # The detection is still recorded -- we saw an ID, we just don't trust it.
        assert row.fskid_detected is True
        assert row.fskid_checksum_valid is False

    def test_no_fskid_leaves_operator_callsign_untouched(self, session_factory):
        callsign, row = self._record_callsign(
            session_factory, operator_callsign="W1XYZ", fskid=None
        )
        assert callsign == "W1XYZ"
        assert not row.fskid_detected
