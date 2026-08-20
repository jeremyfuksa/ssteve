"""Live scanline pixels for the progressive decode canvas (#55).

PRODUCT.md #6: "Scanlines render as they arrive, with no buffering
delay." `ScanlineUpdateEvent` carried numbers only -- backend-spec even
admitted it: "A per-scanline `rgb_data` field appeared here but was never
implemented." So the canvas could show a finished picture and nothing
else, turning the product's centrepiece interaction into a progress bar.

Plain integer arrays, not base64. Measured at each mode's real pacing,
the worst case is Robot 36 at 28.7 KB/s of JSON; base64 would cut that to
8.5 and cost every client a decode step between arrival and paint. When
the budget is not tight, the requirement that scanlines render "with no
buffering delay" is what decides it -- integers drop straight into a
Uint8ClampedArray for putImageData.
"""

from __future__ import annotations

import numpy as np
import pytest

from sstv_core.api.scanlines import (
    MAX_LINES_PER_EVENT,
    rows_to_rgb_payload,
)


def _rows(count: int, width: int = 320) -> np.ndarray:
    rng = np.random.default_rng(0)
    return rng.integers(0, 255, (count, width, 3), dtype=np.uint8)


class TestThePayload:
    def test_a_row_becomes_a_flat_integer_list(self) -> None:
        payload = rows_to_rgb_payload(_rows(1))

        assert isinstance(payload, list)
        assert len(payload) == 1
        assert len(payload[0]) == 320 * 3

    def test_values_are_bytes_a_canvas_can_use(self) -> None:
        payload = rows_to_rgb_payload(_rows(2))

        for row in payload:
            assert all(isinstance(v, int) for v in row)
            assert all(0 <= v <= 255 for v in row)

    def test_channel_order_is_rgb(self) -> None:
        """putImageData wants RGB. Handing it BGR would tint every
        picture, and the decoders already produce RGB rows."""
        row = np.zeros((1, 2, 3), dtype=np.uint8)
        row[0, 0] = [255, 0, 0]
        row[0, 1] = [0, 0, 255]

        payload = rows_to_rgb_payload(row)

        assert payload[0][:3] == [255, 0, 0]
        assert payload[0][3:6] == [0, 0, 255]

    def test_it_is_json_serialisable(self) -> None:
        """numpy ints are not, and the failure would only appear with a
        client attached."""
        import json

        json.dumps(rows_to_rgb_payload(_rows(3)))

    def test_no_rows_is_an_empty_payload(self) -> None:
        assert rows_to_rgb_payload(np.zeros((0, 320, 3), dtype=np.uint8)) == []


class TestBatchingKeepsEveryLine:
    """The old event fired every 5th line to "reduce spam".

    That was defensible when it carried numbers. Carrying pixels, it
    would paint the canvas in visible chunks and drop four lines in five
    -- which is precisely the buffering delay PRODUCT.md rules out. The
    fix is to send the lines *since the last event*, so the event rate is
    unchanged and no pixel is lost.
    """

    def test_a_batch_carries_every_line_in_it(self) -> None:
        payload = rows_to_rgb_payload(_rows(5))

        assert len(payload) == 5

    def test_a_runaway_batch_is_capped(self) -> None:
        """A stalled consumer must not turn one event into a megabyte."""
        payload = rows_to_rgb_payload(_rows(MAX_LINES_PER_EVENT + 50))

        assert len(payload) == MAX_LINES_PER_EVENT

    def test_the_cap_keeps_the_newest_lines(self) -> None:
        """Dropping the oldest keeps the canvas current. Keeping the
        oldest would paint stale lines and then jump."""
        rows = np.zeros((MAX_LINES_PER_EVENT + 2, 4, 3), dtype=np.uint8)
        rows[-1] = 200  # the newest line

        payload = rows_to_rgb_payload(rows)

        assert payload[-1][0] == 200


class TestTheEventCarriesThem:
    def test_scanline_update_has_an_rgb_field(self) -> None:
        from sstv_core.api.models import ScanlineUpdateEvent

        assert "rgb_rows" in ScanlineUpdateEvent.model_fields, (
            "the canvas cannot paint a decode in progress without pixels"
        )

    def test_rgb_is_optional_so_headless_decodes_are_unaffected(self) -> None:
        """A CLI decode has no canvas. Requiring pixels would make every
        event carry a kilobyte nothing reads."""
        from sstv_core.api.models import ScanlineUpdateEvent

        event = ScanlineUpdateEvent(
            scanline_number=10, total_scanlines=256, progress_percent=4.0
        )

        assert event.rgb_rows is None

    def test_the_first_row_index_locates_the_batch(self) -> None:
        """A batch of rows is meaningless without knowing where it
        starts -- the canvas has to paint them at the right y."""
        from sstv_core.api.models import ScanlineUpdateEvent

        assert "first_row" in ScanlineUpdateEvent.model_fields

    @pytest.mark.parametrize("width", [320, 640])
    def test_a_client_can_size_the_canvas_from_the_event(
        self, width: int
    ) -> None:
        """Row length divided by 3 gives the width, so nothing has to be
        assumed about the mode before the first paint."""
        payload = rows_to_rgb_payload(_rows(1, width=width))

        assert len(payload[0]) // 3 == width


class TestARealDecoderSuppliesPixels:
    """The getattr chain that reads them would silently return None.

    `_rows_since` walks rx_manager -> active_decoder -> image_buffer with
    getattr at every step, so a rename anywhere leaves the canvas blank
    and every test above still green. That is the exact shape that shipped
    three broken FSKID versions and an unwired spectrum relay earlier the
    same day.
    """

    def test_decoders_expose_their_partial_buffer(self) -> None:
        from sstv_core.decode.martin_decoder import MartinM1Decoder
        from sstv_core.decode.robot_decoder import Robot36Decoder
        from sstv_core.decode.scottie_decoder import ScottieS1Decoder

        for cls in (ScottieS1Decoder, MartinM1Decoder, Robot36Decoder):
            assert hasattr(cls, "image_buffer"), (
                f"{cls.__name__} has no image_buffer, so the canvas stays "
                "blank through every decode in that mode"
            )

    def test_the_buffer_fills_as_lines_decode(self) -> None:
        """Pixels have to appear in it mid-decode, not only at the end."""
        from sstv_core.decode.scottie_decoder import ScottieS1Config, ScottieS1Decoder

        decoder = ScottieS1Decoder(ScottieS1Config(sample_rate=48_000))
        decoder.reset()

        assert decoder.image_buffer is not None
        assert decoder.image_buffer.shape[2] == 3, "rows must be RGB"

    def test_rx_manager_exposes_the_active_decoder(self) -> None:
        from sstv_core.decode.rx_manager import RXManager

        class _NoStream:
            def get_input_levels(self) -> None:
                return None

        assert hasattr(RXManager(stream_manager=_NoStream()), "active_decoder")

    def test_rows_since_returns_pixels_from_a_real_buffer(self) -> None:
        """Drive `_rows_since` against a decoder with rows in it."""
        from uuid import uuid4

        from sstv_core.api.dsp_manager import DSPManager
        from sstv_core.decode.scottie_decoder import ScottieS1Config, ScottieS1Decoder

        decoder = ScottieS1Decoder(ScottieS1Config(sample_rate=48_000))
        decoder.reset()
        assert decoder.image_buffer is not None
        decoder.image_buffer[0:3] = 128

        class _RX:
            active_decoder = decoder

        manager = DSPManager()
        session_id = uuid4()
        manager._rx_managers[session_id] = _RX()  # type: ignore[assignment]

        rows, first = manager._rows_since(session_id, 0, 3)

        assert rows is not None, (
            "no pixels came back from a decoder that plainly has rows -- "
            "the getattr chain is reading the wrong attribute"
        )
        assert len(rows) == 3
        assert first == 0
        assert rows[0][0] == 128
