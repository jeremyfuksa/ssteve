"""Unit tests for FSKID generator."""

import numpy as np
import pytest

from sstv_core.decode.fsk_decoder import FSKIDDecoder
from sstv_core.encode.fsk_generator import FSKIDGenerator


class TestFSKIDGenerator:
    """Test FSKID generator functionality."""

    @pytest.fixture
    def generator(self):
        """Create generator instance."""
        return FSKIDGenerator(sample_rate=48000)

    def test_generate_simple_callsign(self, generator):
        """Test generating FSKID for simple callsign."""
        audio = generator.generate("K8JTK")

        assert isinstance(audio, np.ndarray)
        assert audio.dtype == np.float32
        assert len(audio) > 0

        # Check audio amplitude (should be ±0.8)
        assert np.max(np.abs(audio)) <= 0.85  # Allow small margin

    def test_generate_various_callsigns(self, generator):
        """Test generating FSKID for various valid callsigns."""
        test_callsigns = [
            "W1AW",
            "VE3XYZ",
            "G4ABC",
            "K8JTK",
            "N5AC",
            "AA1AA",
            "W6AER",
        ]

        for callsign in test_callsigns:
            audio = generator.generate(callsign)
            assert len(audio) > 0
            assert audio.dtype == np.float32

    def test_generate_with_slash(self, generator):
        """Test generating FSKID for portable callsign."""
        audio = generator.generate("G4ABC/P")
        assert len(audio) > 0

    def test_case_insensitive(self, generator):
        """Test that lowercase callsigns are normalized to uppercase."""
        audio1 = generator.generate("k8jtk")
        audio2 = generator.generate("K8JTK")

        # Should generate identical audio
        np.testing.assert_array_equal(audio1, audio2)

    def test_whitespace_stripped(self, generator):
        """Test that whitespace is stripped from callsign."""
        audio1 = generator.generate("  K8JTK  ")
        audio2 = generator.generate("K8JTK")

        np.testing.assert_array_equal(audio1, audio2)

    def test_invalid_empty_callsign(self, generator):
        """Test that empty callsign raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            generator.generate("")

    def test_invalid_too_short(self, generator):
        """Test that too-short callsign raises ValueError."""
        with pytest.raises(ValueError, match="3-12 characters"):
            generator.generate("AB")

    def test_invalid_too_long(self, generator):
        """Test that too-long callsign raises ValueError."""
        with pytest.raises(ValueError, match="3-12 characters"):
            generator.generate("ABCDEFGHIJKLM")  # 13 characters

    def test_invalid_no_letter(self, generator):
        """Test that callsign without letters raises ValueError."""
        with pytest.raises(ValueError, match="at least one letter"):
            generator.generate("123")

    def test_invalid_no_digit(self, generator):
        """Test that callsign without digits raises ValueError."""
        with pytest.raises(ValueError, match="at least one digit"):
            generator.generate("ABCD")

    def test_invalid_special_chars(self, generator):
        """Test that invalid characters raise ValueError."""
        with pytest.raises(ValueError, match="only A-Z, 0-9, and /"):
            generator.generate("K8JTK!")

        with pytest.raises(ValueError, match="only A-Z, 0-9, and /"):
            generator.generate("K8-JTK")

        with pytest.raises(ValueError, match="only A-Z, 0-9, and /"):
            generator.generate("K8 JTK")

    def test_duration_calculation(self, generator):
        """Test FSKID duration calculation."""
        # For "K8JTK" (5 chars):
        # Symbols: start(1) + chars(5) + end(1) + checksum(1) = 8 symbols
        # Duration: preamble(300) + guard(100) + start_bit(22) + 8*6*22 = 1478ms

        duration_ms = generator.get_duration_ms("K8JTK")
        expected_ms = 300 + 100 + 22 + (8 * 6 * 22)  # = 1478
        assert duration_ms == pytest.approx(expected_ms, abs=1)

    def test_duration_samples(self, generator):
        """Test FSKID duration in samples."""
        duration_samples = generator.get_duration_samples("K8JTK")
        duration_ms = generator.get_duration_ms("K8JTK")

        expected_samples = int(48000 * duration_ms / 1000)
        assert duration_samples == expected_samples

    def test_longer_callsign_longer_duration(self, generator):
        """Test that longer callsigns produce longer audio."""
        audio_short = generator.generate("W1AW")  # 4 chars
        audio_long = generator.generate("VE3VERYLONGX")  # 12 chars

        assert len(audio_long) > len(audio_short)

    def test_generated_audio_length_matches_calculation(self, generator):
        """Test that actual audio length matches calculated length."""
        callsign = "K8JTK"  # 5 chars = 9 symbols
        audio = generator.generate(callsign)
        expected_samples = generator.get_duration_samples(callsign)

        # Allow small rounding error
        assert len(audio) == pytest.approx(expected_samples, abs=100)


class TestFSKIDRoundtrip:
    """Test FSKID encode→decode roundtrip."""

    @pytest.fixture
    def generator(self):
        """Create generator instance."""
        return FSKIDGenerator(sample_rate=48000)

    @pytest.fixture
    def decoder(self):
        """Create decoder instance."""
        return FSKIDDecoder(sample_rate=48000)

    def test_roundtrip_simple(self, generator, decoder):
        """Test encode→decode roundtrip for simple callsign."""
        original = "K8JTK"

        # Generate FSKID audio
        audio = generator.generate(original)

        # Decode it back
        result = decoder.decode(audio)

        assert result is not None
        assert result.callsign == original
        assert result.checksum_valid is True
        assert result.confidence > 0.8

    def test_roundtrip_various_callsigns(self, generator, decoder):
        """Test roundtrip for multiple callsigns."""
        test_callsigns = [
            "W1AW",
            "VE3XYZ",
            "G4ABC",
            "K8JTK",
            "N5AC",
            "AA1AA",
            "W6AER",
            "G4ABC/P",
        ]

        for callsign in test_callsigns:
            audio = generator.generate(callsign)
            result = decoder.decode(audio)

            assert result is not None, f"Decode failed for {callsign}"
            assert result.callsign == callsign
            assert result.checksum_valid is True

    def test_roundtrip_with_noise(self, generator, decoder):
        """Test encode→decode roundtrip with added noise."""
        original = "K8JTK"

        # Generate clean audio
        audio = generator.generate(original)

        # Add white noise (SNR ~15dB)
        noise = np.random.randn(len(audio)).astype(np.float32) * 0.15
        noisy_audio = audio + noise

        # Decode noisy audio
        result = decoder.decode(noisy_audio)

        # Should still decode despite noise
        assert result is not None
        assert result.callsign == original
        # Checksum might fail with noise, but callsign should be correct

    def test_roundtrip_max_length(self, generator, decoder):
        """Test roundtrip for maximum length callsign."""
        original = "VE3VERYLONGX"  # 12 characters

        audio = generator.generate(original)
        result = decoder.decode(audio)

        assert result is not None
        assert result.callsign == original
        assert result.checksum_valid is True

    def test_roundtrip_with_silence_before(self, generator, decoder):
        """Test roundtrip with silence before FSKID (realistic scenario)."""
        original = "W1AW"

        # Add 1 second silence before (simulating end of SSTV image)
        silence = np.zeros(48000, dtype=np.float32)
        fskid_audio = generator.generate(original)
        audio = np.concatenate([silence, fskid_audio])

        result = decoder.decode(audio)

        assert result is not None
        assert result.callsign == original
        assert result.checksum_valid is True

    def test_roundtrip_multiple_decodes(self, generator, decoder):
        """Test that generator and decoder can be reused."""
        callsigns = ["K8JTK", "W1AW", "VE3XYZ"]

        for callsign in callsigns:
            audio = generator.generate(callsign)
            result = decoder.decode(audio)

            assert result is not None
            assert result.callsign == callsign
