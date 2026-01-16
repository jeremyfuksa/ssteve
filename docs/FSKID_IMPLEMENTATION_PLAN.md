# FSKID Implementation Plan

## Quick Reference

**What FSKID Does:** Automatically transmits/receives operator callsign via FSK tones appended to SSTV images

**Why SSTeVe Needs It:** Smart Reply can auto-populate callsign field instead of requiring manual entry

**MMSSTV Compatibility:** 100% compatible with MMSSTV FSKID standard

---

## Critical Technical Parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| **Mark freq (1)** | 1900 Hz | Same as VIS leader |
| **Space freq (0)** | 2100 Hz | 200 Hz shift |
| **Baud rate** | 45.45 baud | 22ms per bit |
| **Symbol size** | 6 bits | Transmitted MSB-first |
| **Preamble** | 1500 Hz × 300ms | Detection anchor |
| **Guard** | 2100 Hz × 100ms | Frequency shift marker |

---

## Implementation Phases

### Phase 1: Decoder (Immediate Value)
**Goal:** SSTeVe can receive MMSSTV transmissions and auto-populate Smart Reply callsign

**Files to Create:**
```
sstv_core/src/sstv_core/decode/fsk_decoder.py
sstv_core/tests/test_fsk_decoder.py
to_reuse/testing_assets/fskid/robot36_k8jtk_fskid.wav
```

**Integration Points:**
1. `rx_manager.py:decode_audio()` - Call FSKID decoder after image completes
2. `database/models.py` - Store extracted callsign in `SSTVImage.callsign`
3. `api/routes/images.py` - Include `fskid_detected: bool` in image metadata
4. `ssteve-ui--figma/components/TransmitView.tsx` - Auto-fill callsign in Smart Reply modal

**Success Criteria:**
- [ ] Decode MMSSTV-generated test file with 100% accuracy
- [ ] Handle missing FSKID gracefully (return `None`, UI shows manual entry)
- [ ] Validate checksum, reject corrupted callsigns
- [ ] Smart Reply modal shows "✓ Auto-detected via FSKID" when present

**Estimated Effort:** 2-3 days (modeling from `vis_detector.py`)

---

### Phase 2: Encoder (Feature Parity)
**Goal:** SSTeVe transmissions include FSKID for MMSSTV receivers

**Files to Create:**
```
sstv_core/src/sstv_core/encode/fsk_generator.py
sstv_core/tests/test_fsk_generator.py
```

**Integration Points:**
1. `encode/tx_manager.py` - Append FSKID after image audio
2. `config/settings.py` - Add `enable_fskid_tx`, `operator_callsign` settings
3. `api/routes/transmit.py` - Use configured callsign for FSKID
4. `ssteve-ui--figma/components/SettingsModal.tsx` - UI for callsign configuration

**Success Criteria:**
- [ ] MMSSTV can decode SSTeVe-generated FSKID
- [ ] Roundtrip encode→decode test passes for 20+ callsigns
- [ ] User can disable FSKID in settings (default: enabled)
- [ ] Transmission time increases by ~1.3 seconds (acceptable)

**Estimated Effort:** 1-2 days (modeling from `vis_generator.py`)

---

### Phase 3: Extended Metadata (Future)
**Goal:** Encode contest number, grid square, signal report

**Optional Extensions:**
- Contest number (numeric ≤4095 or string format)
- Maidenhead grid square (6-character locator)
- RST signal report (auto-calculated or user-provided)

**Estimated Effort:** 1 day per extension

---

## Code Architecture

### Decoder Class Structure

```python
# sstv_core/src/sstv_core/decode/fsk_decoder.py

class FSKIDDecoder:
    """Decodes MMSSTV-compatible FSKID callsign from audio."""

    # Constants matching FSKID spec
    PREAMBLE_FREQ = 1500.0
    GUARD_FREQ = 2100.0
    MARK_FREQ = 1900.0      # Bit = 1
    SPACE_FREQ = 2100.0     # Bit = 0
    BIT_DURATION_MS = 22

    def __init__(self, sample_rate: int = 48000):
        """Initialize with Goertzel filters for 4 frequencies."""
        self._sample_rate = sample_rate
        self._bit_samples = int(sample_rate * 0.022)  # 1056 samples

        # Goertzel filters (reuse from vis_detector.py)
        self._filter_preamble = GoertzelFilter(self.PREAMBLE_FREQ, ...)
        self._filter_guard = GoertzelFilter(self.GUARD_FREQ, ...)
        self._filter_mark = GoertzelFilter(self.MARK_FREQ, ...)
        self._filter_space = GoertzelFilter(self.SPACE_FREQ, ...)

        self._state = "searching"
        self._symbols = []

    def decode(self, audio_buffer: np.ndarray) -> Optional[str]:
        """
        Decode FSKID from audio buffer.

        Returns:
            Callsign string if valid FSKID detected, None otherwise
        """
        self.reset()
        offset = 0

        while offset + self._bit_samples <= len(audio_buffer):
            chunk = audio_buffer[offset:offset + self._bit_samples]
            self._process_chunk(chunk)

            if self._state == "complete":
                return self._extract_callsign()

            offset += self._bit_samples

        return None  # No valid FSKID found

    def _process_chunk(self, samples: np.ndarray) -> None:
        """State machine: searching → preamble → guard → reading_bits → complete."""
        freq, confidence = self._detect_frequency(samples)

        if self._state == "searching":
            if freq == "preamble" and confidence > 0.6:
                self._preamble_count += 1
                if self._preamble_count >= 13:  # 300ms / 22ms
                    self._state = "preamble_detected"

        elif self._state == "preamble_detected":
            if freq == "guard":
                self._state = "guard_detected"

        elif self._state == "guard_detected":
            if freq == "mark":  # Start bit (1900 Hz)
                self._state = "reading_bits"
                self._current_symbol = []

        elif self._state == "reading_bits":
            if freq in ("mark", "space"):
                bit = 1 if freq == "mark" else 0
                self._current_symbol.append(bit)

                if len(self._current_symbol) == 6:
                    # Complete 6-bit symbol
                    symbol_value = self._bits_to_symbol(self._current_symbol)
                    self._symbols.append(symbol_value)

                    if symbol_value == 0x01:  # End marker
                        self._state = "complete"
                    else:
                        self._current_symbol = []  # Start next symbol

    def _extract_callsign(self) -> Optional[str]:
        """
        Extract callsign from symbol list:
        [$2A, C1, C2, ..., CN, $01, XSUM]
        """
        if len(self._symbols) < 4:  # Min: start + 1 char + end + checksum
            return None

        if self._symbols[0] != 0x0A:  # Check start marker ($2A → $0A)
            return None

        # Find end marker
        try:
            end_idx = self._symbols.index(0x01)
        except ValueError:
            return None

        # Extract character codes
        char_codes = self._symbols[1:end_idx]
        checksum = self._symbols[end_idx + 1]

        # Validate checksum
        calculated_xsum = 0x00
        for code in char_codes:
            calculated_xsum ^= code

        if calculated_xsum != checksum:
            logger.warning("FSKID checksum invalid (expected %02X, got %02X)",
                          calculated_xsum, checksum)
            return None

        # Convert to ASCII callsign
        callsign = ""
        for code in char_codes:
            if not (0x00 <= code <= 0x3F):
                return None
            callsign += chr(code + 0x20)

        logger.info("FSKID decoded: %s", callsign)
        return callsign

    def _detect_frequency(self, samples: np.ndarray) -> tuple[str, float]:
        """Use Goertzel filters to identify dominant frequency."""
        magnitudes = {
            "preamble": self._filter_preamble.magnitude(samples),
            "guard": self._filter_guard.magnitude(samples),
            "mark": self._filter_mark.magnitude(samples),
            "space": self._filter_space.magnitude(samples),
        }

        max_freq = max(magnitudes, key=magnitudes.get)
        max_mag = magnitudes[max_freq]
        total_mag = sum(magnitudes.values())

        confidence = max_mag / total_mag if total_mag > 0 else 0.0
        return max_freq, confidence

    def _bits_to_symbol(self, bits: list[int]) -> int:
        """Convert 6-bit list (MSB-first) to integer."""
        value = 0
        for i, bit in enumerate(bits):
            value |= (bit << (5 - i))
        return value
```

---

### Encoder Class Structure

```python
# sstv_core/src/sstv_core/encode/fsk_generator.py

class FSKIDGenerator:
    """Generates MMSSTV-compatible FSKID audio."""

    PREAMBLE_FREQ = 1500.0
    GUARD_FREQ = 2100.0
    MARK_FREQ = 1900.0
    SPACE_FREQ = 2100.0

    def __init__(self, sample_rate: int = 48000):
        self._sample_rate = sample_rate

    def generate(self, callsign: str) -> np.ndarray:
        """
        Generate complete FSKID audio for callsign.

        Args:
            callsign: Operator callsign (3-8 characters, alphanumeric)

        Returns:
            Audio samples ready to append after SSTV image

        Raises:
            ValueError: If callsign contains invalid characters
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

        # 5. Generate FSK audio for each bit
        for symbol in symbols:
            bits = self._symbol_to_bits(symbol)
            for bit in bits:
                freq = 1900.0 if bit == 1 else 2100.0
                audio_parts.append(self._generate_tone(freq, 22))

        result = np.concatenate(audio_parts)
        logger.info("Generated FSKID for %s: %d samples (%.2f sec)",
                   callsign, len(result), len(result) / self._sample_rate)
        return result

    def _encode_callsign(self, callsign: str) -> list[int]:
        """
        Convert callsign to symbol list with framing and checksum.

        Example: "K8JTK" → [0x0A, 0x2B, 0x18, 0x2A, 0x34, 0x2B, 0x01, XSUM]
        """
        callsign = callsign.upper().strip()

        # Validate callsign format
        if not re.match(r'^[A-Z0-9/]{3,8}$', callsign):
            raise ValueError(f"Invalid callsign format: {callsign}")

        symbols = [0x0A]  # Start marker ($2A → $0A)

        # Convert each character
        xsum = 0x00
        for char in callsign:
            ascii_code = ord(char)
            if not (0x20 <= ascii_code <= 0x5F):
                raise ValueError(f"Character '{char}' out of range for FSKID")

            encoded = ascii_code - 0x20
            symbols.append(encoded)
            xsum ^= encoded

        symbols.append(0x01)  # End marker
        symbols.append(xsum)  # Checksum

        return symbols

    def _symbol_to_bits(self, symbol: int) -> list[int]:
        """Convert 6-bit symbol to bit list (MSB-first)."""
        return [(symbol >> (5 - i)) & 1 for i in range(6)]

    def _generate_tone(self, freq: float, duration_ms: float) -> np.ndarray:
        """Generate sine wave at specified frequency."""
        num_samples = int(self._sample_rate * duration_ms / 1000)
        t = np.arange(num_samples) / self._sample_rate
        return (np.sin(2 * np.pi * freq * t) * 0.8).astype(np.float32)

    def get_duration_ms(self, callsign: str) -> float:
        """Calculate total FSKID duration."""
        num_symbols = 2 + len(callsign) + 2  # start + chars + end + checksum
        return 300 + 100 + 22 + (num_symbols * 6 * 22)
```

---

## Integration Examples

### RX Manager Integration

```python
# sstv_core/src/sstv_core/decode/rx_manager.py

class RxManager:
    def __init__(self, ...):
        self.vis_detector = VISDetector(sample_rate)
        self.fskid_decoder = FSKIDDecoder(sample_rate)  # ← NEW
        # ...

    async def decode_audio(self, audio_buffer: np.ndarray):
        # 1. Detect VIS code
        vis_result = self.vis_detector.detect_from_buffer(audio_buffer)
        if not vis_result or not vis_result.mode:
            raise ValueError("No valid VIS code detected")

        # 2. Decode SSTV image scanlines
        mode_params = get_mode_parameters(vis_result.mode)
        image = self.scanline_decoder.decode(audio_buffer, mode_params)

        # 3. NEW: Look for FSKID after image completes
        image_duration_samples = mode_params.total_duration_ms * self._sample_rate / 1000
        fskid_start = int(image_duration_samples)

        callsign = None
        if fskid_start < len(audio_buffer):
            fskid_buffer = audio_buffer[fskid_start:]
            callsign = self.fskid_decoder.decode(fskid_buffer)

            if callsign:
                logger.info("FSKID detected: %s", callsign)
            else:
                logger.debug("No FSKID detected, Smart Reply will require manual entry")

        # 4. Store in database
        image_record = self.db.save_image(
            image_data=image,
            mode=vis_result.mode.name,
            callsign=callsign,  # ← May be None
            rx_quality=vis_result.confidence,
            timestamp=datetime.utcnow()
        )

        # 5. Emit WebSocket event
        await self.websocket.send_json({
            "event": "decode_complete",
            "image_id": image_record.id,
            "mode": vis_result.mode.name,
            "callsign": callsign,
            "fskid_detected": callsign is not None  # ← UI indicator
        })

        return image_record
```

---

### TX Manager Integration

```python
# sstv_core/src/sstv_core/encode/tx_manager.py

class TxManager:
    def __init__(self, config: TransmitConfig, ...):
        self.vis_generator = VISGenerator(sample_rate)
        self.fskid_generator = FSKIDGenerator(sample_rate)  # ← NEW
        self.config = config
        # ...

    async def transmit_image(self, image: np.ndarray, mode: SSTVMode):
        audio_parts = []

        # 1. Generate VIS code
        vis_audio = self.vis_generator.generate(mode)
        audio_parts.append(vis_audio)

        # 2. Encode SSTV image
        image_audio = self.scanline_encoder.encode(image, mode)
        audio_parts.append(image_audio)

        # 3. NEW: Append FSKID (if enabled and callsign configured)
        if self.config.enable_fskid_tx and self.config.operator_callsign:
            try:
                fskid_audio = self.fskid_generator.generate(self.config.operator_callsign)
                audio_parts.append(fskid_audio)
                fskid_duration = len(fskid_audio) / self._sample_rate
                logger.info("Appended FSKID: %s (+%.2f sec)",
                           self.config.operator_callsign, fskid_duration)
            except ValueError as e:
                logger.error("FSKID generation failed: %s", e)
                # Continue without FSKID

        # 4. Concatenate and transmit
        full_audio = np.concatenate(audio_parts)

        # PTT control + audio playback
        await self.ptt_controller.key_radio()
        await asyncio.sleep(self.config.ptt_pre_delay_ms / 1000)

        self.audio_output.play(full_audio)

        await asyncio.sleep(self.config.ptt_post_delay_ms / 1000)
        await self.ptt_controller.unkey_radio()

        logger.info("Transmission complete: %s with FSKID=%s",
                   mode.name, self.config.operator_callsign)
```

---

### Smart Reply UI Integration

```tsx
// ssteve-ui--figma/components/TransmitView.tsx

interface SmartReplyModalProps {
  receivedImage: {
    id: number;
    callsign?: string;
    fskid_detected: boolean;
    mode: string;
    thumbnail_url: string;
  };
  onClose: () => void;
  onSubmit: (callsign: string, template: string) => Promise<void>;
}

const SmartReplyModal: React.FC<SmartReplyModalProps> = ({
  receivedImage,
  onClose,
  onSubmit
}) => {
  const [callsign, setCallsign] = useState(receivedImage.callsign || "");
  const [template, setTemplate] = useState("599_tnx");

  const handleSubmit = async () => {
    if (!callsign.trim()) {
      toast.error("Callsign required");
      return;
    }

    await onSubmit(callsign, template);
    onClose();
  };

  return (
    <Dialog open onClose={onClose}>
      <DialogTitle>Smart Reply to {receivedImage.callsign || "Unknown"}</DialogTitle>

      <DialogContent>
        {/* Callsign input with FSKID indicator */}
        <Input
          label="Callsign"
          value={callsign}
          onChange={(e) => setCallsign(e.target.value.toUpperCase())}
          placeholder="K8JTK"
          hint={receivedImage.fskid_detected
            ? "✓ Auto-detected via FSKID"
            : "Enter callsign manually (no FSKID detected)"}
          variant={receivedImage.fskid_detected ? "success" : "default"}
          leftIcon={receivedImage.fskid_detected ? <CheckCircle /> : <AlertCircle />}
        />

        {/* Template selection */}
        <Select
          label="Reply Template"
          value={template}
          onChange={setTemplate}
          options={[
            { value: "599_tnx", label: "599 TNX - Standard signal report" },
            { value: "custom", label: "Custom message" }
          ]}
        />

        {/* Preview received image */}
        <img
          src={receivedImage.thumbnail_url}
          alt="Received SSTV"
          className="w-full rounded border border-gray-700"
        />
      </DialogContent>

      <DialogActions>
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button onClick={handleSubmit}>Generate Reply</Button>
      </DialogActions>
    </Dialog>
  );
};
```

---

## Testing Checklist

### Decoder Tests
- [ ] Decode clean MMSSTV-generated test file
- [ ] Decode SSTeVe-generated test file (roundtrip)
- [ ] Handle missing FSKID gracefully (return `None`)
- [ ] Reject corrupted checksum (flip bits, verify failure)
- [ ] Test with 20+ callsign formats (W1AW, VE3XYZ, G4ABC/P, etc.)
- [ ] Decode with 10dB SNR (noise resilience)
- [ ] Timeout after 3 seconds if no valid FSKID

### Encoder Tests
- [ ] Generate valid FSKID for "K8JTK"
- [ ] MMSSTV can decode SSTeVe-generated FSKID
- [ ] Roundtrip: encode → decode → verify callsign
- [ ] Validate callsign format (reject invalid characters)
- [ ] Calculate correct checksum
- [ ] Duration matches formula (300+100+22+N*132ms)

### Integration Tests
- [ ] RX Manager populates `SSTVImage.callsign` from FSKID
- [ ] Smart Reply modal auto-fills callsign when FSKID present
- [ ] Smart Reply works when FSKID missing (manual entry)
- [ ] TX Manager appends FSKID when `enable_fskid_tx=true`
- [ ] TX Manager skips FSKID when disabled or no callsign configured
- [ ] WebSocket event includes `fskid_detected` flag

---

## Performance Benchmarks

**Target Metrics:**
- Decoder processing time: <50ms (negligible vs 8-second image decode)
- Encoder generation time: <10ms
- Transmission overhead: ~1.3 seconds for typical callsign (acceptable)
- Memory overhead: <1 MB (Goertzel filters + audio buffer)

**Test Environment:**
- Raspberry Pi 4 (2GB RAM, quad-core 1.5GHz)
- 48kHz sample rate
- Typical 6-character callsign

---

## Migration Checklist

### Phase 1: Decoder (Week 1)
- [ ] Day 1: Implement `FSKIDDecoder` class with Goertzel filters
- [ ] Day 2: Write unit tests, create reference audio files
- [ ] Day 3: Integrate with `rx_manager.py`
- [ ] Day 4: Update Smart Reply UI for auto-fill
- [ ] Day 5: E2E testing with MMSSTV compatibility

### Phase 2: Encoder (Week 2)
- [ ] Day 1: Implement `FSKIDGenerator` class
- [ ] Day 2: Write unit tests, roundtrip validation
- [ ] Day 3: Integrate with `tx_manager.py`
- [ ] Day 4: Add config UI in Settings modal
- [ ] Day 5: MMSSTV interoperability testing

---

## Success Metrics

**Phase 1 Complete When:**
- SSTeVe decodes MMSSTV FSKID with 100% accuracy (clean signal)
- Smart Reply modal shows "✓ Auto-detected via FSKID" for received images
- No regressions in existing VIS detection or image decoding
- Unit test coverage ≥90%

**Phase 2 Complete When:**
- MMSSTV decodes SSTeVe FSKID with 100% accuracy
- Users can configure callsign in Settings → Transmit
- FSKID can be disabled without breaking transmit
- Roundtrip tests pass for 20+ callsigns

---

## Documentation Updates

After implementation, update:

1. **`docs/TRANSMIT_SPEC.md`** - Add FSKID to Smart Reply section
2. **`docs/API_SPEC.md`** (if exists) - Document `fskid_detected` field
3. **`CLAUDE.md`** - Add FSKID to "Available Specialized Agents" context
4. **`README.md`** - Highlight FSKID as key feature ("MMSSTV-compatible callsign exchange")
5. **User Guide** - Explain what FSKID is and how to configure callsign

---

## Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| MMSSTV compatibility issues | Medium | High | Test with actual MMSSTV before release |
| FSKID decode failures in noise | High | Low | Graceful fallback to manual entry |
| User forgets to set callsign | High | Low | Show warning in UI if `operator_callsign` empty |
| Performance overhead | Low | Low | Profile on low-end hardware (RPi) |
| Checksum collisions | Very Low | Low | XOR is weak but sufficient for this use case |

---

## Future Enhancements

**Extended Metadata (Phase 3):**
- Grid square encoding (Maidenhead locator)
- Contest number (numeric or string)
- Signal report (RST auto-calculated from SNR)

**Advanced Features:**
- Multi-line FSKID (split long callsigns across multiple frames)
- UTF-8 callsign support (for non-English characters)
- CRC16 checksum (stronger than XOR, but breaks MMSSTV compat)
- FSKID "signature" verification (optional crypto signing)

---

## References

- [MMSSTV FSKID Specification](https://github.com/n5ac/mmsstv/blob/master/fskid.txt)
- [MMSSTV by JE3HHT](https://hamsoft.ca/pages/mmsstv.php)
- [SSTeVe FSKID Specification](./FSKID_SPECIFICATION.md) (this project)
- [SSTeVe Transmit Specification](./TRANSMIT_SPEC.md) (Smart Reply context)

---

**Document Status:** Complete technical specification for FSKID decoder/encoder implementation

**Next Action:** Begin Phase 1 implementation (`fsk_decoder.py`)
