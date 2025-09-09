# SSTV Domain Context

## Core SSTV Knowledge
- **Protocol**: Slow-scan television over audio (analog)
- **Modes**: Scottie S1/S2/DX, Martin M1/M2, Robot 36
- **VIS Codes**: Mode identification at start of transmission
- **Timing Critical**: Audio sample rate and timing precision essential

## colaclanth/sstv Library (NEVER REPLACE)
- **Repository**: https://github.com/colaclanth/sstv
- **Quality**: Produces reference-quality results
- **Integration**: Python subprocess calls via Tauri
- **Streaming**: Progressive image rendering during decode

## Audio Pipeline Architecture
```
Microphone → CPAL → Threaded Capture → WAV File → Python Subprocess → Progressive Image
```

## Common SSTV Issues
- **Timing Drift**: Requires precise audio timing
- **Noise Handling**: Partial signals, interference
- **Mode Detection**: VIS code parsing, fallback strategies
- **Image Quality**: Sync pulse detection, line alignment

## Test Resources
- **MMSSTV Reference**: Known-good reference images in `core/shared/testing/reference/`
- **Essex Ham**: Real-world test signals
- **ARISS**: ISS SSTV transmissions for testing

## Performance Requirements
- **Real-time**: Must process audio without dropouts
- **Progressive**: Show image building line by line
- **File-based**: Current approach uses temporary WAV files
- **Cross-platform**: Must work on macOS, Windows, Linux