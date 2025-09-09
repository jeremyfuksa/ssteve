# Context Layering System - SSTV Project

## L1: Core Context (Always Active)
- **Project Type**: SSTV decoder/encoder desktop application
- **Primary Framework**: Tauri v2 (Rust backend + Vanilla JS frontend)
- **Core Library**: colaclanth/sstv Python library (NEVER REPLACE)
- **Status**: Phase 4B Complete - Real-time audio capture → SSTV decode pipeline working
- **Architecture**: Cross-platform desktop app with streaming decoder

## L2: Development Context (Task-Dependent)
- **Current Directory**: `/Users/jf065530/_Repos/sstv`
- **Key Files**: 
  - `platforms/tauri/src-tauri/src/main.rs` - Rust backend
  - `platforms/tauri/src/` - Frontend components
  - `core/python/sstv_engine/` - Python SSTV library integration
- **Build Process**: `npm run build && npm run tauri dev`
- **Test Files**: `core/shared/testing/reference/` for validation

## L3: Feature Context (Feature-Specific)
### Current Features (Working)
- **Real-time Decoding**: Live audio → PCM → WAV → Python decoder
- **Image Enhancement**: PIL-based pipeline with presets
- **Multi-format Encoding**: Scottie, Martin, Robot modes
- **Gallery Management**: File browsing and organization
- **Settings Persistence**: JSON configuration system

### Phase 5 Target: Signal Analysis
- **Basic FFT Spectrogram**: Web Audio API + canvas
- **Signal Quality Metrics**: SNR estimation, signal strength
- **VIS Detection**: Mode detection improvements
- **Basic Hamlib**: CAT control integration

## L4: Deep Context (Investigation-Specific)
- **Performance**: File-based approach for real-time processing
- **Audio Flow**: CPAL → threaded capture → WAV files → Python subprocess
- **Error Handling**: Comprehensive status feedback system
- **UI Architecture**: Tab-based interface with dynamic controls

## Context Triggers
- **`L1+L2`**: Basic development tasks, bug fixes
- **`L1+L2+L3`**: Feature development, UI changes
- **`L1+L2+L3+L4`**: Complex debugging, architecture changes
- **`L2+L3`**: Frontend-only changes
- **`L2+L4`**: Backend/performance work