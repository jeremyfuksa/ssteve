"""Martin M2 timing.

M2 was missing until 2026-08-17: two real transmissions in a 20m capture were
identified as MARTIN_M2 by the VIS detector and then skipped, because the CLI
had no config for the mode. Like Scottie S2, the whole difference from M1 is
the colour scan duration, so these tests guard the arithmetic that produces
the line time rather than any new decoding logic.
"""

from __future__ import annotations

from sstv_core.decode.martin_decoder import MartinM1Config, MartinM2Config

# Published Martin M2 figures.
SPEC_COLOR_SCAN_MS = 73.216
SPEC_LINE_MS = 226.798
SPEC_VIS_CODE = 40

RATE = 48000


class TestMartinM2Timing:
    """The scan duration and the line time it produces must match the spec."""

    def test_color_scan_duration_matches_spec(self) -> None:
        assert abs(MartinM2Config().color_scan_duration_ms - SPEC_COLOR_SCAN_MS) < 0.01

    def test_total_line_time_matches_spec(self) -> None:
        """Line time is derived from its parts, so this catches a bad part.

        1 sync + 4 separators + 3 colour scans must sum to the published
        226.798 ms. A wrong component drifts the sum and slants every
        decoded image.
        """
        cfg = MartinM2Config(sample_rate=RATE)
        line_ms = 1000.0 * cfg.total_line_samples / RATE
        assert abs(line_ms - SPEC_LINE_MS) < 0.1, (
            f"line time {line_ms:.3f}ms, spec is {SPEC_LINE_MS}ms"
        )

    def test_m2_colour_scan_is_about_half_of_m1(self) -> None:
        """The one real difference between the modes.

        Not exactly half as written: each mode carries its own published
        figure, and M1's 146.43 is itself rounded, so half of it is 73.215
        against M2's 73.216. Both are the spec values -- the tolerance is
        for the rounding, not for drift.
        """
        assert abs(
            MartinM2Config().color_scan_duration_ms
            - MartinM1Config().color_scan_duration_ms / 2
        ) < 0.01

    def test_m2_is_faster_than_m1(self) -> None:
        """Guards against M2 being a copy of M1 that was never edited."""
        assert (
            MartinM2Config(sample_rate=RATE).total_line_samples
            < MartinM1Config(sample_rate=RATE).total_line_samples
        )

    def test_frame_time_is_about_58_seconds(self) -> None:
        """Sanity against the published ~58s frame, and against the air.

        The two off-air M2 transmissions measured 58.0s between VIS header
        and the FSKID that follows the picture.
        """
        cfg = MartinM2Config(sample_rate=RATE)
        frame_sec = cfg.total_line_samples * cfg.height / RATE
        assert 57.0 < frame_sec < 59.0, f"frame is {frame_sec:.1f}s"

    def test_geometry_matches_m1(self) -> None:
        """M2 differs from M1 in timing only, not in image size."""
        assert MartinM2Config().width == MartinM1Config().width
        assert MartinM2Config().height == MartinM1Config().height
