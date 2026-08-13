"""SpyServer wire protocol: framing, commands, and IQ conversion.

Pure functions over bytes — no socket, no state. Constants verified
byte-identical across SDR++ (spyserver_protocol.h),
miweber67/spyserver_client, and xritdemod's SpyServerFrontend.cpp.

Everything on the wire is packed little-endian uint32.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

import numpy as np

PROTOCOL_VERSION = 0x020006A4  # (2 << 24) | (0 << 16) | 1700
DEFAULT_PORT = 5555

CMD_HELLO = 0
CMD_SET_SETTING = 2

SETTING_STREAMING_MODE = 0
SETTING_STREAMING_ENABLED = 1
SETTING_GAIN = 2
SETTING_IQ_FORMAT = 100
SETTING_IQ_FREQUENCY = 101
SETTING_IQ_DECIMATION = 102
SETTING_IQ_DIGITAL_GAIN = 103

MSG_DEVICE_INFO = 0
MSG_CLIENT_SYNC = 1
MSG_UINT8_IQ = 100
MSG_INT16_IQ = 101
MSG_INT24_IQ = 102
MSG_FLOAT_IQ = 103

STREAM_MODE_IQ_ONLY = 1

FORMAT_UINT8 = 1
FORMAT_INT16 = 2
FORMAT_FLOAT = 4

MAX_MESSAGE_BODY_SIZE = 1 << 20
HEADER_SIZE = 20
DEVICE_INFO_SIZE = 48
CLIENT_SYNC_SIZE = 36


class ProtocolError(Exception):
    """Raised when bytes on the wire don't match the protocol."""


@dataclass(frozen=True)
class MessageHeader:
    protocol_id: int
    message_type: int
    stream_type: int
    sequence_number: int
    body_size: int

    @property
    def msg_type(self) -> int:
        """Message type — the low 16 bits."""
        return self.message_type & 0xFFFF

    @property
    def gain_db(self) -> int:
        """Server-applied digital gain in dB — the high 16 bits.

        Ignoring this silently mis-scales amplitude whenever the server
        applies gain.
        """
        return (self.message_type >> 16) & 0xFFFF


@dataclass(frozen=True)
class DeviceInfo:
    device_type: int
    device_serial: int
    maximum_sample_rate: int
    maximum_bandwidth: int
    decimation_stage_count: int
    gain_stage_count: int
    maximum_gain_index: int
    minimum_frequency: int
    maximum_frequency: int
    resolution: int
    min_iq_decimation: int
    forced_iq_format: int


@dataclass(frozen=True)
class ClientSync:
    can_control: int
    gain: int
    device_center_frequency: int
    iq_center_frequency: int
    fft_center_frequency: int
    minimum_iq_center_frequency: int
    maximum_iq_center_frequency: int
    minimum_fft_center_frequency: int
    maximum_fft_center_frequency: int


def build_hello(client_name: str) -> bytes:
    """CMD_HELLO: version then the client name as raw bytes.

    The name is not NUL-terminated and carries no length prefix —
    BodySize alone delimits it.
    """
    name = client_name.encode("utf-8")
    body = struct.pack("<I", PROTOCOL_VERSION) + name
    return struct.pack("<II", CMD_HELLO, len(body)) + body


def build_set_setting(setting_id: int, value: int) -> bytes:
    body = struct.pack("<II", setting_id, value)
    return struct.pack("<II", CMD_SET_SETTING, len(body)) + body


def parse_message_header(data: bytes) -> MessageHeader:
    if len(data) < HEADER_SIZE:
        raise ProtocolError(
            f"Message header is {len(data)} bytes; I need {HEADER_SIZE}."
        )
    protocol_id, message_type, stream_type, sequence_number, body_size = struct.unpack(
        "<IIIII", data[:HEADER_SIZE]
    )
    if body_size > MAX_MESSAGE_BODY_SIZE:
        raise ProtocolError(
            f"Message claims a {body_size}-byte body, over the "
            f"{MAX_MESSAGE_BODY_SIZE} limit."
        )
    return MessageHeader(
        protocol_id=protocol_id,
        message_type=message_type,
        stream_type=stream_type,
        sequence_number=sequence_number,
        body_size=body_size,
    )


def parse_device_info(body: bytes) -> DeviceInfo:
    if len(body) < DEVICE_INFO_SIZE:
        raise ProtocolError(
            f"DeviceInfo is {len(body)} bytes; I need {DEVICE_INFO_SIZE}."
        )
    fields = struct.unpack("<12I", body[:DEVICE_INFO_SIZE])
    return DeviceInfo(*fields)


def parse_client_sync(body: bytes) -> ClientSync:
    if len(body) < CLIENT_SYNC_SIZE:
        raise ProtocolError(
            f"ClientSync is {len(body)} bytes; I need {CLIENT_SYNC_SIZE}."
        )
    fields = struct.unpack("<9I", body[:CLIENT_SYNC_SIZE])
    return ClientSync(*fields)


def iq_bytes_to_complex(body: bytes, msg_type: int, gain_db: int) -> np.ndarray:
    """Interleaved I,Q bytes to complex64, with server gain applied."""
    if msg_type == MSG_INT24_IQ:
        raise ProtocolError(
            "The server sent INT24 IQ, which I don't support. "
            "I ask for INT16, so this shouldn't happen."
        )
    if msg_type == MSG_UINT8_IQ:
        raw = np.frombuffer(body, dtype=np.uint8)
        if len(raw) % 2:
            raise ProtocolError("UINT8 IQ payload has an odd number of samples.")
        values = (raw.astype(np.float32) - 128.0) / 128.0
    elif msg_type == MSG_INT16_IQ:
        if len(body) % 4:
            raise ProtocolError("INT16 IQ payload isn't a whole number of I/Q pairs.")
        values = np.frombuffer(body, dtype="<i2").astype(np.float32) / 32768.0
    elif msg_type == MSG_FLOAT_IQ:
        if len(body) % 8:
            raise ProtocolError("FLOAT IQ payload isn't a whole number of I/Q pairs.")
        values = np.frombuffer(body, dtype="<f4").astype(np.float32)
    else:
        raise ProtocolError(f"Message type {msg_type} isn't an IQ payload.")

    iq = values[0::2] + 1j * values[1::2]
    if gain_db:
        iq = iq * (10.0 ** (gain_db / 20.0))
    return iq.astype(np.complex64)
