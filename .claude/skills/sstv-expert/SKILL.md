---
name: sstv-expert
description: >
  Use this skill for SSTV protocol and DSP knowledge while working in SSTeVe —
  mode identification, VIS structure, frequency mapping, timing recovery, and
  which DSP approach suits which stage. Triggers on: SSTV, MMSSTV, QSSTV, VIS
  code, Scottie S1/S2/DX, Martin M1/M2, Robot 36/72, PD modes, sync pulse,
  slant correction, AFC, "what mode is this", "how long is a Martin M1", or
  any question about how the signal itself is structured. This is reference
  knowledge about the protocol; for verifying a decode change use
  ssteve-decode-verification, and for a quiet receiver use sstv-rf-diagnosis.
---

# SSTV Signal Architect

## SSTV Fundamentals

Slow Scan Television encodes images as audio frequency modulations. The receiver maps audio frequencies to pixel luminance values and reconstructs an image line by line.

**Core frequency mapping (all modes):**
- 1200 Hz: Sync pulse
- 1500 Hz: Black (minimum luminance)
- 2300 Hz: White (maximum luminance)
- Everything between: linear mapping to gray/color values

**VIS (Vertical Interval Signaling):** The header that identifies the mode. 300ms leader tone (1900 Hz) + break (1200 Hz) + start bit + 8 mode bits + parity bit + stop bit. Decoding VIS correctly is how you identify the incoming mode before trying to decode image data.

## SSTV Modes Reference

| Mode | Lines | Duration | Color | Primary Use |
|------|-------|----------|-------|-------------|
| Scottie S1 | 256 | 110s | RGB | General purpose, most common |
| Scottie S2 | 256 | 71s | RGB | Faster version of S1 |
| Scottie DX | 256 | 269s | RGB | Maximum quality, slow |
| Martin M1 | 256 | 114s | RGB | Common in Europe |
| Martin M2 | 256 | 58s | RGB | Faster Martin |
| Robot 36 | 240 | 36s | YCrCb | Fast, emergency comms |
| Robot 72 | 240 | 72s | YCrCb | Better quality than R36 |
| PD 50 | 256 | 50s | YCrCb | Balance of speed and quality |
| PD 90 | 256 | 90s | YCrCb | Good general use |
| PD 120 | 496 | 120s | YCrCb | Higher resolution |
| PD 180 | 496 | 180s | YCrCb | High quality, slow |
| PD 240 | 496 | 240s | YCrCb | Maximum PD quality |

## DSP Implementation

**Frequency detection approaches (in order of accuracy):**

1. **Goertzel algorithm** — efficient single-frequency detection, best for sync pulse identification
2. **FFT-based** — good for scanning across the full frequency range, frame-by-frame
3. **PLL (Phase-Locked Loop)** — continuous tracking of the instantaneous frequency, best for image decoding
4. **Hilbert transform / analytic signal** — instantaneous frequency via phase derivative, computationally efficient

For production SSTV decoders, the combination approach works best: FFT for VIS detection and mode identification, PLL for image data decoding.

**Audio preprocessing pipeline:**
1. Resample to known rate (typically 8kHz or 22050Hz)
2. Normalize amplitude
3. Bandpass filter (1000-2500 Hz) to reject out-of-band noise
4. Apply LMS adaptive filter if noise rejection is needed
5. Feed to frequency detector

**Timing recovery:** SSTV is critically timing-sensitive. The sync pulse at 1200 Hz provides the timing reference. Drift accumulates — implement AFC (Automatic Frequency Control) and slant correction. MMSSTV uses a least-squares method for slant correction that's worth studying.

## Where this lives in SSTeVe

The engine is Python, headless, and UI-agnostic (`sstv_core/src/sstv_core/`):

```
decode/   rx_manager, per-mode decoders, vis_detector,
          correlation_vis_detector, sync_detector, hough_slant_corrector
encode/   tx_manager, per-mode encoders, vis_generator, fsk_generator
sdr/      source, demodulator, spyserver/, audio_stream, audio_recorder
audio/    stream_manager, bandpass_filter, ring_buffer, ptt_controller
```

Mode timing constants live on the decoder config classes — `ScottieS1Config`,
`ScottieS2Config`, `MartinM1Config`, `MartinM2Config`. When this file and the
code disagree about a number, **the code is truth**: check the config class
before quoting the table above.

Live display is line-by-line by design (PRODUCT.md: "Scanlines render as they
arrive, with no buffering delay"), but the pixel-delivery path is still open
work — see issue #55.

## Amateur Radio Integration

**SDR input:** In this repo, via SpyServer or a local device through `sdr/source.py`. Tune to the SSTV frequency (typically 14.230 MHz USB on 20m for HF), set appropriate gain, pipe audio to the decoder.

**CAT control:** If operating with a transceiver, CAT control allows automatic frequency and mode coordination. HamLib provides a cross-platform API.

**Logging:** ADIF format for QSL logging. SSTV QSOs typically logged with received image stored as JPEG.

## Response Structure

For any SSTV request:
1. **Mode/signal identification** — what mode, what to expect from its timing
2. **DSP approach** — which algorithm applies and why
3. **Implementation** — Python, matching the surrounding module
4. **Test methodology** — how to validate the decoder against known-good audio
5. **Reference** — point to MMSSTV source or Web-SSTV as implementation references where relevant
