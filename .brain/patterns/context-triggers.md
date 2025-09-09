# Context Triggers - SSTV Project

## Automatic Context Loading Patterns

### File-based Triggers
- **`.rs` files**: Load L2 (Development) + Rust-specific context
- **`.js` files**: Load L2 (Development) + Frontend-specific context  
- **`.py` files**: Load L2 (Development) + Python SSTV context
- **`Cargo.toml`**: Load L2 + Tauri build context
- **`package.json`**: Load L2 + Frontend build context

### Task-based Triggers
- **"debug"**, **"error"**, **"broken"**: Load debug-investigation template
- **"feature"**, **"implement"**, **"add"**: Load feature-development template
- **"review"**, **"check"**, **"audit"**: Load code-review template
- **"performance"**, **"slow"**, **"timing"**: Load L4 (Deep) context

### Domain-specific Triggers
- **"audio"**, **"recording"**, **"CPAL"**: Load audio pipeline context
- **"decode"**, **"encode"**, **"SSTV"**: Load colaclanth/sstv integration context
- **"UI"**, **"frontend"**, **"tab"**: Load frontend architecture context
- **"Python"**, **"subprocess"**: Load Python integration context

### Project Phase Triggers
- **"Phase 5"**, **"signal analysis"**: Load Phase 5 planning context
- **"FFT"**, **"spectrogram"**: Load signal processing context
- **"Hamlib"**, **"CAT"**: Load radio control context
- **"VIS"**, **"mode detection"**: Load SSTV protocol context

## Context Combinations
- **Bug in audio**: L1+L2+L4 + audio pipeline + debug template
- **New UI feature**: L1+L2+L3 + frontend + feature template
- **Python integration**: L1+L2 + Python SSTV + colaclanth/sstv context
- **Performance issue**: L1+L2+L4 + performance patterns + debug template