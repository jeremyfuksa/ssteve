"""Unit tests for FSKID decoder."""

import numpy as np
import pytest

from sstv_core.decode.fsk_decoder import FSKIDDecoder, FSKIDResult


class TestFSKIDDecoder:
    """Test FSKID decoder functionality."""

    @pytest.fixture
    def decoder(self):
        """Create decoder instance."""
        return FSKIDDecoder(sample_rate=48000)

    def _generate_tone(
        self, freq: float, duration_ms: float, sample_rate: int = 48000
    ) -> np.ndarray:
        """Generate sine wave tone for testing."""
        num_samples = int(sample_rate * duration_ms / 1000)
        t = np.arange(num_samples) / sample_rate
        return (np.sin(2 * np.pi * freq * t) * 0.8).astype(np.float32)

    def _generate_fskid_audio(
        self, callsign: str, sample_rate: int = 48000
    ) -> np.ndarray:
        """Generate complete FSKID audio for testing.

        Implements MMSSTV FSKID protocol:
        - Preamble (1500 Hz, 300ms)
        - Guard (2100 Hz, 100ms)
        - Start bit (1900 Hz, 22ms)
        - Data symbols (6 bits each, 22ms per bit)
        - End marker + checksum
        """
        audio_parts = []

        # Preamble
        audio_parts.append(self._generate_tone(1500.0, 300, sample_rate))

        # Guard
        audio_parts.append(self._generate_tone(2100.0, 100, sample_rate))

        # Start bit
        audio_parts.append(self._generate_tone(1900.0, 22, sample_rate))

        # Encode callsign to symbols
        symbols = [0x2A]  # Start marker: the literal $2A from the spec frame

        # Convert callsign characters
        xsum = 0x00
        for char in callsign.upper():
            encoded = ord(char) - 0x20
            symbols.append(encoded)
            xsum ^= encoded

        symbols.append(0x01)  # End marker
        symbols.append(xsum)  # Checksum

        # Generate FSK audio for each symbol
        for symbol in symbols:
            # Convert symbol to 6 bits in transmission order (LSB-first,
            # matching what MMSSTV puts on the air)
            bits = [(symbol >> i) & 1 for i in range(6)]

            # Generate tone for each bit
            for bit in bits:
                freq = 1900.0 if bit == 1 else 2100.0
                audio_parts.append(self._generate_tone(freq, 22, sample_rate))

        return np.concatenate(audio_parts)

    def test_decode_simple_callsign(self, decoder):
        """Test decoding simple callsign 'K8JTK'."""
        audio = self._generate_fskid_audio("K8JTK")
        result = decoder.decode(audio)

        assert result is not None
        assert result.callsign == "K8JTK"
        assert result.checksum_valid is True
        assert result.confidence > 0.8  # Should be high for clean signal

    def test_decode_various_callsigns(self, decoder):
        """Test decoding various valid callsign formats."""
        test_callsigns = [
            "W1AW",  # 4 characters
            "VE3XYZ",  # 6 characters
            "G4ABC",  # 5 characters
            "K8JTK",  # 5 characters with digit in middle
            "N5AC",  # 4 characters
            "AA1AA",  # Repeated characters
            "W6AER",  # Mix of letters/numbers
        ]

        for callsign in test_callsigns:
            audio = self._generate_fskid_audio(callsign)
            result = decoder.decode(audio)

            assert result is not None, f"Failed to decode {callsign}"
            assert result.callsign == callsign
            assert result.checksum_valid is True

    def test_decode_with_slash(self, decoder):
        """Test decoding callsign with slash (portable operation)."""
        audio = self._generate_fskid_audio("G4ABC/P")
        result = decoder.decode(audio)

        assert result is not None
        assert result.callsign == "G4ABC/P"
        assert result.checksum_valid is True

    def test_no_fskid_present(self, decoder):
        """Test with audio containing no FSKID signal."""
        # Generate random noise
        audio = np.random.randn(48000 * 2).astype(np.float32) * 0.1
        result = decoder.decode(audio)

        assert result is None

    def test_partial_fskid(self, decoder):
        """Test with incomplete FSKID (cut off mid-transmission)."""
        # Generate full FSKID but truncate before end
        audio = self._generate_fskid_audio("K8JTK")
        truncated = audio[: len(audio) // 2]  # Cut in half

        result = decoder.decode(truncated)
        assert result is None

    def test_corrupted_checksum(self, decoder):
        """Test FSKID with invalid checksum."""
        # Generate valid FSKID
        audio = self._generate_fskid_audio("K8JTK")

        # Corrupt the first checksum bit by changing its frequency. A phase
        # inversion alone would preserve the FSK tone and remain valid.
        # Last symbol = 6 bits × 1056 samples = 6336 samples
        checksum_start = len(audio) - (6 * 1056)
        audio[checksum_start : checksum_start + 1056] = self._generate_tone(
            1900.0,
            22,
        )

        result = decoder.decode(audio)

        # Should still decode callsign but flag invalid checksum
        assert result is not None
        assert result.callsign == "K8JTK"
        assert result.checksum_valid is False
        assert result.confidence < 0.8  # Reduced confidence

    def test_missing_start_marker(self, decoder):
        """Test FSKID with wrong start marker."""
        audio_parts = []

        # Preamble + guard + start bit
        audio_parts.append(self._generate_tone(1500.0, 300))
        audio_parts.append(self._generate_tone(2100.0, 100))
        audio_parts.append(self._generate_tone(1900.0, 22))

        # Wrong start marker (use 0x00 instead of 0x0A)
        symbols = [0x00] + [ord(c) - 0x20 for c in "K8JTK"] + [0x01, 0x00]

        for symbol in symbols:
            bits = [(symbol >> (5 - i)) & 1 for i in range(6)]
            for bit in bits:
                freq = 1900.0 if bit == 1 else 2100.0
                audio_parts.append(self._generate_tone(freq, 22))

        audio = np.concatenate(audio_parts)
        result = decoder.decode(audio)

        assert result is None  # Should reject due to invalid start marker

    def test_timeout(self, decoder):
        """Test FSKID timeout after 3 seconds."""
        # Generate 5 seconds of preamble (should timeout)
        audio = self._generate_tone(1500.0, 5000)  # 5 seconds

        result = decoder.decode(audio)
        assert result is None  # Should timeout and return None

    def test_noise_resilience(self, decoder):
        """Test FSKID decoding with added noise."""
        # Generate clean FSKID
        audio = self._generate_fskid_audio("K8JTK")

        # Add white noise (SNR ~15dB)
        noise = np.random.randn(len(audio)).astype(np.float32) * 0.15
        noisy_audio = audio + noise

        result = decoder.decode(noisy_audio)

        # Should still decode despite noise
        assert result is not None
        assert result.callsign == "K8JTK"
        # Confidence may be lower due to noise
        assert result.confidence > 0.5

    def test_narrow_mode_preamble(self, decoder):
        """Test FSKID with narrow mode preamble (1900 Hz)."""
        audio_parts = []

        # Narrow mode: 1900 Hz preamble instead of 1500 Hz
        audio_parts.append(self._generate_tone(1900.0, 300))
        audio_parts.append(self._generate_tone(2100.0, 100))
        audio_parts.append(self._generate_tone(1900.0, 22))

        # Encode "W1AW"
        symbols = [0x2A]
        xsum = 0x00
        for char in "W1AW":
            encoded = ord(char) - 0x20
            symbols.append(encoded)
            xsum ^= encoded
        symbols.append(0x01)
        symbols.append(xsum)

        for symbol in symbols:
            bits = [(symbol >> i) & 1 for i in range(6)]
            for bit in bits:
                freq = 1900.0 if bit == 1 else 2100.0
                audio_parts.append(self._generate_tone(freq, 22))

        audio = np.concatenate(audio_parts)
        result = decoder.decode(audio)

        assert result is not None
        assert result.callsign == "W1AW"
        assert result.checksum_valid is True

    def test_max_length_callsign(self, decoder):
        """Test maximum length callsign (12 characters)."""
        # 12-char callsign (at upper limit)
        audio = self._generate_fskid_audio("VE3VERYLONGX")
        result = decoder.decode(audio)

        assert result is not None
        assert result.callsign == "VE3VERYLONGX"

    def test_invalid_length_callsign(self, decoder):
        """Test callsign that's too short."""
        # Generate FSKID for 2-char callsign (invalid)
        audio_parts = []
        audio_parts.append(self._generate_tone(1500.0, 300))
        audio_parts.append(self._generate_tone(2100.0, 100))
        audio_parts.append(self._generate_tone(1900.0, 22))

        symbols = [0x0A, ord('A') - 0x20, ord('B') - 0x20, 0x01, 0x00]

        for symbol in symbols:
            bits = [(symbol >> (5 - i)) & 1 for i in range(6)]
            for bit in bits:
                freq = 1900.0 if bit == 1 else 2100.0
                audio_parts.append(self._generate_tone(freq, 22))

        audio = np.concatenate(audio_parts)
        result = decoder.decode(audio)

        assert result is None  # Too short (need 3+ chars)

    def test_fskid_after_silence(self, decoder):
        """Test FSKID detection after initial silence (realistic scenario)."""
        # Add 1 second of silence before FSKID (simulating end of SSTV image)
        silence = np.zeros(48000, dtype=np.float32)
        fskid_audio = self._generate_fskid_audio("K8JTK")
        audio = np.concatenate([silence, fskid_audio])

        result = decoder.decode(audio)

        assert result is not None
        assert result.callsign == "K8JTK"
        assert result.checksum_valid is True

    def test_reset_between_decodes(self, decoder):
        """Test that decoder can be reused for multiple decodes."""
        # Decode first callsign
        audio1 = self._generate_fskid_audio("K8JTK")
        result1 = decoder.decode(audio1)
        assert result1 is not None
        assert result1.callsign == "K8JTK"

        # Decode second callsign (decoder should reset internally)
        audio2 = self._generate_fskid_audio("W1AW")
        result2 = decoder.decode(audio2)
        assert result2 is not None
        assert result2.callsign == "W1AW"

    def test_fskid_result_to_dict(self):
        """Test FSKIDResult serialization to dict."""
        result = FSKIDResult(
            callsign="K8JTK",
            confidence=0.92,
            checksum_valid=True,
            symbols_decoded=8,
        )

        result_dict = result.to_dict()

        assert result_dict["callsign"] == "K8JTK"
        assert result_dict["confidence"] == 0.92
        assert result_dict["checksum_valid"] is True
        assert result_dict["symbols_decoded"] == 8
