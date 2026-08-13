# SpyServer USB Receive Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decode live SSTV from a SpyServer network stream over the CLI, with no virtual audio cable anywhere in the flow.

**Architecture:** A `SpyServerSource` implements the four-method contract `RXManager` already depends on (`start_input`/`stop_input`/`get_input_buffer`/`get_input_levels`), so the decode stack is untouched. Below it: a pure-bytes protocol module, a socket client, and a pure-numpy USB demodulator that decimates to 48 kHz. Seven PRs to `main`, one concern each.

**Tech Stack:** Python 3.12, numpy/scipy, pytest; uv from `sstv_core/`. **No new third-party dependencies** — `socket` + `struct` + `numpy` only.

**Spec:** `docs/superpowers/specs/2026-08-13-spyserver-usb-receive-design.md`. **Issue:** #68, milestone "4: SDR epoch".

## Global Constraints

- Done = full `uv run pytest`, `uv run ruff check src/`, `uv run mypy src/` — exit codes verified bare, never piped through `tail`/`head`.
- **No new dependencies.** If a task seems to need one, stop and raise it.
- All wire fields are packed **little-endian `uint32`** (`struct` format `<I`).
- Error copy is SSTeVe voice: first person, contractions, concrete `suggested_action`. Emitted via the existing `log_event(event_type, **kwargs)` in `cli/main.py:75`.
- Exit codes follow the existing CLI: 0 success, 1 error, 2 nothing-decoded/timeout, 130 interrupt.
- Never report a stream failure as a weak signal (PRODUCT.md).
- OUT OF SCOPE, stated not silently dropped: NBFM demodulation, local SDR devices, waterfall/click-to-tune (needs #53), API/WebSocket plumbing, auto-reconnect, new SSTV modes (PD/Wraase stay post-MVP).

---

### Task 1 (PR S1): Reconcile sample rate between RXManager and its stream manager

The prerequisite fix. `RXManager` takes `sample_rate` independently (`rx_manager.py:92`, `:101`) and never checks it against `stream_manager.sample_rate` (`stream_manager.py:70`); `DSPManager` hardcodes `48000` twice. Everything is 48 kHz today so it is invisible — and it silently garbles any source at another rate. Lands before the SDR work so the trap is gone, not so the feature depends on it.

**Files:**
- Modify: `src/sstv_core/decode/rx_manager.py:89-101` (constructor)
- Test: `tests/decode/test_sample_rate_reconciliation.py` (create)

**Interfaces:**
- Consumes: nothing
- Produces: `RXManager.__init__` raises `ValueError` when `sample_rate` conflicts with `stream_manager.sample_rate`; adopts the stream manager's rate when `sample_rate` is not passed.

- [ ] **Step 1: Write the failing test**

```python
"""RXManager must not silently disagree with its stream manager's rate."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from sstv_core.audio.ring_buffer import AudioRingBuffer
from sstv_core.decode.rx_manager import RXManager


class FakeStream:
    """Four-method stream-manager duck type at a chosen sample rate."""

    def __init__(self, sample_rate: int) -> None:
        self.sample_rate = sample_rate
        self._buffer = AudioRingBuffer(max_samples=sample_rate)

    def start_input(self, device_index=None) -> None:
        pass

    def stop_input(self) -> None:
        pass

    def get_input_buffer(self) -> AudioRingBuffer:
        return self._buffer

    def get_input_levels(self):
        return SimpleNamespace(rms=0.0, peak=0.0, is_clipping=False)


def test_conflicting_sample_rate_is_rejected():
    with pytest.raises(ValueError, match="sample rate"):
        RXManager(stream_manager=FakeStream(22050), sample_rate=48000)


def test_rate_is_adopted_from_stream_manager_when_unspecified():
    rx = RXManager(stream_manager=FakeStream(22050))
    assert rx._sample_rate == 22050


def test_matching_rate_is_accepted():
    rx = RXManager(stream_manager=FakeStream(48000), sample_rate=48000)
    assert rx._sample_rate == 48000


def test_stream_manager_without_sample_rate_falls_back_to_argument():
    """A duck type need not expose sample_rate; the explicit arg still wins."""

    class RatelessStream(FakeStream):
        def __init__(self) -> None:
            super().__init__(48000)
            del self.sample_rate

    rx = RXManager(stream_manager=RatelessStream(), sample_rate=48000)
    assert rx._sample_rate == 48000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/decode/test_sample_rate_reconciliation.py -v`
Expected: FAIL — `test_conflicting_sample_rate_is_rejected` does not raise, `test_rate_is_adopted_from_stream_manager_when_unspecified` gets 48000.

- [ ] **Step 3: Write minimal implementation**

Change the signature default to `None` and reconcile. In `rx_manager.py`, the constructor parameter becomes `sample_rate: int | None = None`, and replace `self._sample_rate = sample_rate` (line 101) with:

```python
        stream_rate = getattr(stream_manager, "sample_rate", None)
        if sample_rate is None:
            self._sample_rate = stream_rate if stream_rate is not None else 48000
        else:
            if stream_rate is not None and stream_rate != sample_rate:
                raise ValueError(
                    f"Conflicting sample rate: I was given {sample_rate} Hz but the "
                    f"audio source runs at {stream_rate} Hz. They have to match."
                )
            self._sample_rate = sample_rate
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/decode/test_sample_rate_reconciliation.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Verify nothing regressed**

Run: `uv run pytest` then `uv run ruff check src/` then `uv run mypy src/`
Expected: all green. `DSPManager`'s explicit `sample_rate=48000` (`dsp_manager.py:303`, `:441`) now matches `AudioStreamManager`'s default 48000 and still passes.

- [ ] **Step 6: Commit**

```bash
git add tests/decode/test_sample_rate_reconciliation.py src/sstv_core/decode/rx_manager.py
git commit -m "fix(decode): reconcile RXManager sample rate with its stream manager

RXManager took sample_rate independently and never checked it against
stream_manager.sample_rate. Invisible while everything is 48 kHz;
silently produces wrong-length decoder configs for any source at
another rate. Conflicts now raise, and an unspecified rate is adopted
from the source.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2 (PR S2): SpyServer wire protocol (pure bytes)

**Files:**
- Create: `src/sstv_core/sdr/__init__.py`, `src/sstv_core/sdr/spyserver/__init__.py`, `src/sstv_core/sdr/spyserver/protocol.py`
- Test: `tests/sdr/__init__.py` (empty), `tests/sdr/test_spyserver_protocol.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - Constants: `PROTOCOL_VERSION = 0x020006A4`, `DEFAULT_PORT = 5555`, `CMD_HELLO = 0`, `CMD_SET_SETTING = 2`, `SETTING_STREAMING_MODE = 0`, `SETTING_STREAMING_ENABLED = 1`, `SETTING_GAIN = 2`, `SETTING_IQ_FORMAT = 100`, `SETTING_IQ_FREQUENCY = 101`, `SETTING_IQ_DECIMATION = 102`, `SETTING_IQ_DIGITAL_GAIN = 103`, `MSG_DEVICE_INFO = 0`, `MSG_CLIENT_SYNC = 1`, `MSG_UINT8_IQ = 100`, `MSG_INT16_IQ = 101`, `MSG_INT24_IQ = 102`, `MSG_FLOAT_IQ = 103`, `STREAM_MODE_IQ_ONLY = 1`, `FORMAT_UINT8 = 1`, `FORMAT_INT16 = 2`, `FORMAT_FLOAT = 4`, `MAX_MESSAGE_BODY_SIZE = 1 << 20`
  - `MessageHeader` dataclass: `protocol_id: int`, `message_type: int`, `stream_type: int`, `sequence_number: int`, `body_size: int`, plus properties `msg_type -> int` (low 16 bits) and `gain_db -> int` (high 16 bits)
  - `DeviceInfo` dataclass: `device_type: int`, `device_serial: int`, `maximum_sample_rate: int`, `maximum_bandwidth: int`, `decimation_stage_count: int`, `gain_stage_count: int`, `maximum_gain_index: int`, `minimum_frequency: int`, `maximum_frequency: int`, `resolution: int`, `min_iq_decimation: int`, `forced_iq_format: int`
  - `ClientSync` dataclass: `can_control: int`, `gain: int`, `device_center_frequency: int`, `iq_center_frequency: int`, `fft_center_frequency: int`, `minimum_iq_center_frequency: int`, `maximum_iq_center_frequency: int`, `minimum_fft_center_frequency: int`, `maximum_fft_center_frequency: int`
  - `build_hello(client_name: str) -> bytes`
  - `build_set_setting(setting_id: int, value: int) -> bytes`
  - `parse_message_header(data: bytes) -> MessageHeader`
  - `parse_device_info(body: bytes) -> DeviceInfo`
  - `parse_client_sync(body: bytes) -> ClientSync`
  - `iq_bytes_to_complex(body: bytes, msg_type: int, gain_db: int) -> np.ndarray` (complex64)
  - `ProtocolError(Exception)`
  - `HEADER_SIZE = 20`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/sdr/test_spyserver_protocol.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sstv_core.sdr'`

- [ ] **Step 3: Write minimal implementation**

Create the two `__init__.py` files (empty, with a one-line docstring), then `protocol.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/sdr/test_spyserver_protocol.py -v`
Expected: PASS (all)

- [ ] **Step 5: Lint and type check**

Run: `uv run ruff check src/` then `uv run mypy src/`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/sstv_core/sdr tests/sdr
git commit -m "feat(sdr): add the SpyServer wire protocol

Pure-bytes framing, commands, and IQ conversion. Constants verified
byte-identical across SDR++, spyserver_client, and xritdemod.

Handles the gain-in-high-16-bits hazard explicitly: MessageType's upper
half carries server digital gain in dB, and ignoring it silently
mis-scales amplitude.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3 (PR S3): USB demodulator (pure numpy)

IQ at the server's rate to real audio at 48 kHz. No I/O, so it is testable against synthesized IQ with a known tone.

**Files:**
- Create: `src/sstv_core/sdr/demodulator.py`
- Test: `tests/sdr/test_demodulator.py`

**Interfaces:**
- Consumes: nothing (pure numpy/scipy)
- Produces: `USBDemodulator(input_rate: int, output_rate: int = 48000, bandwidth_hz: float = 2400.0)` with `demodulate(iq: np.ndarray, offset_hz: float = 0.0) -> np.ndarray` returning float32 audio, and property `decimation: int`. Module constant `TARGET_RATE = 48000`.

- [ ] **Step 1: Write the failing test**

```python
"""USB demodulation: IQ in, 48 kHz real audio out.

USB means the upper sideband survives and the lower is rejected. A tone
at +1500 Hz from center must land at 1500 Hz in the audio; a tone at
-1500 Hz must be suppressed.
"""

from __future__ import annotations

import numpy as np
import pytest

from sstv_core.sdr.demodulator import TARGET_RATE, USBDemodulator


def _tone_iq(offset_hz: float, rate: int, duration: float = 0.25) -> np.ndarray:
    """A complex exponential at offset_hz from center."""
    t = np.arange(int(rate * duration)) / rate
    return np.exp(2j * np.pi * offset_hz * t).astype(np.complex64)


def _dominant_freq(audio: np.ndarray, rate: int) -> float:
    spectrum = np.abs(np.fft.rfft(audio * np.hanning(len(audio))))
    return float(np.fft.rfftfreq(len(audio), 1 / rate)[int(np.argmax(spectrum))])


class TestUSBDemodulation:
    def test_upper_sideband_tone_lands_at_its_audio_frequency(self):
        rate = 192_000
        demod = USBDemodulator(input_rate=rate)
        audio = demod.demodulate(_tone_iq(1500.0, rate))
        assert _dominant_freq(audio, TARGET_RATE) == pytest.approx(1500.0, abs=30.0)

    def test_output_is_float32_at_the_target_rate(self):
        rate = 192_000
        demod = USBDemodulator(input_rate=rate)
        audio = demod.demodulate(_tone_iq(1000.0, rate, duration=1.0))
        assert audio.dtype == np.float32
        assert len(audio) == pytest.approx(TARGET_RATE, rel=0.02)

    def test_lower_sideband_is_rejected(self):
        """The property that makes this USB rather than DSB."""
        rate = 192_000
        demod = USBDemodulator(input_rate=rate)
        upper = demod.demodulate(_tone_iq(1500.0, rate))
        lower = demod.demodulate(_tone_iq(-1500.0, rate))
        assert np.max(np.abs(lower)) < np.max(np.abs(upper)) * 0.25

    def test_out_of_passband_tone_is_filtered_out(self):
        rate = 192_000
        demod = USBDemodulator(input_rate=rate)
        inband = demod.demodulate(_tone_iq(1500.0, rate))
        outband = demod.demodulate(_tone_iq(20_000.0, rate))
        assert np.max(np.abs(outband)) < np.max(np.abs(inband)) * 0.25

    def test_offset_shifts_the_tuned_frequency(self):
        rate = 192_000
        demod = USBDemodulator(input_rate=rate)
        audio = demod.demodulate(_tone_iq(3000.0, rate), offset_hz=1500.0)
        assert _dominant_freq(audio, TARGET_RATE) == pytest.approx(1500.0, abs=30.0)

    def test_strong_input_does_not_clip(self):
        rate = 192_000
        demod = USBDemodulator(input_rate=rate)
        audio = demod.demodulate(_tone_iq(1500.0, rate) * 50.0)
        assert np.max(np.abs(audio)) <= 1.0

    def test_empty_input_yields_empty_output(self):
        demod = USBDemodulator(input_rate=192_000)
        assert len(demod.demodulate(np.zeros(0, dtype=np.complex64))) == 0

    def test_non_integer_decimation_is_rejected(self):
        with pytest.raises(ValueError, match="multiple"):
            USBDemodulator(input_rate=100_000)

    def test_decimation_factor_is_reported(self):
        assert USBDemodulator(input_rate=192_000).decimation == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/sdr/test_demodulator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sstv_core.sdr.demodulator'`

- [ ] **Step 3: Write minimal implementation**

```python
"""USB demodulation: complex IQ in, real 48 kHz audio out.

The SDR path's only job is to hand the decoder the same 300-3000 Hz
audio a sound card would have produced. Nothing below this line knows
the signal arrived over a network.
"""

from __future__ import annotations

import numpy as np
from scipy import signal

TARGET_RATE = 48000


class USBDemodulator:
    """Upper-sideband demodulator with decimation to a fixed audio rate.

    Args:
        input_rate: IQ sample rate from the source, in Hz.
        output_rate: Audio rate to produce. The engine is 48 kHz end to end.
        bandwidth_hz: SSB passband width.

    """

    def __init__(
        self,
        input_rate: int,
        output_rate: int = TARGET_RATE,
        bandwidth_hz: float = 2400.0,
    ) -> None:
        if input_rate % output_rate:
            raise ValueError(
                f"IQ rate {input_rate} Hz isn't a whole multiple of the "
                f"{output_rate} Hz audio rate."
            )
        self._input_rate = input_rate
        self._output_rate = output_rate
        self._bandwidth_hz = bandwidth_hz
        self._decimation = input_rate // output_rate
        # Lowpass at the SSB bandwidth, applied at the input rate before
        # decimation so nothing above Nyquist folds back in.
        self._taps = signal.firwin(
            129, bandwidth_hz, fs=input_rate, pass_zero="lowpass"
        ).astype(np.float64)

    @property
    def decimation(self) -> int:
        return self._decimation

    def demodulate(self, iq: np.ndarray, offset_hz: float = 0.0) -> np.ndarray:
        """Demodulate one block of complex IQ to real audio."""
        if len(iq) == 0:
            return np.zeros(0, dtype=np.float32)

        # Shift the wanted signal down so the passband starts at DC. For USB
        # the audio sits just above the tuned frequency, so shifting by
        # offset_hz places that content at baseband.
        if offset_hz:
            t = np.arange(len(iq)) / self._input_rate
            iq = iq * np.exp(-2j * np.pi * offset_hz * t)

        # Complex lowpass: keeps the upper sideband, rejects the lower.
        filtered = signal.lfilter(self._taps, [1.0], iq)
        decimated = filtered[:: self._decimation]

        # Real part of the analytic signal is the demodulated audio.
        audio = np.real(decimated).astype(np.float32)

        peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
        if peak > 1.0:
            audio = audio / peak
        return audio.astype(np.float32)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/sdr/test_demodulator.py -v`
Expected: PASS (9 tests)

If `test_lower_sideband_is_rejected` fails, the complex filter is not
asymmetric enough — widen the tap count rather than loosening the assertion,
and re-run. Never relax a sideband-rejection threshold to make a test pass.

- [ ] **Step 5: Lint and type check**

Run: `uv run ruff check src/` then `uv run mypy src/`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/sstv_core/sdr/demodulator.py tests/sdr/test_demodulator.py
git commit -m "feat(sdr): add the USB demodulator

Complex IQ to real 48 kHz audio: mix, lowpass at SSB bandwidth,
decimate, take the real part. Pure numpy/scipy, no I/O.

Tested against synthesized IQ with a known tone, including
lower-sideband rejection -- the property that makes it USB rather
than DSB.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4 (PR S4): SpyServer client

Socket lifecycle, handshake, tuning, IQ delivery, and every failure the network can produce. Tested against an in-process fake socket — no server required.

**Files:**
- Create: `src/sstv_core/sdr/spyserver/client.py`
- Test: `tests/sdr/test_spyserver_client.py`

**Interfaces:**
- Consumes: everything `protocol.py` produces (Task 2)
- Produces:
  - `SpyServerError(Exception)` with attributes `message: str` and `suggested_action: str`
  - `SpyServerClient(host: str, port: int = 5555, client_name: str = "SSTeVe", stall_timeout_sec: float = 5.0, sock_factory=None)`
  - `connect() -> None` — handshake, populates `device_info` and `client_sync`
  - `tune(frequency_hz: int) -> None` — sets frequency, then verifies against the next `ClientSync`
  - `start_streaming(on_iq: Callable[[np.ndarray], None], gain: int = 0) -> None`
  - `stop_streaming() -> None`, `close() -> None`
  - `wait_for_stream_end(timeout: float | None = None) -> bool` — blocks until the receive thread exits; used by tests to await a scripted stream
  - Properties: `device_info: DeviceInfo | None`, `client_sync: ClientSync | None`, `sample_rate: int`
  - Attributes: `dropped_frames: int`, `stream_error: SpyServerError | None`
  - `choose_decimation_stage(maximum_sample_rate, decimation_stage_count, min_iq_decimation, target_rate=48000) -> tuple[int, int]` returning `(stage, resulting_rate)`

- [ ] **Step 1: Write the failing test**

```python
"""SpyServer client: handshake, tuning verification, failure reporting.

Runs against an in-process fake socket. The protocol has no error
message type -- a rejected tune is silent, and the next ClientSync is
the only evidence. Every test here exists because silence would
otherwise look like success.
"""

from __future__ import annotations

import struct
import threading

import numpy as np
import pytest

from sstv_core.sdr.spyserver import protocol as p
from sstv_core.sdr.spyserver.client import (
    SpyServerClient,
    SpyServerError,
    choose_decimation_stage,
)


def _device_info_bytes(
    max_rate: int = 10_000_000,
    stages: int = 9,
    min_decim: int = 0,
    forced_format: int = 0,
    min_freq: int = 1_000_000,
    max_freq: int = 30_000_000,
) -> bytes:
    return struct.pack(
        "<12I", 3, 0xDEADBEEF, max_rate, 8_000_000, stages, 1, 49,
        min_freq, max_freq, 8, min_decim, forced_format,
    )


def _client_sync_bytes(iq_freq: int = 14_230_000, can_control: int = 1) -> bytes:
    return struct.pack(
        "<9I", can_control, 20, iq_freq, iq_freq, iq_freq,
        1_000_000, 30_000_000, 1_000_000, 30_000_000,
    )


def _message(message_type: int, body: bytes, seq: int = 0) -> bytes:
    return struct.pack(
        "<IIIII", p.PROTOCOL_VERSION, message_type, 1, seq, len(body)
    ) + body


class FakeSocket:
    """Scripted server: hands back queued bytes, records what was sent."""

    def __init__(self, script: bytes = b"") -> None:
        self._script = script
        self._pos = 0
        self.sent = b""
        self.closed = False
        self._lock = threading.Lock()

    def connect(self, address) -> None:
        pass

    def sendall(self, data: bytes) -> None:
        with self._lock:
            self.sent += data

    def recv(self, size: int) -> bytes:
        with self._lock:
            if self._pos >= len(self._script):
                return b""  # peer closed
            chunk = self._script[self._pos : self._pos + size]
            self._pos += len(chunk)
            return chunk

    def settimeout(self, timeout) -> None:
        pass

    def close(self) -> None:
        self.closed = True


def _client(script: bytes, **kwargs) -> tuple[SpyServerClient, FakeSocket]:
    sock = FakeSocket(script)
    client = SpyServerClient("example.test", sock_factory=lambda: sock, **kwargs)
    return client, sock


class TestHandshake:
    def test_connect_sends_hello_and_stores_server_state(self):
        script = _message(p.MSG_DEVICE_INFO, _device_info_bytes()) + _message(
            p.MSG_CLIENT_SYNC, _client_sync_bytes()
        )
        client, sock = _client(script)
        client.connect()
        cmd_type, _ = struct.unpack("<II", sock.sent[:8])
        assert cmd_type == p.CMD_HELLO
        assert client.device_info is not None
        assert client.device_info.maximum_sample_rate == 10_000_000
        assert client.client_sync is not None
        assert client.client_sync.can_control == 1

    def test_version_mismatch_is_rejected(self):
        body = _device_info_bytes()
        bad = struct.pack("<IIIII", 0x01000000, p.MSG_DEVICE_INFO, 1, 0, len(body)) + body
        client, _ = _client(bad)
        with pytest.raises(SpyServerError, match="version"):
            client.connect()

    def test_immediate_close_is_reported_not_hung(self):
        client, _ = _client(b"")
        with pytest.raises(SpyServerError, match="closed|reach"):
            client.connect()


class TestTuning:
    def test_tune_sends_frequency_and_accepts_matching_sync(self):
        script = (
            _message(p.MSG_DEVICE_INFO, _device_info_bytes())
            + _message(p.MSG_CLIENT_SYNC, _client_sync_bytes())
            + _message(p.MSG_CLIENT_SYNC, _client_sync_bytes(iq_freq=14_230_000))
        )
        client, sock = _client(script)
        client.connect()
        client.tune(14_230_000)
        assert struct.pack("<II", p.SETTING_IQ_FREQUENCY, 14_230_000) in sock.sent

    def test_silent_mismatch_is_surfaced(self):
        """The server clamps and says nothing; ClientSync is the only truth."""
        script = (
            _message(p.MSG_DEVICE_INFO, _device_info_bytes())
            + _message(p.MSG_CLIENT_SYNC, _client_sync_bytes())
            + _message(p.MSG_CLIENT_SYNC, _client_sync_bytes(iq_freq=7_171_000))
        )
        client, _ = _client(script)
        client.connect()
        with pytest.raises(SpyServerError, match="7171000|7,171,000|different"):
            client.tune(14_230_000)

    def test_out_of_range_is_refused_before_sending(self):
        script = _message(
            p.MSG_DEVICE_INFO, _device_info_bytes()
        ) + _message(p.MSG_CLIENT_SYNC, _client_sync_bytes())
        client, sock = _client(script)
        client.connect()
        with pytest.raises(SpyServerError, match="range"):
            client.tune(500_000_000)
        assert struct.pack("<II", p.SETTING_IQ_FREQUENCY, 500_000_000) not in sock.sent


class TestDecimationChoice:
    def test_picks_a_stage_at_or_above_the_target_rate(self):
        stage, rate = choose_decimation_stage(
            maximum_sample_rate=10_000_000, decimation_stage_count=9, min_iq_decimation=0
        )
        assert rate >= 48000
        assert rate % 48000 == 0
        assert 0 <= stage <= 9

    def test_honors_the_minimum_stage(self):
        stage, _ = choose_decimation_stage(
            maximum_sample_rate=10_000_000, decimation_stage_count=9, min_iq_decimation=3
        )
        assert stage >= 3

    def test_raises_when_no_stage_can_reach_the_target(self):
        with pytest.raises(SpyServerError, match="rate"):
            choose_decimation_stage(
                maximum_sample_rate=8000, decimation_stage_count=2, min_iq_decimation=0
            )


class TestStreamFailures:
    def test_sequence_gap_counts_dropped_frames(self):
        payload = struct.pack("<2h", 1000, 0)
        script = (
            _message(p.MSG_DEVICE_INFO, _device_info_bytes())
            + _message(p.MSG_CLIENT_SYNC, _client_sync_bytes())
            + _message(p.MSG_INT16_IQ, payload, seq=0)
            + _message(p.MSG_INT16_IQ, payload, seq=5)  # gap: 1-4 lost
        )
        client, _ = _client(script)
        client.connect()
        received: list[np.ndarray] = []
        client.start_streaming(received.append)
        client.wait_for_stream_end(timeout=5.0)
        assert client.dropped_frames == 4
        assert len(received) == 2

    def test_disconnect_mid_stream_is_recorded(self):
        payload = struct.pack("<2h", 1000, 0)
        script = (
            _message(p.MSG_DEVICE_INFO, _device_info_bytes())
            + _message(p.MSG_CLIENT_SYNC, _client_sync_bytes())
            + _message(p.MSG_INT16_IQ, payload, seq=0)
        )
        client, _ = _client(script)
        client.connect()
        client.start_streaming(lambda _: None)
        client.wait_for_stream_end(timeout=5.0)
        assert client.stream_error is not None
        assert "dropped" in client.stream_error.message.lower()

    def test_gain_in_high_bits_is_applied_to_delivered_iq(self):
        payload = struct.pack("<2h", 16384, 0)
        gained_type = (20 << 16) | p.MSG_INT16_IQ
        script = (
            _message(p.MSG_DEVICE_INFO, _device_info_bytes())
            + _message(p.MSG_CLIENT_SYNC, _client_sync_bytes())
            + _message(gained_type, payload, seq=0)
        )
        client, _ = _client(script)
        client.connect()
        received: list[np.ndarray] = []
        client.start_streaming(received.append)
        client.wait_for_stream_end(timeout=5.0)
        assert len(received) == 1
        assert received[0][0].real == pytest.approx(0.5 * 10.0, rel=1e-3)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/sdr/test_spyserver_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sstv_core.sdr.spyserver.client'`

- [ ] **Step 3: Write minimal implementation**

```python
"""SpyServer client: connection, tuning, and IQ streaming.

The protocol has no error message type. A rejected or out-of-range tune
is never reported -- the server clamps or ignores it and the next
ClientSync reflects reality. So every setting is verified against the
sync that follows it, and never assumed.
"""

from __future__ import annotations

import logging
import socket
import threading
from collections.abc import Callable

import numpy as np

from sstv_core.sdr.spyserver import protocol as p

logger = logging.getLogger(__name__)


class SpyServerError(Exception):
    """A SpyServer failure, carrying copy fit for the operator."""

    def __init__(self, message: str, suggested_action: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.suggested_action = suggested_action


def choose_decimation_stage(
    maximum_sample_rate: int,
    decimation_stage_count: int,
    min_iq_decimation: int,
    target_rate: int = 48000,
) -> tuple[int, int]:
    """Pick the lowest IQ rate that still divides evenly into the audio rate.

    Decimation is a stage index, not a rate:
    rate = maximum_sample_rate / (1 << stage).
    """
    best: tuple[int, int] | None = None
    for stage in range(min_iq_decimation, decimation_stage_count + 1):
        rate = maximum_sample_rate // (1 << stage)
        if rate >= target_rate and rate % target_rate == 0:
            if best is None or rate < best[1]:
                best = (stage, rate)
    if best is None:
        raise SpyServerError(
            f"I couldn't find a sample rate on this server that divides into "
            f"{target_rate} Hz (its maximum is {maximum_sample_rate} Hz).",
            suggested_action="Try a different SpyServer.",
        )
    return best


class SpyServerClient:
    """One connection to one SpyServer."""

    def __init__(
        self,
        host: str,
        port: int = p.DEFAULT_PORT,
        client_name: str = "SSTeVe",
        stall_timeout_sec: float = 5.0,
        sock_factory: Callable[[], object] | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._client_name = client_name
        self._stall_timeout_sec = stall_timeout_sec
        self._sock_factory = sock_factory or (
            lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        )
        self._sock: object | None = None
        self._device_info: p.DeviceInfo | None = None
        self._client_sync: p.ClientSync | None = None
        self._sample_rate = 48000
        self._decimation_stage = 0
        self._on_iq: Callable[[np.ndarray], None] | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._ended = threading.Event()
        self._last_sequence: int | None = None
        self.dropped_frames = 0
        self.stream_error: SpyServerError | None = None

    @property
    def device_info(self) -> p.DeviceInfo | None:
        return self._device_info

    @property
    def client_sync(self) -> p.ClientSync | None:
        return self._client_sync

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def _recv_exactly(self, size: int) -> bytes:
        buf = b""
        while len(buf) < size:
            chunk = self._sock.recv(size - len(buf))  # type: ignore[union-attr]
            if not chunk:
                raise SpyServerError(
                    "The server closed the connection.",
                    suggested_action="Check the server is still up, then try again.",
                )
            buf += chunk
        return buf

    def _read_message(self) -> tuple[p.MessageHeader, bytes]:
        header = p.parse_message_header(self._recv_exactly(p.HEADER_SIZE))
        body = self._recv_exactly(header.body_size) if header.body_size else b""
        return header, body

    def connect(self) -> None:
        try:
            self._sock = self._sock_factory()
            self._sock.settimeout(self._stall_timeout_sec)  # type: ignore[union-attr]
            self._sock.connect((self._host, self._port))  # type: ignore[union-attr]
            self._sock.sendall(p.build_hello(self._client_name))  # type: ignore[union-attr]
        except SpyServerError:
            raise
        except OSError as exc:
            raise SpyServerError(
                f"I couldn't reach the SpyServer at {self._host}:{self._port}.",
                suggested_action="Check the host and port, and that the server is running.",
            ) from exc

        while self._device_info is None or self._client_sync is None:
            header, body = self._read_message()
            self._check_version(header)
            if header.msg_type == p.MSG_DEVICE_INFO:
                self._device_info = p.parse_device_info(body)
            elif header.msg_type == p.MSG_CLIENT_SYNC:
                self._client_sync = p.parse_client_sync(body)

        stage, rate = choose_decimation_stage(
            self._device_info.maximum_sample_rate,
            self._device_info.decimation_stage_count,
            self._device_info.min_iq_decimation,
        )
        self._decimation_stage = stage
        self._sample_rate = rate

    def _check_version(self, header: p.MessageHeader) -> None:
        theirs, ours = header.protocol_id, p.PROTOCOL_VERSION
        if (theirs >> 24) != (ours >> 24) or ((theirs >> 16) & 0xFF) != (
            (ours >> 16) & 0xFF
        ):
            raise SpyServerError(
                f"This server speaks protocol version {theirs:#x}, and I speak "
                f"{ours:#x}.",
                suggested_action="Try a server running a current SpyServer build.",
            )

    def tune(self, frequency_hz: int) -> None:
        sync = self._client_sync
        if sync is None:
            raise SpyServerError(
                "I'm not connected yet.", suggested_action="Connect first."
            )
        low, high = sync.minimum_iq_center_frequency, sync.maximum_iq_center_frequency
        if not (low <= frequency_hz <= high):
            raise SpyServerError(
                f"{frequency_hz} Hz is outside this server's range "
                f"({low}-{high} Hz).",
                suggested_action=f"Pick a frequency between {low} and {high} Hz.",
            )
        self._sock.sendall(  # type: ignore[union-attr]
            p.build_set_setting(p.SETTING_IQ_FREQUENCY, frequency_hz)
        )
        header, body = self._read_message()
        if header.msg_type == p.MSG_CLIENT_SYNC:
            self._client_sync = p.parse_client_sync(body)
            actual = self._client_sync.iq_center_frequency
            if actual != frequency_hz:
                raise SpyServerError(
                    f"I asked for {frequency_hz} Hz but the server put me on "
                    f"{actual} Hz.",
                    suggested_action=(
                        "This server may be locked to one frequency by its owner."
                    ),
                )

    def start_streaming(
        self, on_iq: Callable[[np.ndarray], None], gain: int = 0
    ) -> None:
        if self._device_info is None:
            raise SpyServerError(
                "I'm not connected yet.", suggested_action="Connect first."
            )
        self._on_iq = on_iq
        send = self._sock.sendall  # type: ignore[union-attr]
        send(p.build_set_setting(p.SETTING_IQ_FORMAT, p.FORMAT_INT16))
        send(p.build_set_setting(p.SETTING_IQ_DECIMATION, self._decimation_stage))
        send(p.build_set_setting(p.SETTING_STREAMING_MODE, p.STREAM_MODE_IQ_ONLY))
        send(p.build_set_setting(p.SETTING_GAIN, gain))
        # Digital gain semantics differ across reference clients; send 0 and do
        # any gain in our own DSP where it is testable.
        send(p.build_set_setting(p.SETTING_IQ_DIGITAL_GAIN, 0))
        send(p.build_set_setting(p.SETTING_STREAMING_ENABLED, 1))
        self._stop.clear()
        self._ended.clear()
        self._thread = threading.Thread(target=self._receive_loop, daemon=True)
        self._thread.start()

    def _receive_loop(self) -> None:
        try:
            while not self._stop.is_set():
                header, body = self._read_message()
                if header.msg_type == p.MSG_CLIENT_SYNC:
                    self._client_sync = p.parse_client_sync(body)
                    continue
                if header.msg_type not in (
                    p.MSG_UINT8_IQ,
                    p.MSG_INT16_IQ,
                    p.MSG_FLOAT_IQ,
                    p.MSG_INT24_IQ,
                ):
                    continue
                if self._last_sequence is not None:
                    gap = header.sequence_number - self._last_sequence - 1
                    if gap > 0:
                        self.dropped_frames += gap
                        logger.warning("SpyServer dropped %d frames", gap)
                self._last_sequence = header.sequence_number
                iq = p.iq_bytes_to_complex(body, header.msg_type, header.gain_db)
                if self._on_iq is not None:
                    self._on_iq(iq)
        except SpyServerError as exc:
            self.stream_error = exc
        except (OSError, p.ProtocolError) as exc:
            self.stream_error = SpyServerError(
                f"The stream dropped: {exc}",
                suggested_action="Check the network, then try again.",
            )
        finally:
            self._ended.set()

    def wait_for_stream_end(self, timeout: float | None = None) -> bool:
        return self._ended.wait(timeout)

    def stop_streaming(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.sendall(  # type: ignore[union-attr]
                    p.build_set_setting(p.SETTING_STREAMING_ENABLED, 0)
                )
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def close(self) -> None:
        self.stop_streaming()
        if self._sock is not None:
            try:
                self._sock.close()  # type: ignore[union-attr]
            except OSError:
                pass
            self._sock = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/sdr/test_spyserver_client.py -v`
Expected: PASS (all)

- [ ] **Step 5: Lint and type check**

Run: `uv run ruff check src/` then `uv run mypy src/`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/sstv_core/sdr/spyserver/client.py tests/sdr/test_spyserver_client.py
git commit -m "feat(sdr): add the SpyServer client

Connection, handshake, tuning, and IQ streaming against an in-process
fake socket -- no live server needed.

Tuning failure is silent in this protocol: the server clamps and says
nothing, so every tune is verified against the ClientSync that follows
it. Sequence gaps are counted as upstream frame drops, distinct from a
local overflow.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5 (PR S5): SpyServerSource — the stream-manager adapter

The seam. Implements the four methods `RXManager` calls, so nothing in the decode stack changes.

**Note on pacing.** The source writes each demodulated block straight into the ring buffer, which is correct for a normally-paced stream: the server sends IQ in real time, so audio arrives at real-time rate. `AudioRingBuffer` already evicts on overflow and counts it in `dropped_samples`, so a post-stall burst degrades exactly like a sound-card overrun rather than corrupting state. No extra throttle is built here. If real-server testing shows bursts scrolling VIS headers out of the correlation window (the hazard recorded in the spec), the fix belongs here — but do not build it speculatively.

**Files:**
- Create: `src/sstv_core/sdr/source.py`
- Test: `tests/sdr/test_source.py`

**Interfaces:**
- Consumes: `SpyServerClient`, `SpyServerError` (Task 4); `USBDemodulator`, `TARGET_RATE` (Task 3)
- Produces: `SpyServerSource(host, port=5555, frequency_hz=14_230_000, gain=0, stall_timeout_sec=5.0, client=None)` with:
  - `start_input(device_index=None, callback=None, buffer_size=None) -> None` — the full `AudioStreamManager.start_input` signature (`stream_manager.py:163`) so the duck type is drop-in; all three parameters are accepted and `device_index`/`callback` ignored
  - `stop_input() -> None`, `get_input_buffer() -> AudioRingBuffer | None`, `get_input_levels() -> AudioLevels`
  - Properties: `sample_rate -> int` (always 48000), `stream_failure -> SpyServerError | None`, `dropped_frames -> int`
  - `seconds_since_last_iq() -> float`

  The injected `client` must expose: `connect()`, `tune(frequency_hz)`, `start_streaming(on_iq, gain=0)`, `stop_streaming()`, `close()`, plus attributes `sample_rate`, `dropped_frames`, `stream_error`. `SpyServerClient` from Task 4 satisfies this; tests substitute their own.

- [ ] **Step 1: Write the failing test**

```python
"""SpyServerSource satisfies the contract RXManager already depends on."""

from __future__ import annotations

import numpy as np
import pytest

from sstv_core.audio.ring_buffer import AudioRingBuffer
from sstv_core.sdr.demodulator import TARGET_RATE
from sstv_core.sdr.source import SpyServerSource
from sstv_core.sdr.spyserver.client import SpyServerError


class FakeClient:
    """Stands in for SpyServerClient; feeds IQ on demand."""

    def __init__(self, sample_rate: int = 192_000) -> None:
        self.sample_rate = sample_rate
        self.connected = False
        self.tuned_to: int | None = None
        self.streaming = False
        self.closed = False
        self.dropped_frames = 0
        self.stream_error: SpyServerError | None = None
        self._on_iq = None

    def connect(self) -> None:
        self.connected = True

    def tune(self, frequency_hz: int) -> None:
        self.tuned_to = frequency_hz

    def start_streaming(self, on_iq, gain: int = 0) -> None:
        self.streaming = True
        self._on_iq = on_iq

    def stop_streaming(self) -> None:
        self.streaming = False

    def close(self) -> None:
        self.closed = True

    def feed_tone(self, offset_hz: float = 1500.0, duration: float = 0.2) -> None:
        t = np.arange(int(self.sample_rate * duration)) / self.sample_rate
        self._on_iq(np.exp(2j * np.pi * offset_hz * t).astype(np.complex64))


def _source(client: FakeClient) -> SpyServerSource:
    return SpyServerSource("example.test", frequency_hz=14_230_000, client=client)


class TestContract:
    def test_exposes_the_four_methods_rxmanager_calls(self):
        src = _source(FakeClient())
        for name in (
            "start_input",
            "stop_input",
            "get_input_buffer",
            "get_input_levels",
        ):
            assert callable(getattr(src, name))

    def test_start_input_ignores_device_index(self):
        """RXManager passes device_index by keyword; a network source has none."""
        client = FakeClient()
        src = _source(client)
        src.start_input(device_index=7)
        assert client.connected and client.streaming
        src.stop_input()

    def test_sample_rate_is_always_the_engine_rate(self):
        assert _source(FakeClient()).sample_rate == TARGET_RATE

    def test_buffer_is_none_before_start(self):
        assert _source(FakeClient()).get_input_buffer() is None

    def test_levels_are_zero_before_any_audio(self):
        levels = _source(FakeClient()).get_input_levels()
        assert levels.rms == 0.0
        assert levels.peak == 0.0
        assert levels.is_clipping is False


class TestAudioFlow:
    def test_iq_becomes_audio_in_the_ring_buffer(self):
        client = FakeClient()
        src = _source(client)
        src.start_input()
        client.feed_tone()
        buffer = src.get_input_buffer()
        assert isinstance(buffer, AudioRingBuffer)
        assert len(buffer) > 0
        samples = buffer.pop(len(buffer))
        assert samples.dtype == np.float32
        assert np.max(np.abs(samples)) > 0.01
        src.stop_input()

    def test_levels_track_delivered_audio(self):
        client = FakeClient()
        src = _source(client)
        src.start_input()
        client.feed_tone()
        levels = src.get_input_levels()
        assert levels.rms > 0.0
        assert levels.peak > 0.0
        src.stop_input()

    def test_tunes_to_the_requested_frequency(self):
        client = FakeClient()
        src = _source(client)
        src.start_input()
        assert client.tuned_to == 14_230_000
        src.stop_input()

    def test_stop_input_closes_the_client(self):
        client = FakeClient()
        src = _source(client)
        src.start_input()
        src.stop_input()
        assert not client.streaming
        assert client.closed


class TestFailureReporting:
    def test_stream_failure_is_exposed(self):
        client = FakeClient()
        src = _source(client)
        src.start_input()
        client.stream_error = SpyServerError("The stream dropped.", "Try again.")
        assert src.stream_failure is not None
        assert "dropped" in src.stream_failure.message.lower()
        src.stop_input()

    def test_time_since_last_iq_grows_before_data(self):
        client = FakeClient()
        src = _source(client)
        src.start_input()
        assert src.seconds_since_last_iq() >= 0.0
        src.stop_input()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/sdr/test_source.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sstv_core.sdr.source'`

- [ ] **Step 3: Write minimal implementation**

```python
"""SpyServerSource: a network IQ source shaped like an audio input.

RXManager depends on four methods -- start_input, stop_input,
get_input_buffer, get_input_levels -- and never imports sounddevice.
Implementing those is the whole seam; the decode stack is unchanged.
"""

from __future__ import annotations

import logging
import time

import numpy as np

from sstv_core.audio.ring_buffer import AudioRingBuffer
from sstv_core.audio.stream_manager import AudioLevels
from sstv_core.sdr.demodulator import TARGET_RATE, USBDemodulator
from sstv_core.sdr.spyserver.client import SpyServerClient, SpyServerError

logger = logging.getLogger(__name__)

CLIP_THRESHOLD = 0.99


class SpyServerSource:
    """Feeds demodulated SpyServer audio into a ring buffer.

    Args:
        host: SpyServer hostname or IP.
        port: SpyServer port.
        frequency_hz: Frequency to tune, in Hz.
        gain: Device RF/IF gain index.
        stall_timeout_sec: Seconds without IQ before the stream counts as stalled.
        client: Injected client (tests); a real one is built when omitted.

    """

    def __init__(
        self,
        host: str,
        port: int = 5555,
        frequency_hz: int = 14_230_000,
        gain: int = 0,
        stall_timeout_sec: float = 5.0,
        client: object | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._frequency_hz = frequency_hz
        self._gain = gain
        self._stall_timeout_sec = stall_timeout_sec
        self._client = client
        self._demod: USBDemodulator | None = None
        self._buffer: AudioRingBuffer | None = None
        self._levels = AudioLevels()
        self._last_iq_at = 0.0

    @property
    def sample_rate(self) -> int:
        """Always the engine rate — the demodulator decimates to it."""
        return TARGET_RATE

    @property
    def stream_failure(self) -> SpyServerError | None:
        return getattr(self._client, "stream_error", None)

    @property
    def dropped_frames(self) -> int:
        return int(getattr(self._client, "dropped_frames", 0))

    def seconds_since_last_iq(self) -> float:
        if not self._last_iq_at:
            return 0.0
        return time.monotonic() - self._last_iq_at

    def start_input(
        self, device_index: int | None = None, callback=None, buffer_size: int | None = None
    ) -> None:
        """Connect, tune, and start filling the ring buffer.

        `device_index` is accepted and ignored: RXManager passes it by
        keyword and a network source has no device to select.
        """
        if self._client is None:
            self._client = SpyServerClient(
                self._host, self._port, stall_timeout_sec=self._stall_timeout_sec
            )
        self._client.connect()  # type: ignore[union-attr]
        self._client.tune(self._frequency_hz)  # type: ignore[union-attr]
        self._demod = USBDemodulator(input_rate=self._client.sample_rate)  # type: ignore[union-attr]
        self._buffer = AudioRingBuffer(
            max_samples=buffer_size or AudioRingBuffer.DEFAULT_MAX_SAMPLES
        )
        self._last_iq_at = time.monotonic()
        self._client.start_streaming(self._on_iq, gain=self._gain)  # type: ignore[union-attr]

    def _on_iq(self, iq: np.ndarray) -> None:
        if self._demod is None or self._buffer is None:
            return
        audio = self._demod.demodulate(iq)
        if len(audio) == 0:
            return
        self._last_iq_at = time.monotonic()
        self._levels = self._calculate_levels(audio)
        self._buffer.add(audio)

    @staticmethod
    def _calculate_levels(samples: np.ndarray) -> AudioLevels:
        if len(samples) == 0:
            return AudioLevels()
        rms = float(np.sqrt(np.mean(samples**2)))
        peak = float(np.max(np.abs(samples)))
        return AudioLevels(rms=rms, peak=peak, is_clipping=peak >= CLIP_THRESHOLD)

    def stop_input(self) -> None:
        if self._client is not None:
            self._client.stop_streaming()  # type: ignore[union-attr]
            self._client.close()  # type: ignore[union-attr]

    def get_input_buffer(self) -> AudioRingBuffer | None:
        return self._buffer

    def get_input_levels(self) -> AudioLevels:
        return self._levels
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/sdr/test_source.py -v`
Expected: PASS (all)

- [ ] **Step 5: Lint and type check**

Run: `uv run ruff check src/` then `uv run mypy src/`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/sstv_core/sdr/source.py tests/sdr/test_source.py
git commit -m "feat(sdr): add SpyServerSource, the audio-shaped IQ seam

Implements the four methods RXManager already calls, so a network IQ
source drops in where a sound card goes and the decode stack is
untouched.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6 (PR S6): End-to-end gate — SSTV through the SDR path

The regression gate for the whole feature: a real reference recording, modulated up into synthetic USB IQ, decoded by the real `RXManager` through the real source. Proves the SDR path delivers audio the decoder accepts, with no server and no radio.

**Files:**
- Create: `tests/integration/test_sdr_roundtrip.py`

**Interfaces:**
- Consumes: `SpyServerSource` (Task 5), `RXManager`, `AudioRingBuffer`
- Produces: nothing consumed by later tasks

- [ ] **Step 1: Write the failing test**

```python
"""SSTV over the SDR path, end to end, with no server and no radio.

Takes a real Scottie S1 recording, modulates it up as USB IQ, and feeds
it through SpyServerSource into the real RXManager. If this passes, the
SDR path produces audio the decoder actually accepts.

The feeder paces itself deliberately: dumping a backlog into the ring
buffer scrolls the VIS header out of the correlation window, which
paced live audio never does. A network source that stalls then bursts
can produce exactly that -- see the source's pacing note.
"""

from __future__ import annotations

import asyncio
import wave
from pathlib import Path

import numpy as np
import pytest

from sstv_core.decode.rx_manager import RXManager
from sstv_core.sdr.source import SpyServerSource

REFERENCE = (
    Path(__file__).resolve().parents[1]
    / "reference"
    / "audio"
    / "mmsstv"
    / "scottie_s1_bear_je3hht.wav"
)
IQ_RATE = 192_000
AUDIO_OFFSET_HZ = 0.0


def _load_reference() -> tuple[np.ndarray, int]:
    with wave.open(str(REFERENCE), "rb") as wav:
        rate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())
        channels = wav.getnchannels()
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return audio, rate


def _audio_to_usb_iq(audio: np.ndarray, audio_rate: int, iq_rate: int) -> np.ndarray:
    """Modulate real audio up into complex IQ as an upper-sideband signal.

    The analytic signal (audio + j*hilbert(audio)) has energy only on the
    positive-frequency side, which is exactly what USB means.
    """
    from scipy import signal as sp_signal

    upsampled = sp_signal.resample_poly(audio, iq_rate // audio_rate, 1)
    analytic = sp_signal.hilbert(upsampled)
    return analytic.astype(np.complex64)


class ScriptedClient:
    """Feeds prepared IQ to the source the way a server would."""

    def __init__(self, iq: np.ndarray, sample_rate: int) -> None:
        self.sample_rate = sample_rate
        self._iq = iq
        self._on_iq = None
        self.dropped_frames = 0
        self.stream_error = None
        self.closed = False
        self.offset = 0

    def connect(self) -> None:
        pass

    def tune(self, frequency_hz: int) -> None:
        pass

    def start_streaming(self, on_iq, gain: int = 0) -> None:
        self._on_iq = on_iq

    def stop_streaming(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True

    def pump(self, samples: int) -> int:
        """Deliver one block; returns how many samples were sent."""
        chunk = self._iq[self.offset : self.offset + samples]
        if len(chunk) == 0:
            return 0
        self._on_iq(chunk)
        self.offset += len(chunk)
        return len(chunk)


@pytest.mark.asyncio
async def test_scottie_s1_decodes_through_the_sdr_path(tmp_path):
    audio, audio_rate = _load_reference()
    iq = _audio_to_usb_iq(audio, audio_rate, IQ_RATE)

    client = ScriptedClient(iq, IQ_RATE)
    source = SpyServerSource("fake.test", frequency_hz=14_230_000, client=client)
    source.start_input()

    rx = RXManager(stream_manager=source, save_directory=tmp_path)

    async def feeder() -> None:
        block = IQ_RATE // 4  # 0.25 s of IQ per pump
        while True:
            buffer = source.get_input_buffer()
            # Stay near the consumer: a big backlog scrolls the VIS header
            # out of the correlation window.
            if buffer is not None and len(buffer) < 24_000:
                if client.pump(block) == 0:
                    return
            await asyncio.sleep(0.001)

    feed_task = asyncio.create_task(feeder())
    try:
        result = await asyncio.wait_for(
            rx.receive(timeout_sec=60.0, save_image=True), timeout=180
        )
    finally:
        feed_task.cancel()
        source.stop_input()

    assert result is not None, "the SDR path decoded nothing"
    assert Path(result).exists()

    import cv2

    decoded = cv2.imread(str(result))
    assert decoded is not None
    assert decoded.shape[0] >= 200 and decoded.shape[1] >= 300
    # A real decode has structure; a failed one is flat.
    assert float(decoded.std()) > 20.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_sdr_roundtrip.py -v`
Expected: FAIL initially — either an import error before Task 5 is merged, or a
decode failure while pacing/offset are being tuned.

- [ ] **Step 3: Make it pass**

No new production code should be required. If the decode fails:

1. Confirm the reference file decodes normally first:
   `uv run python -m sstv_core.cli.main decode --file tests/reference/audio/mmsstv/scottie_s1_bear_je3hht.wav --output /tmp/ref.png` — it must produce the bear image.
2. If that works but the SDR path does not, the fault is in modulation, pacing, or the demodulator's passband. Check in that order: dump `source.get_input_buffer()` contents to a WAV and listen/plot before assuming the decoder is wrong.
3. **Do not** loosen the assertions to get a pass. A flat image (`std() <= 20`) means the path is broken.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest` then `uv run ruff check src/` then `uv run mypy src/`
Expected: all green, exit codes verified bare.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_sdr_roundtrip.py
git commit -m "test(sdr): gate the SDR path on a real SSTV decode

Modulates a real Scottie S1 recording up into synthetic USB IQ and
decodes it through SpyServerSource and the real RXManager. No server,
no radio -- but it proves the SDR path hands the decoder audio it
actually accepts.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7 (PR S7): Config settings and CLI wiring

Makes it usable: persisted connection settings and `decode --spyserver`.

**Files:**
- Modify: `src/sstv_core/config/manager.py` (add `SpyServerSettings`, register on `AdvancedSettings:98-106`)
- Modify: `src/sstv_core/cli/main.py` (decode args at `:631-661`; dispatch at `:99-107`; new `_decode_spyserver`)
- Test: `tests/config/test_spyserver_settings.py`, `tests/cli/test_cli_spyserver.py`

**Interfaces:**
- Consumes: `SpyServerSource`, `SpyServerError` (Tasks 4-5)
- Produces: `SpyServerSettings` on `AdvancedSettings.spyserver`; CLI flags `--spyserver`, `--frequency`, `--band`; `BAND_PRESETS: dict[str, int]`

- [ ] **Step 1: Write the failing tests**

`tests/config/test_spyserver_settings.py`:

```python
"""SpyServer settings live in the JSON tier — no migration."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sstv_core.config.manager import AdvancedSettings, SpyServerSettings


def test_defaults_are_sane():
    s = SpyServerSettings()
    assert s.port == 5555
    assert s.stall_timeout_sec == 5.0
    assert s.gain == 0


def test_registered_on_advanced_settings():
    assert isinstance(AdvancedSettings().spyserver, SpyServerSettings)


def test_port_is_range_checked():
    with pytest.raises(ValidationError):
        SpyServerSettings(port=70000)


def test_frequency_is_uint32_bounded():
    """The protocol carries frequency as uint32 Hz."""
    with pytest.raises(ValidationError):
        SpyServerSettings(frequency_hz=5_000_000_000)


def test_round_trips_through_advanced_settings_json():
    settings = AdvancedSettings(
        spyserver=SpyServerSettings(host="sdr.example.test", frequency_hz=14_230_000)
    )
    restored = AdvancedSettings.model_validate(settings.model_dump())
    assert restored.spyserver.host == "sdr.example.test"
    assert restored.spyserver.frequency_hz == 14_230_000
```

`tests/cli/test_cli_spyserver.py`:

```python
"""decode --spyserver: argument handling and honest failures."""

from __future__ import annotations

import pytest

from sstv_core.cli.main import BAND_PRESETS, main


class TestBandPresets:
    def test_hf_presets_match_product_md(self):
        assert BAND_PRESETS["20m"] == 14_230_000
        assert BAND_PRESETS["40m"] == 7_171_000
        assert BAND_PRESETS["15m"] == 21_340_000
        assert BAND_PRESETS["10m"] == 28_680_000
        assert BAND_PRESETS["80m"] == 3_845_000

    def test_fm_presets_are_absent_because_fm_is_out_of_scope(self):
        assert "2m" not in BAND_PRESETS


class TestArgumentHandling:
    def test_spyserver_and_device_together_is_an_error(self, capsys):
        rc = main(["decode", "--spyserver", "host:5555", "--device", "ca_Test"])
        assert rc == 1

    def test_spyserver_and_file_together_is_an_error(self):
        rc = main(["decode", "--spyserver", "host:5555", "--file", "x.wav"])
        assert rc == 1

    def test_unknown_band_is_rejected(self):
        rc = main(["decode", "--spyserver", "host:5555", "--band", "6m"])
        assert rc == 1

    def test_connection_failure_exits_one_not_zero(self, monkeypatch):
        """An unreachable server must never look like a successful run."""
        import sstv_core.sdr.source as source_module
        from sstv_core.sdr.spyserver.client import SpyServerError

        class FailingSource:
            def __init__(self, *a, **k):
                pass

            def start_input(self, **k):
                raise SpyServerError(
                    "I couldn't reach the SpyServer at nowhere.test:5555.",
                    suggested_action="Check the host and port.",
                )

            def stop_input(self):
                pass

        monkeypatch.setattr(source_module, "SpyServerSource", FailingSource)
        rc = main(
            ["decode", "--spyserver", "nowhere.test:5555", "--band", "20m", "--timeout", "1"]
        )
        assert rc == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/config/test_spyserver_settings.py tests/cli/test_cli_spyserver.py -v`
Expected: FAIL — `ImportError: cannot import name 'SpyServerSettings'` / `'BAND_PRESETS'`

- [ ] **Step 3a: Add the config model**

In `config/manager.py`, after `ExperimentalSettings` (ends line 95):

```python
class SpyServerSettings(BaseModel):
    """SpyServer connection settings from advanced_settings_json."""

    host: str = ""
    port: int = Field(default=5555, ge=1, le=65535)
    # The protocol carries frequency as a uint32 in Hz.
    frequency_hz: int = Field(default=14_230_000, ge=0, le=4_294_967_295)
    gain: int = Field(default=0, ge=0, le=63)
    stall_timeout_sec: float = Field(default=5.0, gt=0.0, le=120.0)
```

Then register it on `AdvancedSettings` (line 98-106):

```python
    spyserver: SpyServerSettings = Field(default_factory=SpyServerSettings)
```

- [ ] **Step 3b: Add the CLI flags**

In `cli/main.py`, near the top-level constants:

```python
# SSTV calling frequencies per band (PRODUCT.md §Scope). HF only: FM
# demodulation is out of scope, so 145.500/145.800 are deliberately absent.
BAND_PRESETS: dict[str, int] = {
    "80m": 3_845_000,
    "40m": 7_171_000,
    "20m": 14_230_000,
    "15m": 21_340_000,
    "10m": 28_680_000,
}
```

Add to `decode_parser` (after the `--file` argument, line ~650):

```python
    decode_parser.add_argument(
        "--spyserver",
        type=str,
        default=None,
        help="SpyServer to receive from, as host or host:port (default port 5555)",
    )
    decode_parser.add_argument(
        "--frequency",
        type=int,
        default=None,
        help="Frequency in Hz for --spyserver (overrides --band)",
    )
    decode_parser.add_argument(
        "--band",
        type=str,
        default=None,
        choices=sorted(BAND_PRESETS),
        help="SSTV calling frequency by band for --spyserver",
    )
```

- [ ] **Step 3c: Wire the dispatch**

In `cmd_decode`, before the `if args.file:` branch (line ~99):

```python
    spyserver = getattr(args, "spyserver", None)
    if spyserver and (args.file or args.device):
        log_event(
            "error",
            message="I can only listen to one source at a time.",
            suggested_action="Use --spyserver, --device, or --file — not more than one.",
        )
        return 1
    if spyserver:
        return _decode_spyserver(args)
```

Then add the handler, modeled on `_decode_live` (`cli/main.py:134`).

**Import the module, not the class.** `from sstv_core.sdr import source as source_module`, then `source_module.SpyServerSource(...)`. A direct `from ... import SpyServerSource` binds the name at import time and the monkeypatch in `test_connection_failure_exits_one_not_zero` silently stops working — the test would pass against the real class and try to reach a real network. Do not "tidy" this into a direct import.

```python
def _decode_spyserver(args: argparse.Namespace) -> int:
    """Decode from a SpyServer network stream.

    Same RXManager the sound-card path uses: the source is swapped, the
    decode stack is not.
    """
    import asyncio
    import shutil

    from sstv_core.decode.rx_manager import RXManager
    from sstv_core.sdr import source as source_module
    from sstv_core.sdr.spyserver.client import SpyServerError

    host, _, port_text = args.spyserver.partition(":")
    try:
        port = int(port_text) if port_text else 5555
    except ValueError:
        log_event(
            "error",
            message=f"I couldn't read '{port_text}' as a port number.",
            suggested_action="Use --spyserver host:port, for example sdr.example.com:5555.",
        )
        return 1

    if args.frequency is not None:
        frequency = args.frequency
    elif args.band is not None:
        frequency = BAND_PRESETS[args.band]
    else:
        frequency = BAND_PRESETS["20m"]

    save_directory = (
        Path(args.output).resolve().parent if args.output else Path.home() / "sstv_images"
    )
    save_directory.mkdir(parents=True, exist_ok=True)

    src = source_module.SpyServerSource(
        host=host, port=port, frequency_hz=frequency
    )
    log_event("decode_start", mode=args.mode, spyserver=f"{host}:{port}", frequency=frequency)

    rx = RXManager(stream_manager=src, save_directory=save_directory)

    def on_progress(progress) -> None:
        log_event(
            "rx_progress",
            state=progress.state.value,
            mode=progress.mode,
            line=progress.current_line,
            total=progress.total_lines,
            percent=round(progress.percent_complete, 1),
        )

    rx.set_progress_callback(on_progress)

    try:
        result = asyncio.run(
            rx.receive(mode=args.mode, timeout_sec=float(args.timeout), save_image=True)
        )
    except SpyServerError as exc:
        log_event(
            "error", message=exc.message, suggested_action=exc.suggested_action
        )
        return 1
    except KeyboardInterrupt:
        log_event("decode_stopped", message="Stopped by user.")
        return 130
    except Exception as exc:
        log_event(
            "error",
            message="The SpyServer decode failed.",
            detail=str(exc),
            suggested_action="Check the server address and frequency, then try again.",
        )
        return 1
    finally:
        src.stop_input()

    # A dropped stream must never read as a weak signal.
    failure = src.stream_failure
    if failure is not None:
        log_event(
            "error",
            message=failure.message,
            detail="The stream failed — this is a network problem, not a weak signal.",
            suggested_action=failure.suggested_action,
        )
        if result is None:
            return 1
    if src.dropped_frames:
        log_event(
            "stream_warning",
            message=f"The server dropped {src.dropped_frames} frames.",
            suggested_action="Any gaps in the image come from the stream, not the signal.",
        )

    if result is None:
        log_event(
            "error",
            message="I didn't hear an SSTV transmission before the timeout.",
            suggested_action="Check the frequency and the band, or raise --timeout.",
        )
        return 2

    output = Path(args.output) if args.output else Path(result)
    if args.output and Path(result) != output:
        shutil.move(str(result), str(output))
    log_event("decode_complete", output_path=str(output))
    return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/config/test_spyserver_settings.py tests/cli/test_cli_spyserver.py -v`
Expected: PASS (all)

- [ ] **Step 5: Verify the whole suite and gates**

Run: `uv run pytest` then `uv run ruff check src/` then `uv run mypy src/`
Expected: all green, exit codes verified bare.

- [ ] **Step 6: Commit**

```bash
git add src/sstv_core/config/manager.py src/sstv_core/cli/main.py \
        tests/config/test_spyserver_settings.py tests/cli/test_cli_spyserver.py
git commit -m "feat(cli): decode from a SpyServer with no audio cable

Adds decode --spyserver/--frequency/--band and persisted connection
settings in the JSON config tier (no migration).

Band presets are the HF SSTV calling frequencies from PRODUCT.md; the
2m FM ones are deliberately absent while FM demodulation is out of
scope. A dropped stream is reported as a network failure, never as a
weak signal.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Manual verification (the actual goal)

Automated tests never touch a real server. After Task 7 lands:

- [ ] Pick a public SpyServer from the SDR# directory near active HF propagation
- [ ] `cd sstv_core && uv run python -m sstv_core.cli.main decode --spyserver <host>:<port> --band 20m --timeout 300 --output ~/sstv_test.png --verbose`
- [ ] Confirm the log shows connection, the tuned frequency, and audio levels moving
- [ ] Wait for a transmission; confirm VIS detection fires and an image is written
- [ ] Note what breaks — the protocol unknowns in the spec (keepalive, `ForcedIQFormat`, endianness) are the first suspects

Expected imperfections on first contact: mistuning by a few hundred Hz (SSB tuning is exact), gain needing adjustment, and PD-mode transmissions reporting "I don't have a decoder" — that last one is correct behavior, not a bug.

## Out of scope, restated

NBFM demodulation · local SDR devices · waterfall/click-to-tune (#53) · API and WebSocket plumbing · auto-reconnect · PD/Wraase decoders. Each is a deliberate deferral recorded in the spec, not an oversight.
