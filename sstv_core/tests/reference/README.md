# SSTV Reference Test Assets

This directory contains reference audio recordings and expected output images for validating the SSTeVe SSTV decoder/encoder implementation.

## Audio Files

### MMSSTV Reference Quality (Primary Validation Set)
**Source:** Professional MMSSTV software recordings
**Format:** 22,050 Hz, 16-bit mono WAV
**Mode:** Scottie S1
**Use:** Primary validation baseline for decoder accuracy

- `mmsstv/scottie_s1_bear_je3hht.wav` (2.5 MB)
- `mmsstv/scottie_s1_elk_forest.wav` (2.5 MB)
- `mmsstv/scottie_s1_operator_shack.wav` (2.5 MB)
- `mmsstv/scottie_s1_radio_desk.wav` (2.5 MB)
- `mmsstv/scottie_s1_winter_creek.wav` (2.5 MB)

### EssexHAM Educational Samples
**Source:** EssexHAM amateur radio club educational recordings
**Modes:** Martin M2, Scottie S2
**Use:** Multi-mode validation, educational testing

- `essexham/martin_m2_*.wav` (2x files, ~2.6 MB each)
- `essexham/scottie_s2_*.wav` (2x files, ~3.1 MB each)

### ARISS/ISS Live Recordings
**Source:** Real International Space Station SSTV transmissions
**Quality:** Variable (realistic field conditions)
**Use:** Real-world signal validation, noise tolerance testing

- `ariss/iss_*.wav` (6x files, 5-6 MB each)

**Total Audio:** ~67 MB across 16 files

## Reference Images

### MMSSTV Expected Outputs
**Source:** MMSSTV software ground truth
**Format:** JPG
**Use:** Pixel-perfect validation of decoder output

- `mmsstv/scottie_s1_*.jpg` (5 reference images, 20-32 KB each)
- `mmsstv/color_bars.jpg` (4 KB test pattern)
- `mmsstv/mmsstv_screenshot.png` (software reference)

### EssexHAM Expected Outputs
**Source:** Educational reference images
**Format:** PNG
**Use:** Multi-mode decoder validation

- `essexham/martin_m2_*.png` (2 images, ~105-117 KB)
- `essexham/scottie_s2_*.png` (2 images, ~111-116 KB)

### ARISS Expected Outputs
**Source:** ISS crew photos and Earth views
**Format:** JPG
**Use:** Real-world decode validation

- `ariss/iss_*.jpg` (8 images, 98-226 KB each)

**Total Images:** 19 reference files

## Usage in Tests

### Validation Testing Pattern

```python
import pytest
from pathlib import Path
from sstv_core.decode.scottie_decoder import ScottieS1Decoder

REFERENCE_AUDIO = Path(__file__).parent / "reference" / "audio"
REFERENCE_IMAGES = Path(__file__).parent / "reference" / "images"

def test_scottie_s1_decode_accuracy():
    """Validate decoder against MMSSTV reference."""
    audio_file = REFERENCE_AUDIO / "mmsstv" / "scottie_s1_bear_je3hht.wav"
    expected_image = REFERENCE_IMAGES / "mmsstv" / "scottie_s1_bear_je3hht.jpg"

    decoder = ScottieS1Decoder()
    result = decoder.decode(audio_file)

    # Compare pixel similarity (allow minor differences)
    assert image_similarity(result, expected_image) > 0.95
```

### Integration Testing

Use these files for:
- End-to-end decode pipeline testing
- Signal quality estimation validation
- VIS code detection accuracy
- Sync pulse tracking accuracy
- Multi-mode decoder validation
- Real-world noise tolerance testing

## Credits

- **MMSSTV:** Makoto Mori, JE3HHT (MMSSTV software)
- **EssexHAM:** Essex Amateur Radio Club educational materials
- **ARISS:** Amateur Radio on International Space Station program

## License

These reference files are used for testing purposes only. Original copyright holders retain all rights.
