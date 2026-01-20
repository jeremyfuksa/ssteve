# FSKID Implementation Specification for SSTeVe

## Executive Summary

FSKID (Frequency-Shift Keying Identification) is an FSK-modulated data channel appended to SSTV transmissions that encodes operator callsign and metadata. This document specifies complete decoder/encoder implementation for SSTeVe to achieve automatic callsign population in Smart Reply.

**Key Benefit:** Receiving stations automatically extract transmitting station's callsign without OCR or manual entry, enabling one-click Smart Reply QSO responses.

---

## Protocol Specification (MMSSTV Compatible)

### Physical Layer

| Parameter | Value | Notes |
|-----------|-------|-------|
| Mark frequency (bit=1) | 1900 Hz | Same as VIS leader tone |
| Space frequency (bit=0) | 2100 Hz | 200 Hz shift from mark |
| Baud rate | 45.45 baud | 22ms per bit |
| Sample rate | 48000 Hz | SSTeVe standard |
| Samples per bit | 1056 samples | 48000 × 0.022 |

### Frame Structure

```
┌─────────────────────────────────────────────────────────────┐
│ PREAMBLE │ GUARD │ START │  DATA BITS (6-bit symbols)  │
│ 1500 Hz  │2100 Hz│1900 Hz│   1900 Hz (1) / 2100 Hz (0) │
│  300ms   │100ms  │ 22ms  │   22ms each, MSB-first      │
└─────────────────────────────────────────────────────────────┘
```

**Timing Breakdown:**
- **Preamble:** 1500 Hz for 300ms (1900 Hz in "narrow mode" - rare)
- **Guard:** 2100 Hz for 100ms (frequency shift marker)
- **Start bit:** 1900 Hz for 22ms (synchronization)
- **Data bits:** 6 bits per symbol, repeated for full message
- **No stop bit:** Continuous data stream until complete

### Symbol Encoding

**6-bit symbols (B5 B4 B3 B2 B1 B0):**
- Transmitted **MSB-first** (B5 → B4 → B3 → B2 → B1 → B0)
- Each bit is 22ms: `1 = 1900 Hz`, `0 = 2100 Hz`
- Binary value: `B5×32 + B4×16 + B3×8 + B2×4 + B1×2 + B0`

**Example:** Symbol `0x15` (decimal 21) = binary `010101`
```
B5=0 → 2100Hz 22ms
B4=1 → 1900Hz 22ms
B3=0 → 2100Hz 22ms
B2=1 → 1900Hz 22ms
B1=0 → 2100Hz 22ms
B0=1 → 1900Hz 22ms
Total duration: 132ms
```

---

## Data Encoding

### Callsign Frame

```
┌──────┬────────────────────────┬──────┬──────────┐
│ $2A  │  C1  C2  C3 ... CN     │ $01  │  XSUM    │
│Start │  Callsign characters   │ End  │ Checksum │
└──────┴────────────────────────┴──────┴──────────┘
```

**ASCII Mapping:** Characters `$20-$5F` (space through underscore) map to `$00-$3F`
- Formula: `encoded_value = ascii_code - 0x20`
- Example: `'K'` (ASCII 0x4B) → `0x4B - 0x20 = 0x2B` → transmit as 6-bit `101011`

**Checksum:** XOR of all character codes
```python
xsum = 0x00
for char in callsign:
    xsum ^= (ord(char) - 0x20)
```

**Example Transmission: "K8JTK"**

| Step | Character | ASCII | Encoded | Binary (MSB-first) |
|------|-----------|-------|---------|-------------------|
| 1 | Start marker | $2A | $0A | `001010` |
| 2 | 'K' | $4B | $2B | `101011` |
| 3 | '8' | $38 | $18 | `011000` |
| 4 | 'J' | $4A | $2A | `101010` |
| 5 | 'T' | $54 | $34 | `110100` |
| 6 | 'K' | $4B | $2B | `101011` |
| 7 | End marker | $01 | $01 | `000001` |
| 8 | Checksum | - | XOR | `xxxxxx` |

**Total duration:** 8 symbols × 132ms = **1.056 seconds**

### Contest Number (Optional Extension)

**Numeric format (≤4095):**
```
┌──────┬──────┬──────┬──────────┐
│ $02  │  HH  │  LL  │  XSUM    │
│Start │Upper │Lower │ Checksum │
└──────┴──────┴──────┴──────────┘

HH = (number >> 6) & 0x3F  # Upper 6 bits
LL = number & 0x3F          # Lower 6 bits
XSUM = $02 XOR HH XOR LL
```

**String format:**
```
┌────────────────────────┬──────┬──────────┐
│  S1  S2  S3 ... SN     │ $01  │  XSUM    │
│  Contest # as string   │ End  │ Checksum │
└────────────────────────┴──────┴──────────┘

ASCII $30-$5F → $10-$3F (digits/letters offset by 0x20)
```

---

## Decoder Implementation (`fsk_decoder.py`)

### Architecture

Model after `vis_detector.py` using Goertzel filters:

```python
class FSKIDDecoder:
    """Decodes FSKID callsign from audio following SSTV image."""

    PREAMBLE_FREQ = 1500.0      # Standard mode (1900 Hz narrow - detect both)
    PREAMBLE_NARROW_FREQ = 1900.0
    GUARD_FREQ = 2100.0
    MARK_FREQ = 1900.0          # Bit = 1
    SPACE_FREQ = 2100.0         # Bit = 0

    PREAMBLE_DURATION_MS = 300
    GUARD_DURATION_MS = 100
    START_BIT_DURATION_MS = 22
    BIT_DURATION_MS = 22

    DETECTION_THRESHOLD = 0.6   # Lower than VIS (FSKID often degraded)
```

### State Machine

```
┌──────────────┐
│  SEARCHING   │ ─── Detect 1500/1900 Hz for 300ms ───┐
└──────────────┘                                       │
                                                       ▼
┌──────────────┐                            ┌─────────────────┐
│   GUARD      │ ◄─────────────────────────│ PREAMBLE_DETECT │
└──────────────┘                            └─────────────────┘
       │
       │ Detect 2100 Hz for 100ms
       ▼
┌──────────────┐
│  START_BIT   │ ─── Detect 1900 Hz for 22ms ───┐
└──────────────┘                                 │
                                                 ▼
┌──────────────┐                         ┌──────────────┐
│   COMPLETE   │ ◄──── Read 6 bits ─────│ READING_BITS │
└──────────────┘                         └──────────────┘
       │                                        │
       │                                        │ Repeat until $01 end marker
       │                                        │
       └────────────────────────────────────────┘
```

### Core Methods

```python
def process_samples(self, samples: np.ndarray) -> Optional[str]:
    """Process 22ms audio chunk, return callsign when complete."""

def _detect_frequency(self, samples: np.ndarray) -> tuple[str, float]:
    """Use Goertzel filters to identify 1500/1900/2100 Hz."""

def _decode_symbol(self) -> int:
    """Convert 6 bits to integer value (0-63)."""

def _decode_callsign(self, symbols: list[int]) -> Optional[str]:
    """
    Extract callsign from symbol stream:
    1. Find $2A start marker
    2. Collect ASCII characters until $01 end marker
    3. Verify checksum
    4. Convert to readable callsign string
    """

def _validate_checksum(self, symbols: list[int]) -> bool:
    """XOR all character codes, compare to transmitted checksum."""
```

### Integration with `rx_manager.py`

```python
# In RxManager.decode_audio():
def decode_audio(self, audio_buffer: np.ndarray):
    # 1. Detect VIS code (existing)
    vis_result = self.vis_detector.detect(audio_buffer)

    # 2. Decode SSTV image scanlines (existing)
    image = self.scanline_decoder.decode(audio_buffer, vis_result.mode)

    # 3. NEW: Look for FSKID after image completes
    fskid_offset = self._calculate_image_end_offset(vis_result.mode)
    fskid_buffer = audio_buffer[fskid_offset:]

    callsign = self.fskid_decoder.decode(fskid_buffer)

    # 4. Store in database with extracted callsign
    self.db.save_image(image, callsign=callsign, mode=vis_result.mode)

    # 5. Emit WebSocket event with callsign for UI
    await self.websocket.send_json({
        "event": "decode_complete",
        "callsign": callsign,
        "fskid_detected": callsign is not None
    })
```

---

## Encoder Implementation (Enhancement to `vis_generator.py`)

### New Class: `FSKIDGenerator`

```python
class FSKIDGenerator:
    """Generates FSKID audio for callsign transmission."""

    def __init__(self, sample_rate: int = 48000):
        self._sample_rate = sample_rate

    def generate(self, callsign: str) -> np.ndarray:
        """
        Generate complete FSKID sequence for callsign.

        Returns:
            Audio samples ready to append after SSTV image
        """
        audio_parts = []

        # 1. Preamble (1500 Hz, 300ms)
        audio_parts.append(self._generate_tone(1500.0, 300))

        # 2. Guard (2100 Hz, 100ms)
        audio_parts.append(self._generate_tone(2100.0, 100))

        # 3. Start bit (1900 Hz, 22ms)
        audio_parts.append(self._generate_tone(1900.0, 22))

        # 4. Encode callsign as symbols
        symbols = self._encode_callsign(callsign)

        # 5. Generate FSK audio for each bit of each symbol
        for symbol in symbols:
            bits = self._symbol_to_bits(symbol)  # MSB-first
            for bit in bits:
                freq = 1900.0 if bit == 1 else 2100.0
                audio_parts.append(self._generate_tone(freq, 22))

        return np.concatenate(audio_parts)

    def _encode_callsign(self, callsign: str) -> list[int]:
        """
        Convert callsign to symbol list with framing and checksum.

        Example: "K8JTK" → [$2A, $2B, $18, $2A, $34, $2B, $01, XSUM]
        """
        symbols = [0x0A]  # Start marker $2A → $0A

        # Convert each character
        xsum = 0x00
        for char in callsign.upper():
            encoded = ord(char) - 0x20
            if not (0x00 <= encoded <= 0x3F):
                raise ValueError(f"Invalid character in callsign: {char}")
            symbols.append(encoded)
            xsum ^= encoded

        symbols.append(0x01)  # End marker
        symbols.append(xsum)  # Checksum

        return symbols

    def _symbol_to_bits(self, symbol: int) -> list[int]:
        """Convert 6-bit symbol to bit list (MSB-first)."""
        return [(symbol >> (5 - i)) & 1 for i in range(6)]

    def get_duration_ms(self, callsign: str) -> float:
        """Calculate FSKID duration for transmission planning."""
        num_symbols = 2 + len(callsign) + 2  # Start + chars + end + checksum
        return 300 + 100 + 22 + (num_symbols * 6 * 22)
```

### Integration with Transmit Pipeline

```python
# In encode/tx_manager.py:
def transmit_image(self, image: np.ndarray, mode: SSTVMode, callsign: str):
    audio_parts = []

    # 1. Generate VIS code
    vis_audio = self.vis_generator.generate(mode)
    audio_parts.append(vis_audio)

    # 2. Encode SSTV image scanlines
    image_audio = self.scanline_encoder.encode(image, mode)
    audio_parts.append(image_audio)

    # 3. NEW: Append FSKID with operator callsign
    if callsign:
        fskid_audio = self.fskid_generator.generate(callsign)
        audio_parts.append(fskid_audio)
        logger.info("Appended FSKID for callsign: %s (+%.1f sec)",
                   callsign, len(fskid_audio) / 48000)

    # 4. Transmit complete audio
    full_audio = np.concatenate(audio_parts)
    self.audio_output.play(full_audio)
```

---

## Smart Reply Integration

### Database Schema (No Changes Required)

`SSTVImage` table already has `callsign` field:

```python
class SSTVImage(Base):
    __tablename__ = "sstv_images"

    id = Column(Integer, primary_key=True)
    callsign = Column(String(20), nullable=True)  # ← Populated by FSKID
    operator_name = Column(String(100), nullable=True)
    frequency = Column(Float, nullable=True)
    mode = Column(String(20), nullable=False)
    # ...
```

### API Enhancement (`routes/smart_reply.py`)

**Current (Phase 1):**
```python
# POST /api/v1/smart-reply
{
  "received_image_id": 123,
  "callsign": "K8JTK",  # ← USER MUST TYPE THIS
  "template": "599_tnx"
}
```

**Enhanced (with FSKID):**
```python
# GET /api/v1/images/123
{
  "id": 123,
  "callsign": "K8JTK",  # ← AUTO-POPULATED FROM FSKID
  "fskid_detected": true,
  "mode": "Robot 36",
  // ...
}

# POST /api/v1/smart-reply
{
  "received_image_id": 123,
  "callsign": "K8JTK",  # ← PRE-FILLED IN UI (user can edit)
  "template": "599_tnx"
}
```

### UI Changes (`TransmitView.tsx`)

**Smart Reply modal enhancements:**

```tsx
// When user clicks "Reply" on received image
const handleReply = async (imageId: number) => {
  const image = await api.getImage(imageId);

  setSmartReplyModal({
    isOpen: true,
    callsign: image.callsign || "",  // ← Auto-fill if FSKID present
    fskidDetected: image.fskid_detected,
    receivedImageId: imageId
  });
};

// In modal UI:
<Input
  label="Callsign"
  value={callsign}
  onChange={setCallsign}
  placeholder="K8JTK"
  hint={fskidDetected
    ? "✓ Auto-detected via FSKID"
    : "Enter callsign manually"}
  variant={fskidDetected ? "success" : "default"}
/>
```

---

## Configuration (`config/settings.py`)

Add FSKID settings:

```python
class TransmitConfig(BaseModel):
    # Existing fields...
    ptt_pre_delay_ms: int = 500
    ptt_post_delay_ms: int = 200

    # NEW: FSKID settings
    enable_fskid_tx: bool = True           # Append FSKID to transmissions
    enable_fskid_rx: bool = True           # Decode FSKID from received
    fskid_narrow_mode: bool = False        # Use 1900 Hz preamble (rare)
    operator_callsign: str = ""            # User's callsign for TX

    @validator('operator_callsign')
    def validate_callsign(cls, v):
        if not v:
            return v
        # Basic validation: 3-8 chars, alphanumeric + slash
        if not re.match(r'^[A-Z0-9/]{3,8}$', v.upper()):
            raise ValueError("Invalid callsign format")
        return v.upper()
```

---

## Testing Strategy

### Unit Tests (`tests/test_fskid_decoder.py`)

```python
def test_decode_callsign_k8jtk():
    """Test FSKID decoding with reference audio."""
    decoder = FSKIDDecoder(sample_rate=48000)

    # Load reference audio: Robot 36 + FSKID "K8JTK"
    audio = load_test_audio("robot36_k8jtk_fskid.wav")

    # Skip to FSKID portion (after image)
    fskid_start = calculate_image_duration("Robot 36") * 48000
    fskid_audio = audio[int(fskid_start):]

    callsign = decoder.decode(fskid_audio)
    assert callsign == "K8JTK"

def test_encode_decode_roundtrip():
    """Verify encoder output can be decoded."""
    encoder = FSKIDGenerator(sample_rate=48000)
    decoder = FSKIDDecoder(sample_rate=48000)

    test_callsigns = ["K8JTK", "W1AW", "VE3XYZ", "G4ABC/P"]

    for callsign in test_callsigns:
        audio = encoder.generate(callsign)
        decoded = decoder.decode(audio)
        assert decoded == callsign, f"Roundtrip failed for {callsign}"

def test_checksum_validation():
    """Corrupt checksum should reject callsign."""
    decoder = FSKIDDecoder(sample_rate=48000)

    # Generate valid audio, then corrupt last symbol (checksum)
    encoder = FSKIDGenerator()
    audio = encoder.generate("K8JTK")

    # Flip frequency of checksum bits
    checksum_offset = -6 * 1056  # Last 6 bits
    audio[checksum_offset:] *= -1  # Invert phase (corrupts FSK)

    callsign = decoder.decode(audio)
    assert callsign is None, "Should reject corrupted checksum"
```

### Integration Tests

1. **MMSSTV Compatibility:** Generate test file in MMSSTV, verify SSTeVe decodes FSKID
2. **End-to-End:** Transmit → Record loopback → Verify Smart Reply auto-populates
3. **Noise Resilience:** Add white noise (SNR 10dB), verify FSKID still decodes

### Reference Audio Creation

Create test assets in `to_reuse/testing_assets/fskid/`:

```
robot36_k8jtk_fskid.wav       - Clean signal
martin_m1_w1aw_fskid.wav      - Another mode
noisy_ve3xyz_fskid.wav        - Low SNR (10dB)
mmsstv_generated_g4abc.wav    - From actual MMSSTV TX
```

---

## Performance Considerations

### Computational Overhead

**Decoder:**
- Goertzel filters: 4 filters × 1056 samples = ~4K ops per bit
- 6 bits per symbol, ~10 symbols per callsign = ~240K ops
- Negligible compared to image decode (~500ms @ 48kHz = 24M samples)

**Encoder:**
- Sine wave generation: 6 bits × 1056 samples × 10 symbols = ~63K samples
- ~1.3 seconds audio duration for typical callsign
- Adds <5% to total transmission time

### Error Handling

**Decoder failure modes:**
1. **No FSKID present** → Return `None`, UI shows "Enter callsign manually"
2. **Corrupted preamble** → No detection, fallback to manual entry
3. **Invalid checksum** → Reject callsign, log warning, return `None`
4. **Partial decode** → Timeout after 3 seconds, return `None`

**Graceful degradation:** FSKID is always optional. Smart Reply works with manual entry if FSKID fails.

---

## Migration Path

### Phase 1: Decoder Only (Immediate Value)
1. Implement `FSKIDDecoder` class
2. Integrate with `rx_manager.py`
3. Auto-populate Smart Reply callsign field
4. **Benefit:** SSTeVe receives MMSSTV transmissions with auto-callsign

### Phase 2: Encoder (Feature Parity)
1. Implement `FSKIDGenerator` class
2. Integrate with `tx_manager.py`
3. Add config setting `enable_fskid_tx`
4. **Benefit:** SSTeVe transmissions work with MMSSTV receivers

### Phase 3: Extended Metadata
1. Add contest number support
2. Add grid square encoding (extension to spec)
3. Add signal report encoding (RST)

---

## Standards Compliance

**MMSSTV Compatibility:** Protocol freely usable per JE3HHT (Makoto Mori)

**Amateur Radio Regulations:**
- FCC §97.119: Station identification required every 10 minutes
- FSKID does NOT replace voice/CW ID requirements
- FSKID is supplemental data for logging convenience

---

## File Structure

New files to create:

```
sstv_core/src/sstv_core/
├── decode/
│   ├── fsk_decoder.py           # ← NEW: FSKID decoder
│   └── vis_detector.py           # (existing, reference model)
├── encode/
│   ├── fsk_generator.py          # ← NEW: FSKID encoder
│   └── vis_generator.py          # (existing, reference model)
└── tests/
    ├── test_fsk_decoder.py       # ← NEW: Unit tests
    ├── test_fsk_generator.py     # ← NEW: Unit tests
    └── test_fsk_integration.py   # ← NEW: E2E tests

to_reuse/testing_assets/
└── fskid/                        # ← NEW: Reference audio files
    ├── robot36_k8jtk_fskid.wav
    ├── martin_m1_w1aw_fskid.wav
    └── noisy_ve3xyz_fskid.wav
```

---

## Summary

This specification provides complete technical detail for MMSSTV-compatible FSKID implementation in SSTeVe. The protocol adds ~1.3 seconds to transmissions but enables automatic callsign exchange, making Smart Reply truly "smart."

**Key Design Principles:**
1. **Graceful degradation:** FSKID failure never breaks Smart Reply (fallback to manual)
2. **Standards compliant:** MMSSTV-compatible, freely usable protocol
3. **Architecture symmetry:** Decoder mirrors `vis_detector.py`, encoder mirrors `vis_generator.py`
4. **Optional feature:** User can disable FSKID TX/RX in config

**Next Steps:**
1. Implement `FSKIDDecoder` (Phase 1)
2. Create unit tests with reference audio
3. Integrate with `rx_manager.py` and Smart Reply UI
4. Implement `FSKIDGenerator` (Phase 2)
5. Test with MMSSTV for interoperability
