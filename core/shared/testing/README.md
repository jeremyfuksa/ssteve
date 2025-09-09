# SSTV Testing Framework

This directory contains all test assets and scripts for the SSTV decoder engine.

## Directory Structure

```
testing/
├── reference/               # Reference test files and expected outputs
│   ├── audio/               # SSTV audio test files organized by source
│   │   ├── mmsstv/          # MMSSTV reference quality test files
│   │   │   ├── scottie_s1_bear_je3hht.wav        # Bear image (Scottie S1)
│   │   │   ├── scottie_s1_elk_forest.wav         # Elk forest (Scottie S1)
│   │   │   ├── scottie_s1_operator_shack.wav     # Operator shack (Scottie S1)
│   │   │   ├── scottie_s1_radio_desk.wav         # Radio desk (Scottie S1)
│   │   │   └── scottie_s1_winter_creek.wav       # Winter creek (Scottie S1)
│   │   ├── essexham/        # EssexHAM educational samples
│   │   │   ├── essexham_01_martin2.wav           # Martin 2 mode
│   │   │   ├── essexham_02_martin2.wav           # Martin 2 mode
│   │   │   ├── essexham_01_scottie2.wav          # Scottie 2 mode  
│   │   │   └── essexham_02_scottie2.wav          # Scottie 2 mode
│   │   └── ariss/           # ARISS/ISS SSTV recordings
│   │       ├── ariss-20201004-1445.wav           # ISS SSTV transmission
│   │       ├── ariss-20201004-1620.wav           # ISS SSTV transmission
│   │       └── partial-ariss-*.wav               # Partial ISS recordings
│   ├── images/              # Expected output images organized by source
│   │   ├── mmsstv/          # MMSSTV reference standard
│   │   │   ├── reference_mmsstv_scottie_s1_*.jpg # Expected outputs (5 files)
│   │   │   ├── mmsstv.png                        # MMSSTV software screenshot
│   │   │   └── tn_colour-bars.jpg                # Color test pattern
│   │   ├── essexham/        # EssexHAM reference images
│   │   │   ├── essexham_01_martin2.png           # Martin 2 expected output
│   │   │   ├── essexham_02_martin2.png           # Martin 2 expected output
│   │   │   ├── essexham_01_scottie2.png          # Scottie 2 expected output
│   │   │   └── essexham_02_scottie2.png          # Scottie 2 expected output
│   │   └── ariss/           # ARISS reference images
│   │       └── ariss-*.jpg                       # ISS SSTV decoded images
│   └── new-images/          # Additional test images for encoding
│       ├── brr-brr-patapim.png                   # Test image
│       ├── monkey-washing-cat.png                # Test image
│       └── potatoes.png                          # Test image
├── results/                 # Test output images
│   ├── decode/              # Decoded image outputs
│   ├── encode/              # Encoded audio outputs
│   └── roundtrip/           # Round-trip test results
└── scripts/                 # Test scripts
    ├── integration_test.js  # Full engine integration test
    ├── roundtrip_test.js    # Round-trip encode/decode tests
    └── engine_test.js       # Unit tests for engine components
```

## Test Assets

## Test Asset Categories

### MMSSTV Reference Quality (Primary Tests)
**Location**: `testing/reference/audio/mmsstv/` | `testing/reference/images/mmsstv/`

- `scottie_s1_bear_je3hht.wav` - Bear image test (Scottie S1)
- `scottie_s1_elk_forest.wav` - Elk in forest test (Scottie S1)
- `scottie_s1_operator_shack.wav` - Radio operator test (Scottie S1)
- `scottie_s1_radio_desk.wav` - Radio desk test (Scottie S1)
- `scottie_s1_winter_creek.wav` - Winter creek test (Scottie S1)

**Format**: WAV, 16-bit, 22050 Hz, mono  
**Quality**: Reference-grade files with corresponding MMSSTV expected outputs  
**Purpose**: Primary validation against industry standard MMSSTV software

### EssexHAM Educational Samples
**Location**: `testing/audio/essexham/` | `testing/reference/essexham/`

- `essexham_01_martin2.wav` - Martin 2 mode educational sample
- `essexham_02_martin2.wav` - Martin 2 mode educational sample  
- `essexham_01_scottie2.wav` - Scottie 2 mode educational sample
- `essexham_02_scottie2.wav` - Scottie 2 mode educational sample

**Format**: WAV, 16-bit, 22050 Hz, mono (converted from original MP3)  
**Source**: https://www.essexham.co.uk/sstv-the-basics  
**Purpose**: Multi-mode testing (Martin 2, Scottie 2)

### ARISS/ISS Live Recordings
**Location**: `testing/audio/ariss/` | `testing/reference/ariss/`

- `ariss-20201004-1445.wav` - ISS SSTV transmission recording
- `ariss-20201004-1620.wav` - ISS SSTV transmission recording
- `partial-ariss-*.wav` - Partial ISS recordings for testing

**Format**: WAV, 16-bit, 22050 Hz, mono (converted from original M4A)  
**Source**: ARISS (Amateur Radio on International Space Station)  
**Content**: ISS crew photos, Earth views, space station imagery  
**Purpose**: Real-world signal testing with varying quality  
**Note**: Some files may contain unsupported SSTV modes

### SSTV Mode Coverage
The organized test suite covers:
- **Scottie S1**: 5 reference-quality WAV files (mmsstv/)
- **Martin 2**: 2 educational WAV files (essexham/)
- **Scottie 2**: 2 educational WAV files (essexham/)  
- **Mixed modes**: Real ISS WAV recordings (ariss/)

## Audio Format Support

**Supported Input Format:**
- **WAV**: Native support (16-bit, 22050 Hz, mono recommended)

**Format Migration:**
All test files have been converted to WAV format to eliminate audio artifacts and ensure consistent decoding quality. Original MP3/M4A files contained compression artifacts that degraded round-trip testing quality.

**For New Test Files:**
Convert to WAV format using:
```bash
# macOS (afconvert)
afconvert input.mp3 output.wav -d LEI16 -r 22050 -c 1

# Cross-platform (ffmpeg)  
ffmpeg -i input.mp3 -ar 22050 -ac 1 -sample_fmt s16 output.wav
```

## Running Tests

```bash
# Full integration test suite
npm test

# Engine unit tests only
npm run test:engine

# Test specific file
node testing/scripts/integration_test.js

# Manual test with specific audio file
node examples/simple_example.js testing/audio/mmsstv/scottie_s1_bear_je3hht.wav output.png
```

## Test Results Cleanup

Test results are automatically ignored by git but can accumulate over time. Use these commands to manage them:

```bash
# Smart cleanup (keeps recent files, removes old ones)
npm run test:clean

# Complete cleanup (removes all generated results)
npm run test:clean-all

# Manual cleanup script with options
node testing/scripts/cleanup_results.js
```

**Cleanup Policy:**
- Removes files older than 7 days
- Keeps only 50 most recent files
- Preserves historical evaluation results (`colaclanth-sstv/`)
- Reports space saved and files cleaned

## Test Results

All tests should achieve:
- ✅ **100% decode success rate** on primary test files
- ✅ **Reference-quality output** matching MMSSTV standard
- ✅ **Correct mode detection** (Scottie S1, Martin M1, etc.)
- ✅ **Performance** under 5 seconds per decode

## Quality Standards

The colaclanth/sstv engine produces outputs that:
- Match MMSSTV reference images pixel-perfect or near-perfect
- Correctly identify VIS codes and SSTV modes
- Handle various audio formats and quality levels
- Provide real-time progress reporting during decode

## Historical Results

The `results/colaclanth-sstv/` directory contains outputs from our library evaluation phase, demonstrating the superior quality of the chosen colaclanth/sstv library compared to custom implementations.

## Notes

- All test files use 16-bit 22050Hz WAV format
- Reference images are 24-bit color JPEG/PNG
- Test framework validates file existence, decode success, and output quality
- Engine is configured for maximum compatibility across platforms