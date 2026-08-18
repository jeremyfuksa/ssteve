"""FSKID (FSK Identification) decoder for MMSSTV-compatible callsign extraction.

Decodes FSK-modulated callsign data transmitted after SSTV images.
Compatible with MMSSTV FSKID standard (JE3HHT).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

# Reuse GoertzelFilter from vis_detector
from sstv_core.decode.vis_detector import GoertzelFilter

logger = logging.getLogger(__name__)


@dataclass
class FSKIDResult:
    """Result of FSKID decoding."""

    callsign: str
    confidence: float  # 0.0-1.0
    checksum_valid: bool
    symbols_decoded: int

    def to_dict(self) -> dict:
        return {
            "callsign": self.callsign,
            "confidence": self.confidence,
            "checksum_valid": self.checksum_valid,
            "symbols_decoded": self.symbols_decoded,
        }


class FSKIDDecoder:
    """Decodes MMSSTV-compatible FSKID callsign from audio.

    FSKID Protocol (MMSSTV Standard):
    - Preamble: 1500 Hz for 300ms (1900 Hz narrow mode - detect both)
    - Guard: 2100 Hz for 100ms
    - Start bit: 1900 Hz for 22ms
    - Data bits: 6 bits per symbol, 22ms each, MSB-first
      - Mark (1): 1900 Hz
      - Space (0): 2100 Hz
    - Frame: [Start $2A] [Callsign chars] [End $01] [Checksum XOR]
    - ASCII mapping: $20-$5F → $00-$3F (subtract 0x20)

    Example: "K8JTK" transmitted as:
        [$0A, $2B, $18, $2A, $34, $2B, $01, XSUM]
    """

    # Frequency constants (MMSSTV FSKID standard)
    PREAMBLE_FREQ = 1500.0  # Standard mode
    MARK_FREQ = 1900.0  # Bit = 1 (also narrow-mode preamble)
    SPACE_FREQ = 2100.0  # Bit = 0 (also guard tone)

    # Timing constants
    PREAMBLE_DURATION_MS = 300
    GUARD_DURATION_MS = 100
    START_BIT_DURATION_MS = 22
    BIT_DURATION_MS = 22

    # Detection threshold (lower than VIS - FSKID often more degraded)
    DETECTION_THRESHOLD = 0.5

    # Protocol constants
    # The frame marker is the literal $2A from the MMSSTV spec. The $20
    # subtraction applies only to the callsign characters Cx, not to the
    # markers -- verified against off-air MMSSTV transmissions (XE2MAM,
    # KD2FTA, VA2PGB all checksum-valid only with $2A).
    START_MARKER = 0x2A
    END_MARKER = 0x01  # $01

    # Maximum reasonable callsign length
    MAX_CALLSIGN_LENGTH = 12

    # Timeout: Max time to wait for complete FSKID (3 seconds)
    TIMEOUT_SAMPLES = 48000 * 3

    def __init__(self, sample_rate: int = 48000) -> None:
        """Initialize FSKID decoder.

        Args:
            sample_rate: Audio sample rate (typically 48000 Hz)

        """
        self._sample_rate = sample_rate
        self._bit_samples = int(sample_rate * self.BIT_DURATION_MS / 1000)

        # Preamble state: track consecutive preamble detections
        self._preamble_count = 0
        self._preamble_chunks_remaining = 14  # ~300ms / 22ms

        # Create Goertzel filters for frequency detection
        self._filter_preamble = GoertzelFilter(
            self.PREAMBLE_FREQ, sample_rate, self._bit_samples
        )
        self._filter_mark = GoertzelFilter(
            self.MARK_FREQ, sample_rate, self._bit_samples
        )
        self._filter_space = GoertzelFilter(
            self.SPACE_FREQ, sample_rate, self._bit_samples
        )

        self.reset()

    def reset(self) -> None:
        """Reset decoder state."""
        self._state = "searching"
        self._preamble_count = 0
        self._preamble_chunks_remaining = 14  # ~300ms / 22ms
        self._symbols: list[int] = []
        self._current_bits: list[int] = []
        self._confidence_sum = 0.0
        self._confidence_count = 0

    def decode(self, audio_buffer: np.ndarray) -> FSKIDResult | None:
        """Decode FSKID from audio buffer.

        Args:
            audio_buffer: Audio samples after SSTV image completes

        Returns:
            FSKIDResult if valid FSKID detected, None otherwise

        """
        self.reset()
        offset = 0
        samples_processed = 0

        while offset + self._bit_samples <= len(audio_buffer):
            # Timeout check (max 3 seconds)
            if samples_processed > self.TIMEOUT_SAMPLES:
                logger.debug("FSKID timeout after 3 seconds")
                return None

            chunk = audio_buffer[offset : offset + self._bit_samples]
            self._process_chunk(chunk)

            if self._state == "complete":
                return self._extract_callsign()
            elif self._state == "error":
                return None

            offset += self._bit_samples
            samples_processed += self._bit_samples

        # A leading delay can shift the fixed-size windows and leave the final
        # checksum bit in a partial chunk. Process it when most of a bit is
        # present instead of discarding an otherwise complete frame.
        remaining = audio_buffer[offset:]
        if (
            self._state in ("reading_bits", "reading_checksum")
            and len(remaining) >= self._bit_samples // 2
        ):
            padded = np.pad(remaining, (0, self._bit_samples - len(remaining)))
            self._process_chunk(padded)
            if self._state == "complete":
                return self._extract_callsign()

        # Reached end of buffer without complete FSKID
        logger.debug("FSKID incomplete, no valid callsign detected")
        return None

    def _process_chunk(self, samples: np.ndarray) -> None:
        """Process 22ms audio chunk through state machine.

        State transitions:
        searching → preamble_detected → guard_detected → start_bit_detected
        → reading_bits → complete (or error)
        """
        freq, confidence = self._detect_frequency(samples)

        if self._state == "searching":
            # Look for preamble (1500 Hz or 1900 Hz narrow mode)
            if freq in ("tone_1500", "tone_1900") and confidence > self.DETECTION_THRESHOLD:
                self._preamble_count += 1
                # 300ms / 22ms = ~14 chunks
                if self._preamble_count >= 13:
                    self._state = "preamble_detected"
                    logger.debug("FSKID preamble detected")
            else:
                self._preamble_count = 0

        elif self._state == "preamble_detected":
            # Look for guard tone (2100 Hz)
            if freq == "tone_2100" and confidence > self.DETECTION_THRESHOLD:
                self._state = "guard_detected"
                self._preamble_chunks_remaining = 0  # Preamble done
                logger.debug("FSKID guard tone detected")
            elif freq not in ("tone_1500", "tone_1900"):
                # Lost preamble without guard
                self._state = "searching"
                self._preamble_count = 0
                self._preamble_chunks_remaining = 14

        elif self._state == "guard_detected":
            # Stay in the 2100 Hz guard until the 1900 Hz start bit arrives.
            if freq == "tone_2100" and confidence > self.DETECTION_THRESHOLD:
                return
            if freq == "tone_1900" and confidence > self.DETECTION_THRESHOLD:
                self._state = "start_bit_detected"
                self._current_bits = []
                self._symbols = []
                logger.debug("FSKID start bit detected, reading data")
            else:
                # Guard tone ended without start bit - back to search
                self._state = "searching"

        elif self._state == "start_bit_detected":
            # Begin reading data bits
            self._state = "reading_bits"
            self._process_data_bit(freq, confidence)

        elif self._state in ("reading_bits", "reading_checksum"):
            self._process_data_bit(freq, confidence)

    def _process_data_bit(self, freq: str, confidence: float) -> None:
        """Process a single data bit in symbol stream."""
        if freq in ("tone_1900", "tone_2100"):
            bit = 1 if freq == "tone_1900" else 0
            self._current_bits.append(bit)
            self._confidence_sum += confidence
            self._confidence_count += 1

            # Complete 6-bit symbol?
            if len(self._current_bits) == 6:
                symbol_bits = self._current_bits
                symbol_value = self._bits_to_symbol(symbol_bits)
                self._symbols.append(symbol_value)
                self._current_bits = []

                logger.debug(
                    f"FSKID symbol decoded: 0x{symbol_value:02X} "
                    f"(bits: {''.join(map(str, symbol_bits))})"
                )

                if self._state == "reading_checksum":
                    self._state = "complete"
                    logger.debug(
                        "FSKID checksum received, %d symbols total",
                        len(self._symbols),
                    )
                    return

                # The checksum is one symbol after the end marker.
                if symbol_value == self.END_MARKER:
                    self._state = "reading_checksum"
                    logger.debug("FSKID end marker detected; awaiting checksum")
                    return

                # Safety: Prevent infinite loop from malformed transmission
                if len(self._symbols) > self.MAX_CALLSIGN_LENGTH + 4:
                    logger.warning("FSKID exceeded max length, aborting")
                    self._state = "error"
                    return

        else:
            # Unexpected frequency during data bits
            logger.warning(f"FSKID unexpected frequency '{freq}' during data bits, aborting")
            self._state = "error"

    def _detect_frequency(self, samples: np.ndarray) -> tuple[str, float]:
        """Detect which frequency is dominant in samples.

        Returns:
            (frequency_name, confidence) tuple

        """
        # Return physical tones only. Their protocol meaning depends on state:
        # 1900 Hz is both narrow preamble and mark; 2100 Hz is guard and space.
        magnitudes = {
            "tone_1500": self._filter_preamble.magnitude(samples),
            "tone_1900": self._filter_mark.magnitude(samples),
            "tone_2100": self._filter_space.magnitude(samples),
        }

        max_freq = max(magnitudes, key=magnitudes.__getitem__)
        max_mag = magnitudes[max_freq]
        total_mag = sum(magnitudes.values())

        confidence = max_mag / total_mag if total_mag > 0 else 0.0
        return max_freq, confidence

    def _bits_to_symbol(self, bits: list[int]) -> int:
        """Convert a 6-bit list to its integer value, LSB-first.

        The published MMSSTV spec (fskid.txt) diagrams the symbol as B5
        first, but MMSSTV transmits B0 first. Off-air recordings decide it:
        on 20m captures, three independent stations (XE2MAM, KD2FTA,
        VA2PGB) produce a valid XOR checksum only when the first bit
        received is the least significant. The wire wins over the document.

        Args:
            bits: List of 6 bits in transmission order [B0, B1, ..., B5]

        Returns:
            Integer value 0-63

        """
        value = 0
        for i, bit in enumerate(bits):
            value |= bit << i
        return value

    def _extract_callsign(self) -> FSKIDResult | None:
        """Extract callsign from decoded symbol stream.

        Expected format: [$0A, C1, C2, ..., CN, $01, XSUM]
        - Start marker: $0A ($2A encoded)
        - Characters: ASCII - 0x20
        - End marker: $01
        - Checksum: XOR of all character codes
        """
        if len(self._symbols) < 4:
            logger.warning("FSKID too short (need at least start + 1 char + end + checksum)")
            return None

        # Verify start marker
        if self._symbols[0] != self.START_MARKER:
            logger.warning(
                f"FSKID invalid start marker: 0x{self._symbols[0]:02X} "
                f"(expected 0x{self.START_MARKER:02X})"
            )
            return None

        # Find end marker
        try:
            end_idx = self._symbols.index(self.END_MARKER)
        except ValueError:
            logger.warning("FSKID missing end marker")
            return None

        # Extract character codes (between start and end markers)
        char_codes = self._symbols[1:end_idx]

        if not char_codes:
            logger.warning("FSKID no characters between markers")
            return None

        if end_idx + 1 >= len(self._symbols):
            logger.warning("FSKID missing checksum")
            return None

        checksum_received = self._symbols[end_idx + 1]

        # Calculate expected checksum (XOR of character codes)
        checksum_calculated = 0x00
        for code in char_codes:
            checksum_calculated ^= code

        checksum_valid = checksum_calculated == checksum_received

        if not checksum_valid:
            logger.warning(
                f"FSKID checksum mismatch: "
                f"calculated 0x{checksum_calculated:02X}, "
                f"received 0x{checksum_received:02X}"
            )
            # Continue anyway - might still be usable callsign

        # Convert codes to ASCII callsign
        callsign_chars = []
        for code in char_codes:
            if not (0x00 <= code <= 0x3F):
                logger.warning(f"FSKID invalid character code: 0x{code:02X}")
                return None

            ascii_code = code + 0x20
            # Valid callsign characters: A-Z, 0-9, /
            if not (
                (0x30 <= ascii_code <= 0x39)  # 0-9
                or (0x41 <= ascii_code <= 0x5A)  # A-Z
                or ascii_code == 0x2F  # /
            ):
                logger.warning(
                    f"FSKID invalid callsign character: "
                    f"'{chr(ascii_code)}' (0x{ascii_code:02X})"
                )
                return None

            callsign_chars.append(chr(ascii_code))

        callsign = "".join(callsign_chars)

        # Basic callsign validation (3-12 alphanumeric characters)
        if not (3 <= len(callsign) <= 12):
            logger.warning(f"FSKID callsign length invalid: '{callsign}' ({len(callsign)} chars)")
            return None

        # Calculate confidence score
        avg_confidence = (
            self._confidence_sum / self._confidence_count if self._confidence_count > 0 else 0.0
        )

        # Reduce confidence if checksum invalid
        if not checksum_valid:
            avg_confidence *= 0.7

        logger.info(
            f"FSKID decoded: '{callsign}' "
            f"(confidence: {avg_confidence:.2f}, "
            f"checksum: {'valid' if checksum_valid else 'INVALID'})"
        )

        return FSKIDResult(
            callsign=callsign,
            confidence=avg_confidence,
            checksum_valid=checksum_valid,
            symbols_decoded=len(self._symbols),
        )
