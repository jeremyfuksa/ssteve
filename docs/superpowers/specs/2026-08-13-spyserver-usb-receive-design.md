# SpyServer USB Receive Path — Design

**Status:** approved design, not yet implemented
**Issue:** #68 (EPIC: SDR/SpyServer input path), milestone "4: SDR epoch"
**Date:** 2026-08-13

**Goal:** Decode live SSTV from a SpyServer network stream with no virtual audio
cable anywhere in the flow. First real slice of the SDR epoch.

**Why now:** PRODUCT.md §Scope (decided 2026-08-07) makes native SDR v1 scope and
names the VB-Cable/BlackHole chain as "the single worst onboarding path in the
product." A loopback rig would work today but is the exact thing this feature
exists to delete, so it is not a stepping stone — it is the anti-goal.

## Scope

**In:**

- SpyServer client (connect, tune, stream IQ) over TCP
- USB demodulation: IQ → 48 kHz mono float32 audio
- An IQ-source seam so a local-device source can be added later without touching
  the demodulator ("two sources, one demodulator", PRODUCT.md)
- SpyServer settings in config (JSON advanced tier, no migration)
- CLI: `decode --spyserver`, `--frequency`, `--band`
- Stream-failure detection and honest reporting

**Out, and deliberately so:**

- **NBFM demodulation.** Only 145.500/145.800 need it, and the marquee FM target
  (ARISS) transmits PD120, which SSTeVe cannot decode (PD is post-MVP per
  PRODUCT.md). USB covers all five HF presets and every mode SSTeVe *can* decode.
  The demodulator interface leaves room for it.
- **Local SDR devices** (RTL-SDR etc.). The seam is built; the second
  implementation is not. No `soapysdr`/`rtlsdr` dependency in this round.
- **Waterfall / click-to-tune.** Needs #53 (spectrum FFT producer, milestone 2),
  which is unbuilt. Tuning here is blind, to preset calling frequencies. #68
  frames the RF waterfall as a *second producer* for #53's contract — it slots in
  later without rework.
- **API/WebSocket plumbing.** No `DSPManager`/REST changes; nothing consumes them
  until a UI exists. Config lives in the tier the API already exposes, so the
  later API round is additive.
- **Auto-reconnect.** A dropped connection ends the session with a clear message.
  Revisit once real-world drop frequency is known.
- **New SSTV modes.** PD/Wraase stay post-MVP. Live PD120 will report "no decoder"
  — expected, not a regression.

## Architecture

`RXManager` depends on exactly four methods of `AudioStreamManager` —
`start_input`, `stop_input`, `get_input_buffer`, `get_input_levels`
(`decode/rx_manager.py:300-301`, `:294`, `:762`) — and never imports
`sounddevice`. That four-method contract *is* the seam; it already exists as a
duck type with one implementation. Nothing in the decode stack changes.

```
SpyServer ──TCP──> client ──IQ blocks──> demodulator ──48kHz mono f32──> AudioRingBuffer
                                                                                │
                                              RXManager (unchanged) ◄───────────┘
```

The demodulator takes IQ and knows nothing about its origin, so the local-device
source added later shares it unmodified.

**Sample rate.** The demodulator always decimates to exactly 48 kHz, whatever the
server sends. The engine is 48 kHz end to end (`config/manager.py:61-62`), so
nothing downstream needs a rate change and `sample_rate_override` stays buried.

## Components

| Unit | Responsibility | Depends on |
|---|---|---|
| `sdr/spyserver/protocol.py` | Wire format: framing, commands, parsing. Pure bytes. | — |
| `sdr/spyserver/client.py` | Socket lifecycle, handshake, tuning, IQ callback, disconnect detection | protocol |
| `sdr/demodulator.py` | IQ → USB audio at 48 kHz. Pure numpy/scipy, no I/O. | numpy, scipy |
| `sdr/source.py` | `AudioStreamManager`-shaped adapter; fills the ring buffer | client, demodulator |

### `protocol.py`

Pure functions over bytes: build command messages, parse response headers and
payloads. No socket, no state. Testable exhaustively without a server, including
malformed input (truncated headers, impossible lengths, unknown message types).

**Wire format.** All fields are packed little-endian `uint32`. Verified
byte-identical across SDR++ (`spyserver_protocol.h`), `miweber67/spyserver_client`,
and `xritdemod`'s `SpyServerFrontend.cpp`.

```
Client→Server:  CommandHeader { u32 CommandType; u32 BodySize; } + body
Server→Client:  MessageHeader { u32 ProtocolID; u32 MessageType; u32 StreamType;
                                u32 SequenceNumber; u32 BodySize; } + body
```

Header sizes: CommandHeader 8 B, MessageHeader 20 B, DeviceInfo 48 B,
ClientSync 36 B. Default port **5555/TCP**.

| Group | Name | Value |
|---|---|---|
| Command | HELLO / SET_SETTING / PING | 0 / 2 / 3 |
| Setting | STREAMING_MODE / STREAMING_ENABLED / GAIN | 0 / 1 / 2 |
| Setting | IQ_FORMAT / IQ_FREQUENCY / IQ_DECIMATION / IQ_DIGITAL_GAIN | 100 / 101 / 102 / 103 |
| Msg | DEVICE_INFO / CLIENT_SYNC / PONG | 0 / 1 / 2 |
| Msg | UINT8_IQ / INT16_IQ / INT24_IQ / FLOAT_IQ | 100 / 101 / 102 / 103 |
| Stream mode | IQ_ONLY | 1 |
| Format | UINT8 / INT16 / FLOAT | 1 / 2 / 4 |
| Limits | MAX_MESSAGE_BODY_SIZE / MAX_COMMAND_BODY_SIZE | 1<<20 / 256 |

`SPYSERVER_PROTOCOL_VERSION = (2<<24)|(0<<16)|1700 = 0x020006A4`. Reject the
server unless **major and minor** match (build ignored).

**Handshake:** `CMD_HELLO(0)` with body = `u32 ProtocolVersion` + client name as
**raw bytes, not NUL-terminated, no length prefix** — `BodySize` alone delimits
it. Server replies `DEVICE_INFO` then `CLIENT_SYNC`.

**`SET_SETTING` body** = `u32 setting_id` + `u32 value`.

**Startup order** (the sequence proven to work in SDR++): `IQ_FORMAT` →
`IQ_DECIMATION` → `IQ_FREQUENCY` → `STREAMING_MODE(1)` → `GAIN` →
`IQ_DIGITAL_GAIN` → `STREAMING_ENABLED(1)`. Retune while running by resending
`IQ_FREQUENCY`. Stop with `STREAMING_ENABLED(0)`.

**Three trip-hazards, each a silent-wrongness bug if missed:**

1. **`MessageType` is a bitfield.** Low 16 bits = message type; **high 16 bits =
   digital gain in dB** applied by the server. Samples must be scaled by
   `10**(gain/20)`. Masking the high bits off (as one reference client does)
   silently mis-scales amplitude whenever the server applies gain — which would
   corrupt levels, squelch, and RSV with no visible cause.
2. **Decimation is a stage index, not a rate:**
   `sample_rate = MaximumSampleRate / (1 << stage)`, valid range
   `MinimumIQDecimation … DecimationStageCount` inclusive. Pick the stage whose
   resulting rate is the lowest that still comfortably exceeds SSB bandwidth,
   then decimate the rest of the way to 48 kHz in the demodulator.
3. **Frequency is `uint32` Hz** — no 64-bit variant exists, capping tuning near
   4.29 GHz. Irrelevant here: it comfortably covers HF and the 2m presets alike,
   so it is not a reason FM is out of scope.

**IQ formats:** interleaved I,Q (I first). UINT8 is offset binary,
`(v-128)/128`, samples = BodySize/2. INT16 is signed LE, `/32768`,
BodySize/4. **INT24 is not supported** — SDR++ explicitly refuses it. Request
**INT16** (better dynamic range than UINT8 for weak-signal HF work), but honor
`DeviceInfo.ForcedIQFormat` if the server pins one, and confirm the actual format
from the received `MessageType` rather than assuming.

**No compression.** The IQ stream is always raw — a grep for
`flac|zlib|compress|deflate|lz4|gzip` across both reference repos returns zero
hits. (FLAC-compressed IQ belongs to the unrelated KiwiSDR/OpenWebRX ecosystem.)
`socket` + `struct` + `numpy` is the entire dependency surface; **no new
third-party packages.**

**Sequence numbers** increment per IQ message; a gap means frames were lost
upstream (server or network) — distinct from a local overflow and from a stall.
(FFT messages always carry sequence 0, but this design never requests FFT.)

**Gain.** `SETTING_GAIN` is the device's RF/IF gain and is what the operator's
`gain` config value maps to. `SETTING_IQ_DIGITAL_GAIN` is a separate server-side
digital multiplier whose semantics differ across reference clients (SDR++ computes
a device-specific value; `spyserver_client` hardcodes 0 and calls its own support
unsupported). **Send `IQ_DIGITAL_GAIN` as 0** and do any further gain in our own
DSP, where it is testable. This is independent of the gain-in-high-bits scaling in
hazard 1, which must always be applied regardless.

### `client.py`

Owns the socket and a receive thread. Connects, negotiates, tunes, and hands IQ
blocks to a callback. Disconnect detection lives here: closed socket, short read,
or no data past the stall timeout each become a typed `SpyServerError` rather
than silence. Raises with enough detail for the error voice.

**`ClientSync` is the source of truth, and tuning failure is silent.** The
protocol has **no error message type**. A rejected or out-of-range tune is not
reported — the server clamps or ignores the request and the next `ClientSync`
reflects the actual state. So the client must:

- Treat every `ClientSync` as authoritative state, never assume a `SET_SETTING`
  took effect
- After tuning, **compare** the reported frequency against what was requested and
  surface a mismatch explicitly
- Honor `CanControl`: when 0 the device is server-locked and shared, and tuning is
  only legal within `[MinimumIQCenterFrequency, MaximumIQCenterFrequency]`.
  Pre-check that range client-side and refuse out-of-range requests with a clear
  message rather than sending a command that will be silently ignored.

This matters directly for blind tuning: without the comparison, asking for 14.230
on a server locked elsewhere yields a confident-looking session listening to the
wrong frequency, which is indistinguishable from a dead band.

### `demodulator.py`

USB demodulation as a pure function of an IQ array:

1. Frequency-shift so the target sits at baseband
2. Filter to SSB bandwidth (~2.4 kHz)
3. Take the real part (discarding the image sideband — this is what makes it USB
   rather than DSB)
4. Decimate to exactly 48 kHz
5. Normalize to float32 in [-1, 1]

Output is the 300–3000 Hz audio a sound card would have produced, which is the
literal requirement in PRODUCT.md ("Not a decoder fork").

### `source.py`

Implements the four-method contract. `start_input(device_index=None)` accepts and
ignores `device_index` — `RXManager` passes it as a keyword argument
(`rx_manager.py:300`) and a network source has no use for it. Owns a client and a
demodulator, runs IQ → demodulate → `ring_buffer.add(audio)`, and computes
`AudioLevels` per block so `get_input_levels()` behaves as `RXManager` expects for
squelch and reporting.

**Precedent:** `tests/cli/test_cli_live_decode.py::TestFullPipeline` already hands a
real `RXManager` a four-method `FakeStream` duck type and decodes a real Robot36
image at ≥0.9 correlation. The seam this design depends on is exercised in CI
today; `SpyServerSource` implements the same contract that test already proves.

**Burst hazard.** That test's feeder deliberately throttles to stay near the
consumer, noting that a large backlog "would scroll the VIS header out of the
correlation window, which paced live audio never does." A network source can
produce exactly that — a stall followed by a burst of buffered IQ. The source
must deliver audio at a paced rate rather than dumping a backlog into the ring
buffer, or VIS detection will miss headers that a sound card would have caught.

### Config

New `SpyServerSettings(BaseModel)` registered on `AdvancedSettings`
(`config/manager.py:98-106`): `host`, `port` (default 5555), `frequency_hz`,
`gain` (the device RF/IF gain — `SETTING_GAIN`, not the digital multiplier), and
`stall_timeout_sec` (default 5.0). Lives in `advanced_settings_json` — **no migration**
(`database/models.py:351-353`). Reachable as `spyserver.host` through the existing
dot-notation path and already exposed by `/config`.

### CLI

`decode` gains `--spyserver [host:port]`, `--frequency HZ`, and `--band NAME`.
Flags override config; config supplies defaults. Mutually exclusive with
`--device` and `--file`.

Band presets (PRODUCT.md §Scope): `20m`→14.230, `40m`→7.171, `15m`→21.340,
`10m`→28.680, `80m`→3.845 MHz. PRODUCT.md lists both 14.230 and 14.233 for 20m;
`20m` resolves to 14.230 (the more common SSTV calling frequency) and 14.233 is
reachable via explicit `--frequency` rather than inventing a second preset name.
FM presets (145.500, 145.800) are rejected with a message saying FM is not yet
supported, rather than silently mis-demodulating.

## Prerequisite fix

`RXManager` takes `sample_rate` as an independent constructor arg
(`rx_manager.py:92`, `:101`) and never reconciles it against
`stream_manager.sample_rate` (`stream_manager.py:70`); `DSPManager` hardcodes
`48000` (`dsp_manager.py:303`, `:441`). Invisible today — everything is 48 kHz —
but any source at another rate silently produces wrong-length decoder configs and
garbled images. Tied together as its own change **before** the SDR work. The SDR
path itself runs at 48 kHz and does not depend on the fix; this removes a live
trap rather than enabling the feature.

## Error handling

Governing rule (PRODUCT.md): **a half-decoded image from a dropped stream must not
read as a weak signal.**

| Failure | When | Detected by | Reported as |
|---|---|---|---|
| Connection refused / DNS failure | connect | socket error | Can't reach the server; check host/port |
| Protocol/version rejection | handshake | major/minor mismatch | Server speaks a version I don't |
| Out-of-range tune | tune | client-side range pre-check | Frequency outside the server's range, with that range |
| **Silent tune mismatch** | tune | ClientSync ≠ requested | Server put me on X, not the Y I asked for |
| **Disconnect mid-decode** | during | socket close / short read | Stream dropped at N% — explicitly not a signal problem |
| **Server-side frame drops** | during | SequenceNumber gap | Server dropped frames; audio gaps, image may be corrupt |
| **Local buffer overflow** | during | `dropped_samples` | I couldn't keep up; audio gaps |
| Stall (no data) | during | time-since-last-IQ > timeout | Connected but silent past timeout |

All messages are SSTeVe voice: first person, contractions, concrete
`suggested_action`.

**Partial images are still saved** — a 60% decode is real data — but carry an
explicit stream-failure distinction, and the CLI says so. What must never happen
is finishing quietly and letting a TCP problem read as a weak signal.

Three distinct gap causes, kept distinct because they point at different fixes:
**server-side drops** (a `SequenceNumber` gap — the server or network lost
frames), **local overflow** (`AudioRingBuffer.dropped_samples`,
`ring_buffer.py:47`, already checked at `rx_manager.py:459-463` — we couldn't
keep up), and **stall** (an *empty* buffer, tracked as time-since-last-IQ).
Reporting all three as one "audio gap" would send the operator debugging the
wrong end of the link.

**Stall timeout defaults to 5 seconds**, configurable. SSTV is slow (Scottie S1 is
110 s), so too-aggressive aborts on ordinary jitter and too-lax wastes a long wait
learning the stream died. 5 s is a starting guess explicitly exposed for tuning
against a real server.

## Testing

Everything runs without a live SpyServer or radio hardware — tests requiring the
server could not run in CI.

- **`protocol.py`** — known frames parse to expected structs; commands serialize
  to exact bytes; malformed input rejected cleanly. Explicitly: the
  **gain-in-high-bits** extraction (a `MessageType` with nonzero upper 16 bits
  yields both the right type *and* the right gain), UINT8 vs INT16 sample
  conversion, and the raw-bytes non-NUL-terminated client name in `CMD_HELLO`.
- **`client.py`** — against an in-process fake socket: handshake success, version
  rejection (major/minor), mid-stream disconnect, short read, stall past timeout,
  **`SequenceNumber` gap detection**, and **silent tune mismatch** (ClientSync
  reports a different frequency than requested → explicit error, not silence).
  Also `CanControl=0` range refusal. Every failure surfaces as a typed error.
- **`demodulator.py`** — synthesize IQ with a known tone at a known offset;
  assert the tone lands at the expected audio frequency at 48 kHz within
  tolerance. Plus image-sideband rejection (a tone on the wrong side is
  suppressed — the property that makes it USB) and no clipping on strong input.
- **End-to-end** — the gate that ties SDR to SSTV: take
  `tests/reference/audio/mmsstv/scottie_s1_bear_je3hht.wav`, modulate it up into
  synthetic USB IQ, feed client-stub → demodulator → source → `RXManager`, assert
  a correct image decodes. Proves the SDR path delivers audio the real decoder
  accepts. Same shape as the existing gradient roundtrip gate.
- **`source.py`** — satisfies the four-method contract; levels computed;
  disconnect propagates.

**Not covered:** real server behavior — protocol quirks, genuine network jitter,
actual signal quality. That is the manual session this feature exists to enable.
CI passing does not prove the feature works against live infrastructure.

## Protocol unknowns

Everything in the protocol section above was verified across three independent
client implementations. These were **not** resolvable from source and are called
out so implementation treats them as open rather than assumed:

- **Keepalive is unconfirmed.** `CMD_PING(3)`/`MSG_TYPE_PONG(2)` are defined, but
  neither reference client ever sends a PING. Whether a real server times out an
  idle client is untested. Continuous streaming traffic likely makes it moot; if a
  real server drops us while idle, PING is the intended mechanism.
- **Endianness is inferred, not documented.** Every client `memcpy`s structs onto
  the socket on LE-only targets; no source explicitly states little-endian. Safe in
  practice, but a big-endian server would break the assumption.
- **`DeviceInfo.ForcedIQFormat`** exists to let a server pin a format, but neither
  reference client actually enforces it. Honor it defensively.
- **`MaximumBandwidth` vs `MaximumSampleRate`** — the distinction is never
  exercised by any client. Decimation math uses `MaximumSampleRate`.

These are the first things to check if a real server misbehaves in a way the
tests did not predict.

## Definition of done

Per CLAUDE.md, from `sstv_core/`:

1. `uv run pytest` — full suite, no exclusions, exit code verified
2. `uv run ruff check src/` and `uv run mypy src/` clean on changed files
3. No API changes this round, so no `openapi.json` regeneration

Plus the end-to-end synthetic-IQ test passing, and a manual session against a real
SpyServer decoding at least one live image — the actual goal.
