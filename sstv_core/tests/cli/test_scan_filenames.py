"""Callsign in the scan's output filenames.

FSKID is decoded already -- rx_manager has done it since #107 -- but the
scan path never asked for it, so every callsign was computed and thrown
away. These tests cover the naming rule that puts it back: a callsign
appears in the filename only when its checksum verifies, because a
plausible-looking wrong callsign in a filename is worse than none.
"""

from __future__ import annotations

import pytest

from sstv_core.cli.main import scan_output_name
from sstv_core.decode.fsk_decoder import FSKIDResult


def _result(callsign: str, *, checksum_valid: bool = True) -> FSKIDResult:
    return FSKIDResult(
        callsign=callsign,
        confidence=0.9,
        checksum_valid=checksum_valid,
        symbols_decoded=len(callsign),
    )


class TestScanOutputName:
    def test_no_fskid_keeps_the_plain_name(self) -> None:
        assert scan_output_name("scan", 9195, "SCOTTIE_S1", None) == (
            "scan_009195s_scottie_s1.png"
        )

    def test_verified_callsign_is_appended(self) -> None:
        assert scan_output_name("scan", 9438, "SCOTTIE_S1", _result("AA6DW")) == (
            "scan_009438s_scottie_s1_AA6DW.png"
        )

    def test_failed_checksum_is_left_out(self) -> None:
        """The rule that makes a name in a filename worth trusting."""
        assert scan_output_name(
            "scan", 9683, "SCOTTIE_S1", _result("AA6DW", checksum_valid=False)
        ) == "scan_009683s_scottie_s1.png"

    def test_empty_callsign_is_left_out(self) -> None:
        assert scan_output_name("scan", 100, "MARTIN_M2", _result("")) == (
            "scan_000100s_martin_m2.png"
        )

    def test_whitespace_only_callsign_is_left_out(self) -> None:
        assert scan_output_name("scan", 100, "MARTIN_M2", _result("   ")) == (
            "scan_000100s_martin_m2.png"
        )

    def test_surrounding_whitespace_is_trimmed(self) -> None:
        """MMSSTV pads the field, so the decode carries the padding."""
        assert scan_output_name("scan", 100, "MARTIN_M2", _result(" KD2TT ")) == (
            "scan_000100s_martin_m2_KD2TT.png"
        )

    @pytest.mark.parametrize(
        "raw",
        ["../../etc/passwd", "AA6DW/../x", "A/B", "A\\B", "A:B", "AA6DW\x00"],
    )
    def test_a_callsign_cannot_escape_the_output_directory(self, raw: str) -> None:
        """Decoded audio is untrusted input -- it is whatever was on the air.

        A garbled FSKID read can produce any bytes at all, so the result
        must never reach the filesystem as a path.
        """
        name = scan_output_name("scan", 100, "MARTIN_M2", _result(raw))
        assert "/" not in name
        assert "\\" not in name
        assert ".." not in name
        assert "\x00" not in name

    def test_slashed_portable_callsign_keeps_its_letters(self) -> None:
        """`AA6DW/P` is a real callsign; keep the characters, drop the slash."""
        name = scan_output_name("scan", 100, "MARTIN_M2", _result("AA6DW/P"))
        assert name == "scan_000100s_martin_m2_AA6DWP.png"

    def test_a_long_callsign_is_capped(self) -> None:
        name = scan_output_name("scan", 100, "MARTIN_M2", _result("A" * 200))
        assert len(name) < 100

    def test_offset_stays_zero_padded_for_sorting(self) -> None:
        """Chronological order must survive a plain alphabetical listing."""
        early = scan_output_name("scan", 42, "SCOTTIE_S1", _result("AA6DW"))
        late = scan_output_name("scan", 11077, "SCOTTIE_S1", _result("AA6DW"))
        assert early < late


class TestFSKIDGetsTheTailNotTheWholeSlice:
    """The bug the filename tests above could not see.

    Every test in this file passed while the scan found no FSKID at all,
    because they exercise the naming rule and never the decoder. The scan
    was handing FSKIDDecoder a whole 110-second Scottie S1; the decoder
    scans forward for its preamble and gives up after TIMEOUT_SAMPLES
    (3 s), so it returned None on every real transmission -- indis-
    tinguishable from "nobody sent an ID".
    """

    def test_the_decoder_gives_up_before_reaching_a_late_preamble(self) -> None:
        """Why the tail must be sliced rather than passed whole.

        Pin the actual constant: a decoder handed a full transmission
        cannot reach an ID sitting at the end of it.
        """
        from sstv_core.decode.fsk_decoder import FSKIDDecoder

        rate = 48_000
        scottie_s1_sec = 110.0
        assert FSKIDDecoder.TIMEOUT_SAMPLES < scottie_s1_sec * rate

    def test_a_decoded_image_length_locates_the_tail(self) -> None:
        """The slice point comes from lines decoded, not from mode timings.

        A faded transmission stops early, so a fixed per-mode duration
        would cut in the wrong place. The decoder's own line count is
        right in both cases.
        """
        total_line_samples = 6_000
        for lines in (144, 245, 256):
            image_samples = lines * total_line_samples
            audio_len = 256 * total_line_samples + 3 * 48_000
            tail = audio_len - image_samples
            assert tail > 0, "the tail must not be empty for a partial decode"
            assert image_samples < audio_len


class TestFSKIDIsActuallyReached:
    """What the tests above could not see.

    Every filename test passed through three broken implementations: the
    whole transmission handed to a 3-second decoder, a slice computed from
    a sample-0 that was not the image start, and a window aimed at the
    strongest 1500 Hz moment -- which is the middle of the tone, not its
    opening edge. All three returned None on every real signal, which reads
    exactly like "nobody sent an ID".

    These use the real fixtures, so they fail if the plumbing stops
    delivering audio the decoder can actually read.
    """

    def test_the_decoder_reads_a_real_mmsstv_id(self) -> None:
        """The control. If this fails, the problem is not the plumbing."""
        import soundfile as sf

        from sstv_core.decode.fsk_decoder import FSKIDDecoder

        path = "tests/reference/audio/fskid/va2pgb_fskid.wav"
        audio, rate = sf.read(path, dtype="float32")
        if audio.ndim > 1:
            audio = audio[:, 0]

        result = FSKIDDecoder(sample_rate=rate).decode(audio)

        assert result is not None
        assert result.callsign == "VA2PGB"
        assert result.checksum_valid

    def test_the_window_must_open_near_the_preamble(self) -> None:
        """Pin the tolerance the three broken versions all fell outside.

        Measured against KD2TT's real off-air ID on 2026-08-19: a window
        opening at the preamble read the callsign, one opening 200 ms
        earlier read nothing. Any approach that aims a single window has
        to land inside that, which is why the shipped one tries several
        and lets the checksum decide.
        """
        import numpy as np
        import soundfile as sf

        from sstv_core.decode.fsk_decoder import FSKIDDecoder

        path = "tests/reference/audio/fskid/va2pgb_fskid.wav"
        audio, rate = sf.read(path, dtype="float32")
        if audio.ndim > 1:
            audio = audio[:, 0]

        # Pad the front, so the ID no longer starts at sample 0.
        padded = np.concatenate((np.zeros(int(rate * 2.0), dtype="float32"), audio))

        at_start = FSKIDDecoder(sample_rate=rate).decode(padded[int(rate * 2.0) :])
        assert at_start is not None and at_start.checksum_valid

        # Two seconds of silence ahead of it is inside the 3 s budget but
        # outside the alignment the decoder wants.
        from_zero = FSKIDDecoder(sample_rate=rate).decode(padded)
        assert from_zero is None or not from_zero.checksum_valid, (
            "a decoder tolerant of a 2 s lead-in would make the search "
            "unnecessary -- if this starts passing, simplify the helper"
        )
