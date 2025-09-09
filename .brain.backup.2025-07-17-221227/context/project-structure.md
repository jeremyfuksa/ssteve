# Project Structure - SSTV Project

## 📁 TOP-LEVEL ORGANIZATION

```
/Users/jf065530/_Repos/sstv/
├── .brain/                    # SuperClaude brain system
├── CLAUDE.md                  # Project instructions (THIS FILE)
├── core/                      # Shared components
├── platforms/                 # Platform-specific implementations
├── docs/                      # Documentation and analysis
└── tools/                     # Utility scripts
```

## 🐍 PYTHON CORE (`core/python/`)

### SSTV Engine
- **`sstv_engine/decoder.py`**: colaclanth/sstv integration (NEVER REPLACE)
- **`sstv_engine/encoder.py`**: PySSTV integration for encoding
- **`sstv_engine/enhancer.py`**: PIL-based image enhancement pipeline
- **`sstv_engine/streaming.py`**: Progressive image rendering
- **`sstv_engine/wrapper.py`**: Subprocess interface layer
- **`sstv_engine/cli.py`**: Command-line interface
- **`sstv_engine/types.py`**: Type definitions and constants

### Configuration
- **`requirements.txt`**: Python dependencies
- **`setup.py`**: Package configuration

## 🦀 TAURI IMPLEMENTATION (`platforms/tauri/`)

### Rust Backend (`src-tauri/`)
- **`src/main.rs`**: Main Tauri application with all commands
- **`Cargo.toml`**: Rust dependencies and build config
- **`tauri.conf.json`**: Tauri application configuration
- **`build.rs`**: Build script for compilation

### Frontend (`src/`)
- **`main.js`**: Application entry point
- **`index.html`**: Main HTML template
- **`core/App.js`**: Main application component and tab management
- **`core/Component.js`**: Base component class

### UI Components (`src/components/`)
- **`ReceiveComponent.js`**: SSTV decoding interface and live audio
- **`TransmitComponent.js`**: SSTV encoding interface  
- **`GalleryComponent.js`**: Image browsing and file management
- **`SetupComponent.js`**: Settings and configuration

### Styling (`src/styles/`)
- **`globals.css`**: Global styles and phosphor green theme
- **`components.css`**: Component-specific styling

### Build System
- **`package.json`**: Node dependencies and scripts
- **`vite.config.js`**: Vite build configuration

## 🧪 TESTING INFRASTRUCTURE (`core/shared/testing/`)

### Reference Files (`reference/`)
- **`audio/mmsstv/`**: MMSSTV reference audio files (5 files)
- **`audio/essexham/`**: Essex Ham test signals (4 files)  
- **`audio/ariss/`**: ARISS ISS SSTV transmissions (8 files)
- **`images/mmsstv/`**: Expected reference images
- **`images/essexham/`**: Expected decode results
- **`images/ariss/`**: ISS SSTV reference images
- **`new-images/`**: Test images for encoding (3 files)

### Test Results (`results/`)
- **`decode/`**: Decoded images from test runs
- **`encode/`**: Generated audio files from encoding tests
- **`roundtrip/`**: Full encode → decode validation results
- **`test_report.json`**: Automated test results

### Test Scripts (`scripts/`)
- **`engine_test.js`**: Main test suite runner
- **`integration_test.js`**: Full pipeline validation
- **`roundtrip_test.js`**: Encode/decode round-trip testing
- **`cleanup_results.js`**: Test cleanup utility

## 📚 SHARED PROTOCOLS (`core/shared/protocols/`)
- **`sstv_ipc.json`**: Inter-process communication definitions

## 📖 DOCUMENTATION (`docs/`)
- **Analysis documents**: Word docs with research and planning
- **`IMAGE_ENHANCEMENT.md`**: Enhancement pipeline documentation
- **`alignment-updates/`**: Project alignment and philosophy documents

## 🔧 UTILITIES (`tools/`)
- **`download_test_files.py`**: Test file acquisition script
- **`rgb_to_png.js`**: Image format conversion utility
- **`setup_platform.sh`**: Platform setup automation

## 🏗️ BUILD ARTIFACTS
- **`platforms/tauri/dist/`**: Frontend build output (generated)
- **`platforms/tauri/src-tauri/target/`**: Rust build artifacts (generated)
- **Node modules**: Platform-specific dependencies (generated)

## 🔑 KEY INTEGRATION POINTS

### Tauri ↔ Python
- **Commands**: Rust functions exposed to frontend via `#[tauri::command]`
- **Subprocess**: Python processes spawned from Rust backend
- **File I/O**: Temporary files for audio/image exchange

### Frontend ↔ Backend  
- **Invoke**: `invoke('command_name', params)` from frontend
- **Events**: Tauri event system for progress updates
- **State**: Audio state management in Rust backend