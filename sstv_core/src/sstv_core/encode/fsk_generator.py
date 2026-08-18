"""FSKID (FSK Identification) generator for MMSSTV-compatible callsign transmission.

Generates FSK-modulated callsign data to append after SSTV images.
Compatible with MMSSTV FSKID standard (JE3HHT).
"""

from __future__ import annotations

import logging
import re

import numpy as np

logger = logging.getLogger(__name__)


class FSKIDGenerator:
    """Generates MMSSTV-compatible FSKID audio for callsign transmission.

    FSKID Protocol (MMSSTV Standard):
    - Preamble: 1500 Hz for 300ms
    - Guard: 2100 Hz for 100ms
    - Start bit: 1900 Hz for 22ms
    - Data bits: 6 bits per symbol, 22ms each, MSB-first
      - Mark (1): 1900 Hz
      - Space (0): 2100 Hz
    - Frame: [Start $2A] [Callsign chars] [End $01] [Checksum XOR]
    - ASCII mapping: $20-$5F → $00-$3F (subtract 0x20)
    """

    # Frequency constants
    PREAMBLE_FREQ = 1500.0
    GUARD_FREQ = 2100.0
    MARK_FREQ = 1900.0  # Bit = 1
    SPACE_FREQ = 2100.0  # Bit = 0

    # Timing constants
    PREAMBLE_DURATION_MS = 300
    GUARD_DURATION_MS = 100
    START_BIT_DURATION_MS = 22
    BIT_DURATION_MS = 22

    # Protocol constants
    # Literal $2A from the MMSSTV spec frame "$2A C1 ... CN $01 XSUM".
    # The $20 subtraction applies to the callsign characters only.
    START_MARKER = 0x2A
    END_MARKER = 0x01  # $01

    def __init__(self, sample_rate: int = 48000):
        """Initialize FSKID generator.

        Args:
            sample_rate: Audio sample rate (typically 48000 Hz)

        """
        self._sample_rate = sample_rate

    def generate(self, callsign: str) -> np.ndarray:
        """Generate complete FSKID audio for callsign.

        Args:
            callsign: Operator callsign (3-12 characters, alphanumeric + slash)

        Returns:
            Audio samples ready to append after SSTV image

        Raises:
            ValueError: If callsign format is invalid

        """
        # Validate and normalize callsign
        callsign = callsign.upper().strip()
        self._validate_callsign(callsign)

        audio_parts = []

        # 1. Preamble (1500 Hz, 300ms)
        audio_parts.append(self._generate_tone(self.PREAMBLE_FREQ, self.PREAMBLE_DURATION_MS))

        # 2. Guard (2100 Hz, 100ms)
        audio_parts.append(self._generate_tone(self.GUARD_FREQ, self.GUARD_DURATION_MS))

        # 3. Start bit (1900 Hz, 22ms)
        audio_parts.append(self._generate_tone(self.MARK_FREQ, self.START_BIT_DURATION_MS))

        # 4. Encode callsign as symbols
        symbols = self._encode_callsign(callsign)

        # 5. Generate FSK audio for each bit of each symbol
        for symbol in symbols:
            bits = self._symbol_to_bits(symbol)
            for bit in bits:
                freq = self.MARK_FREQ if bit == 1 else self.SPACE_FREQ
                audio_parts.append(self._generate_tone(freq, self.BIT_DURATION_MS))

        result = np.concatenate(audio_parts)
        duration_sec = len(result) / self._sample_rate

        logger.info(
            f"Generated FSKID for '{callsign}': "
            f"{len(result)} samples ({duration_sec:.2f} sec), "
            f"{len(symbols)} symbols"
        )

        return result

    def _validate_callsign(self, callsign: str) -> None:
        """Validate callsign format.

        Args:
            callsign: Callsign to validate

        Raises:
            ValueError: If callsign is invalid

        """
        if not callsign:
            raise ValueError("Callsign cannot be empty")

        # Length check (3-12 characters)
        if not (3 <= len(callsign) <= 12):
            raise ValueError(
                f"Callsign length must be 3-12 characters, got {len(callsign)}: '{callsign}'"
            )

        # Character validation: A-Z, 0-9, / only
        if not re.match(r"^[A-Z0-9/]+$", callsign):
            raise ValueError(
                f"Callsign must contain only A-Z, 0-9, and / characters: '{callsign}'"
            )

        # Basic structure validation (at least one letter and one number)
        if not any(c.isalpha() for c in callsign):
            raise ValueError(f"Callsign must contain at least one letter: '{callsign}'")

        if not any(c.isdigit() for c in callsign):
            raise ValueError(f"Callsign must contain at least one digit: '{callsign}'")

    def _encode_callsign(self, callsign: str) -> list[int]:
        """Convert callsign to symbol list with framing and checksum.

        Args:
            callsign: Validated callsign string

        Returns:
            List of 6-bit symbol values

        Example:
            "K8JTK" → [$0A, $2B, $18, $2A, $34, $2B, $01, XSUM]

        """
        symbols = [self.START_MARKER]  # Start marker

        # Convert each character
        xsum = 0x00
        for char in callsign:
            ascii_code = ord(char)

            # Validate ASCII range for FSKID encoding
            if not (0x20 <= ascii_code <= 0x5F):
                raise ValueError(
                    f"Character '{char}' (0x{ascii_code:02X}) "
                    f"out of FSKID encoding range (0x20-0x5F)"
                )

            # Encode: ASCII - 0x20 → 0x00-0x3F
            encoded = ascii_code - 0x20
            symbols.append(encoded)
            xsum ^= encoded

        symbols.append(self.END_MARKER)  # End marker
        symbols.append(xsum)  # Checksum

        logger.debug(
            f"FSKID encoding '{callsign}': "
            f"symbols=[{', '.join(f'0x{s:02X}' for s in symbols)}], "
            f"checksum=0x{xsum:02X}"
        )

        return symbols

    def _symbol_to_bits(self, symbol: int) -> list[int]:
        """Convert a 6-bit symbol to its bit list in transmission order.

        LSB-first, matching what MMSSTV actually puts on the air (see
        FSKIDDecoder._bits_to_symbol for the off-air evidence).

        Args:
            symbol: Integer value 0-63

        Returns:
            List of 6 bits in transmission order [B0, B1, ..., B5]

        Example:
            0x2B (43) → [1, 1, 0, 1, 0, 1]

        """
        if not (0x00 <= symbol <= 0x3F):
            raise ValueError(f"Symbol value must be 0-63, got {symbol}")

        bits = [(symbol >> i) & 1 for i in range(6)]
        return bits

    def _generate_tone(self, freq: float, duration_ms: float) -> np.ndarray:
        """Generate sine wave at specified frequency.

        Args:
            freq: Frequency in Hz
            duration_ms: Duration in milliseconds

        Returns:
            Audio samples (float32, normalized to ±0.8)

        """
        num_samples = int(self._sample_rate * duration_ms / 1000)
        t = np.arange(num_samples) / self._sample_rate
        # Amplitude 0.8 to avoid clipping, leave headroom
        return (np.sin(2 * np.pi * freq * t) * 0.8).astype(np.float32)

    def get_duration_ms(self, callsign: str) -> float:
        """Calculate total FSKID duration for transmission planning.

        Args:
            callsign: Callsign to calculate duration for

        Returns:
            Duration in milliseconds

        """
        # Validate first
        callsign = callsign.upper().strip()
        self._validate_callsign(callsign)

        # Calculate symbol count: start + chars + end + checksum
        num_symbols = len(callsign) + 3

        # Duration calculation
        duration = (
            self.PREAMBLE_DURATION_MS
            + self.GUARD_DURATION_MS
            + self.START_BIT_DURATION_MS
            + (num_symbols * 6 * self.BIT_DURATION_MS)
        )

        return duration

    def get_duration_samples(self, callsign: str) -> int:
        """Calculate total FSKID duration in samples.

        Args:
            callsign: Callsign to calculate duration for

        Returns:
            Duration in samples

        """
        duration_ms = self.get_duration_ms(callsign)
        return int(self._sample_rate * duration_ms / 1000)
