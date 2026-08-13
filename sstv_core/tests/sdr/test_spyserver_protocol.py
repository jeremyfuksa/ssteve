"""SpyServer wire format: framing, commands, IQ conversion.

Constants and layouts verified byte-identical across SDR++
(spyserver_protocol.h), miweber67/spyserver_client, and xritdemod.
"""

from __future__ import annotations

import struct

import numpy as np
import pytest

from sstv_core.sdr.spyserver import protocol as p


class TestCommands:
    def test_hello_carries_version_then_raw_client_name(self):
        out = p.build_hello("SSTeVe")
        cmd_type, body_size = struct.unpack("<II", out[:8])
        assert cmd_type == p.CMD_HELLO
        body = out[8:]
        assert body_size == len(body)
        (version,) = struct.unpack("<I", body[:4])
        assert version == p.PROTOCOL_VERSION
        # Raw bytes: no NUL terminator, no length prefix.
        assert body[4:] == b"SSTeVe"

    def test_set_setting_is_id_then_value(self):
        out = p.build_set_setting(p.SETTING_IQ_FREQUENCY, 14_230_000)
        cmd_type, body_size = struct.unpack("<II", out[:8])
        assert cmd_type == p.CMD_SET_SETTING
        assert body_size == 8
        setting_id, value = struct.unpack("<II", out[8:])
        assert setting_id == p.SETTING_IQ_FREQUENCY
        assert value == 14_230_000


class TestMessageHeader:
    def _header(self, message_type: int, body_size: int = 0, seq: int = 0) -> bytes:
        return struct.pack(
            "<IIIII", p.PROTOCOL_VERSION, message_type, 1, seq, body_size
        )

    def test_parses_all_five_fields(self):
        h = p.parse_message_header(self._header(p.MSG_INT16_IQ, body_size=64, seq=7))
        assert h.protocol_id == p.PROTOCOL_VERSION
        assert h.stream_type == 1
        assert h.sequence_number == 7
        assert h.body_size == 64

    def test_gain_lives_in_the_high_16_bits(self):
        """The hazard: masking the high bits off silently mis-scales amplitude."""
        packed = (12 << 16) | p.MSG_INT16_IQ
        h = p.parse_message_header(self._header(packed))
        assert h.msg_type == p.MSG_INT16_IQ
        assert h.gain_db == 12

    def test_zero_gain_is_the_common_case(self):
        h = p.parse_message_header(self._header(p.MSG_INT16_IQ))
        assert h.msg_type == p.MSG_INT16_IQ
        assert h.gain_db == 0

    def test_short_header_is_rejected(self):
        with pytest.raises(p.ProtocolError):
            p.parse_message_header(b"\x00" * 19)

    def test_absurd_body_size_is_rejected(self):
        bad = struct.pack(
            "<IIIII", p.PROTOCOL_VERSION, p.MSG_INT16_IQ, 1, 0, p.MAX_MESSAGE_BODY_SIZE + 1
        )
        with pytest.raises(p.ProtocolError):
            p.parse_message_header(bad)


class TestIQConversion:
    def test_int16_is_signed_scaled_and_interleaved_i_first(self):
        body = struct.pack("<4h", 16384, -16384, 0, 32767)
        out = p.iq_bytes_to_complex(body, p.MSG_INT16_IQ, gain_db=0)
        assert out.dtype == np.complex64
        assert len(out) == 2
        assert out[0].real == pytest.approx(0.5, abs=1e-4)
        assert out[0].imag == pytest.approx(-0.5, abs=1e-4)
        assert out[1].real == pytest.approx(0.0, abs=1e-4)

    def test_uint8_is_offset_binary(self):
        body = bytes([128, 128, 255, 0])
        out = p.iq_bytes_to_complex(body, p.MSG_UINT8_IQ, gain_db=0)
        assert len(out) == 2
        assert out[0].real == pytest.approx(0.0, abs=1e-2)
        assert out[1].real == pytest.approx(0.992, abs=1e-2)
        assert out[1].imag == pytest.approx(-1.0, abs=1e-2)

    def test_gain_is_applied_as_ten_to_the_db_over_twenty(self):
        body = struct.pack("<2h", 16384, 0)
        plain = p.iq_bytes_to_complex(body, p.MSG_INT16_IQ, gain_db=0)
        gained = p.iq_bytes_to_complex(body, p.MSG_INT16_IQ, gain_db=20)
        assert gained[0].real == pytest.approx(plain[0].real * 10.0, rel=1e-4)

    def test_int24_is_refused_rather_than_guessed(self):
        with pytest.raises(p.ProtocolError, match="INT24"):
            p.iq_bytes_to_complex(b"\x00" * 6, p.MSG_INT24_IQ, gain_db=0)

    def test_truncated_pair_is_rejected(self):
        with pytest.raises(p.ProtocolError):
            p.iq_bytes_to_complex(b"\x00" * 3, p.MSG_INT16_IQ, gain_db=0)


class TestStructParsing:
    def test_device_info_round_trips(self):
        body = struct.pack(
            "<12I", 3, 0xDEADBEEF, 10_000_000, 8_000_000, 9, 1, 49,
            24_000_000, 1_800_000_000, 8, 1, 0,
        )
        info = p.parse_device_info(body)
        assert info.device_type == 3
        assert info.maximum_sample_rate == 10_000_000
        assert info.decimation_stage_count == 9
        assert info.min_iq_decimation == 1
        assert info.forced_iq_format == 0

    def test_client_sync_round_trips(self):
        body = struct.pack(
            "<9I", 1, 20, 14_200_000, 14_230_000, 14_200_000,
            14_000_000, 14_350_000, 14_000_000, 14_350_000,
        )
        sync = p.parse_client_sync(body)
        assert sync.can_control == 1
        assert sync.iq_center_frequency == 14_230_000
        assert sync.minimum_iq_center_frequency == 14_000_000
        assert sync.maximum_iq_center_frequency == 14_350_000

    def test_short_bodies_are_rejected(self):
        with pytest.raises(p.ProtocolError):
            p.parse_device_info(b"\x00" * 40)
        with pytest.raises(p.ProtocolError):
            p.parse_client_sync(b"\x00" * 20)
