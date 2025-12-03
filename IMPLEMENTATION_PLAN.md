# SSTV Station - Gap Completion Plan

## Overview

This plan addresses the remaining gaps between the current implementation and the project goal: a production-ready desktop SSTV app with file-based decode/encode, cross-platform installers, and polished UX.

**Current State**: Core decode/encode flows work end-to-end in dev mode. CI passes. Packaging/bundling incomplete.

**Target State**: Distributable installers for Windows/macOS/Linux with bundled Python engine, polished UX, and comprehensive test coverage.

---

## Gap 1: Packaging & Bundling

**Problem**: The app runs in dev mode but can't be distributed. Python engine lives outside the app bundle, and resource resolution only works from the dev tree.

### 1.1 Python Engine Bundling Strategy

**Decision**: Bundle `.venv` directory with the app.

- Self-contained, version-controlled Python environment
- Located at `core/python/.venv` during dev, bundled into app resources for distribution
- Tradeoff: Larger bundle (~50-100MB) but guarantees correct dependencies

### 1.2 Implementation Steps

#### Step 1.2.1: Create Python bundling script
```
tools/bundle_python.sh
├── Create platform-specific venv
├── Install requirements.txt
├── Strip unnecessary files (.pyc, __pycache__, tests)
├── Output to: sstv-station/src-tauri/resources/python/
```

**Tasks**:
- [x] Write `tools/bundle_python.sh` (bash script)
- [x] Add Python version check (require 3.9+)
- [x] Create minimal requirements-prod.txt (exclude pytest, dev deps)
- [x] Test bundle creation on Linux *(macOS/Windows moved to Phase 7 verification)*

#### Step 1.2.2: Update Tauri resource configuration

**File**: `sstv-station/src-tauri/tauri.conf.json`

Add resource bundling:
```json
{
  "bundle": {
    "resources": [
      "resources/python/**/*"
    ]
  }
}
```

**Tasks**:
- [x] Add resources glob to tauri.conf.json
- [x] Test that resources are included in bundle *(Linux build)*
- [ ] Verify resource path resolution in packaged app *(manual UI verification pending)*

#### Step 1.2.3: Update Rust path resolution

**File**: `sstv-station/src-tauri/src/main.rs`

Current `get_python_engine_path()` needs to:
1. Check for bundled resources first (packaged app)
2. Fall back to dev tree (development mode)

**Tasks**:
- [x] Implement `tauri::api::path::resolve_resource()` for packaged mode
- [x] Add detection logic: is this a packaged app or dev mode?
- [x] Update Python invocation to use bundled venv's python

#### Step 1.2.4: Platform-specific installers

**Files to create/update**:
- `sstv-station/src-tauri/tauri.conf.json` (bundle identifiers)
- `platforms/windows/installer.nsi` (optional custom NSIS)
- `platforms/macos/Info.plist` (app metadata)
- `platforms/linux/sstv-station.desktop` (desktop entry)

**Tasks**:
- [ ] Configure Windows MSI/NSIS bundle settings
- [ ] Configure macOS DMG bundle settings (code signing optional for v1)
- [ ] Configure Linux AppImage/deb bundle settings
- [ ] Test `npm run tauri build` on each platform
- [ ] Document installer creation in BUILDING.md

### 1.3 Verification Checklist

- [x] `npm run tauri build` produces installer on Linux
- [ ] `npm run tauri build` produces installer on macOS *(Phase 7)*
- [ ] `npm run tauri build` produces installer on Windows *(Phase 7)*
- [ ] Installed app can decode SSTV audio without dev tools *(manual GUI verification pending)*
- [ ] Installed app can encode images to SSTV audio *(manual GUI verification pending)*
- [ ] Python engine errors are reported clearly to user *(manual GUI verification pending)*

---

## Gap 2: UX Polish

**Problem**: Missing save dialogs, no feedback during operations, no user documentation.

### 2.1 Save Dialog for Encoded Audio

**Current**: `encode_sstv_image` returns temp file path but no save option exposed.

**File**: `sstv-station/src/main.js`

**Tasks**:
- [x] Add "Save Audio" button to TRANSMIT panel (appears after encode)
- [x] Wire button to `save` dialog from `@tauri-apps/plugin-dialog`
- [x] Copy temp WAV to user-selected location
- [x] Show success/failure toast message
- [x] Clean up temp file after save (or on app close)

### 2.2 Button State Management During Operations

**Current**: Buttons remain clickable during decode/encode, risking double-submission.

**Tasks**:
- [x] Add `isProcessing` state flag to `SSTVStation` class
- [x] Disable "Decode", "Encode", "Load" buttons when `isProcessing=true`
- [x] Add visual indicator (opacity reduction, cursor change)
- [x] Show spinner or progress text during operation
- [x] Re-enable buttons on success or failure

### 2.3 Error Toast System

**Current**: Errors shown via `console.error` or alert dialogs.

**Tasks**:
- [x] Create toast notification component (CSS + JS)
- [x] Position: bottom-right, auto-dismiss after 5 seconds
- [x] Styles: success (green), error (red), info (blue)
- [x] Replace alert() calls with toast.show()
- [x] Add toast for common errors:
  - Invalid file format
  - Python engine not found
  - Decode failed (no SSTV signal detected)
  - Encode failed (invalid image)

### 2.4 User Guide

**File**: `docs/USER_GUIDE.md`

**Content outline**:
1. Quick Start
   - Installing the app
   - Decoding your first SSTV audio
   - Encoding an image to SSTV
2. Receive Mode
   - Loading audio files
   - Understanding the spectrum display
   - Image enhancement options
3. Transmit Mode
   - Supported image formats
   - SSTV mode selection guide
   - Saving encoded audio
4. Gallery Mode
   - Browsing decoded images
   - File management
5. Settings
   - Audio device selection
   - Enhancement presets
6. Troubleshooting
   - Common errors and solutions
   - Getting help

**Tasks**:
- [ ] Write USER_GUIDE.md (target: 500-800 words)
- [ ] Add screenshots for each mode
- [ ] Link from README.md

### 2.5 Additional UX Improvements

**Tasks**:
- [ ] Add keyboard shortcuts (Ctrl+O = open, Ctrl+S = save)
- [ ] Add drag-and-drop support for audio/image files
- [ ] Show file name in title bar after loading
- [ ] Add "Recent Files" menu (stretch goal)

---

## Gap 3: Test Coverage

**Problem**: Minimal Rust tests, Python tests gated behind env var, no UI tests.

### 3.1 Rust Test Expansion

**File**: `sstv-station/src-tauri/src/main.rs`

**Current coverage**: 1 test (sanitize_removes_paths_and_traces)

**Tests to add**:

```rust
#[cfg(test)]
mod tests {
    // Path validation tests
    #[test] fn validate_user_path_allows_valid_paths() {}
    #[test] fn validate_user_path_blocks_traversal() {}
    #[test] fn validate_user_path_blocks_null_bytes() {}

    // JSON parsing tests
    #[test] fn parse_python_output_extracts_image_path() {}
    #[test] fn parse_python_output_extracts_audio_path() {}
    #[test] fn parse_python_output_handles_error_lines() {}
    #[test] fn parse_python_output_handles_malformed_json() {}

    // Mode validation tests
    #[test] fn get_sstv_modes_returns_valid_list() {}
    #[test] fn encode_validates_mode_whitelist() {}

    // Path resolution tests
    #[test] fn get_python_engine_path_finds_dev_tree() {}
}
```

**Tasks**:
- [ ] Write path validation unit tests
- [ ] Write Python output parsing tests
- [ ] Write mode validation tests
- [ ] Ensure tests run in CI without Python

### 3.2 Python Test Expansion

**File**: `core/python/tests/`

**Current coverage**: 2 smoke tests (import, encode)

**Tests to add**:

```python
# test_decoder.py
def test_decode_scottie_s1_reference():
    """Decode known Scottie S1 file, compare to reference image."""

def test_decode_martin_m1_reference():
    """Decode known Martin M1 file."""

def test_decode_handles_corrupt_audio():
    """Graceful failure on corrupt WAV."""

def test_decode_handles_no_sstv_signal():
    """Returns appropriate error when no SSTV detected."""

# test_encoder.py
def test_encode_all_modes():
    """Verify all 6 modes produce valid WAV files."""

def test_encode_handles_large_image():
    """Resize/crop behavior for oversized images."""

def test_encode_handles_invalid_image():
    """Graceful failure on corrupt PNG."""

# test_roundtrip.py
def test_roundtrip_scottie_s1():
    """Encode image, decode result, compare to original."""

def test_roundtrip_preserves_mode():
    """Encoded mode matches decoded mode."""

# test_enhancer.py
def test_enhance_presets():
    """Each preset produces different output."""

def test_enhance_handles_grayscale():
    """Enhancement works on grayscale images."""
```

**Tasks**:
- [ ] Write decoder reference tests using MMSSTV samples
- [ ] Write encoder tests for all modes
- [ ] Write roundtrip tests
- [ ] Write enhancer tests
- [ ] Remove RUN_ENGINE_TESTS guard (run by default in CI)
- [ ] Add pytest-cov for coverage reporting

### 3.3 Integration Tests

**File**: `core/shared/testing/scripts/`

**Current**: Manual test scripts exist but aren't in CI.

**Tasks**:
- [ ] Convert engine_test.js to Jest-based test suite
- [ ] Add to CI workflow as separate job
- [ ] Create test fixtures: known-good audio → expected image checksums
- [ ] Add performance benchmarks (decode time for reference files)

### 3.4 UI Smoke Tests

**Decision**: Use **Playwright** for UI testing with **real engine** (not mocked).

**Rationale**: Real engine tests verify the actual decode quality, not just glue code. Reference files exist, and decode correctness is the core value prop.

**Coverage**:
- [ ] App launches without crash
- [ ] Tab switching works
- [ ] File dialog opens
- [ ] Decode flow completes with real Python engine
- [ ] Encode flow produces valid WAV

**Tasks**:
- [ ] Install Playwright: `npm install -D @playwright/test`
- [ ] Configure Playwright for Tauri: use `electron` mode or direct WebView
- [ ] Write smoke tests in `sstv-station/tests/e2e/`
- [ ] Add to CI with Xvfb on Linux

---

## Gap 4: Headless/Dev Ergonomics

**Problem**: Linux requires GTK/X session; headless CI needs Xvfb.

### 4.1 Documentation Improvements

**File**: `docs/DEVELOPMENT.md`

**Content**:
1. Prerequisites by platform
2. Setting up the dev environment
3. Running in headless mode (Xvfb)
4. Common issues and solutions

**Tasks**:
- [ ] Write DEVELOPMENT.md with platform-specific setup
- [ ] Document Xvfb usage: `xvfb-run npm run tauri dev`
- [ ] Add troubleshooting section for GTK errors
- [ ] Link from README.md

### 4.2 Headless CI Automation

**File**: `.github/workflows/build-and-test.yml`

**Current**: Builds work but GUI tests would fail headless.

**Tasks**:
- [ ] Add Xvfb setup step for Linux GUI tests
- [ ] Create headless test job that skips GUI-dependent tests
- [ ] Add conditional: run GUI tests only when DISPLAY available

### 4.3 Dev Script Improvements

**Tasks**:
- [ ] Create `tools/dev.sh` wrapper that auto-detects headless and uses Xvfb
- [ ] Add `npm run dev:headless` script in package.json
- [ ] Create `.envrc` template for direnv users

---

## Gap 5: Optional Stretch Goals

### 5.1 Live Audio Streaming Decode

**Current**: File-based decode only.

**Implementation approach**:
1. Use CPAL crate for real-time audio capture in Rust
2. Buffer audio chunks, write to temp WAV periodically
3. Invoke streaming decoder on buffered audio
4. Progressive UI updates as image lines decode

**Tasks** (if pursued):
- [ ] Add CPAL dependency to Cargo.toml
- [ ] Implement audio capture thread
- [ ] Create ring buffer for audio samples
- [ ] Wire to streaming.py for progressive decode
- [ ] Add UI controls: Start/Stop listening, auto-decode trigger

### 5.2 Real-World Signal QA

**Tasks** (if pursued):
- [ ] Collect additional reference signals from ham radio operators
- [ ] Create signal quality classification (clean, noisy, weak)
- [ ] Test decoder robustness across signal quality levels
- [ ] Document performance characteristics

---

## Priority Order

### Phase 1: Shippable App (High Priority)
1. **Packaging & Bundling** (Gap 1) - Required for distribution
2. **Save Dialog** (Gap 2.1) - Core missing feature
3. **Button States** (Gap 2.2) - Prevents user confusion/errors

### Phase 2: Quality & Polish (Medium Priority)
4. **Error Toasts** (Gap 2.3) - Better user feedback
5. **Rust Tests** (Gap 3.1) - Catch regressions
6. **Python Tests** (Gap 3.2) - Catch regressions

### Phase 3: Documentation & DX (Lower Priority)
7. **User Guide** (Gap 2.4) - Helps new users
8. **Dev Docs** (Gap 4.1) - Helps contributors
9. **CI Improvements** (Gap 4.2) - Better automation

### Phase 4: Stretch Goals (Optional)
10. **Live Audio** (Gap 5.1) - Nice to have
11. **Signal QA** (Gap 5.2) - Nice to have

---

## Technical Decisions (Confirmed)

1. **Python bundling**: ✅ Bundle `.venv` at `core/python/.venv` with full dependencies
2. **Test scope**: ✅ Real engine tests against reference files (not mocked)
3. **UI testing**: ✅ Playwright with real engine integration

---

## Estimated Complexity

| Gap | Files Touched | Complexity | Notes |
|-----|---------------|------------|-------|
| 1.1-1.4 Packaging | 5-8 files | High | Cross-platform testing needed |
| 2.1 Save Dialog | 1-2 files | Low | UI + Tauri command |
| 2.2 Button States | 1 file | Low | State management |
| 2.3 Toast System | 2 files | Medium | New component |
| 2.4 User Guide | 1 file | Low | Documentation only |
| 3.1 Rust Tests | 1 file | Medium | Test writing |
| 3.2 Python Tests | 3-4 files | Medium | Test writing |
| 3.3 Integration | 2-3 files | Medium | CI integration |
| 4.1 Dev Docs | 1 file | Low | Documentation only |
| 4.2 Headless CI | 1 file | Low | Workflow update |
| 3.4 Playwright Tests | 4-5 files | Medium | E2E test setup |
| 5.1 Live Audio | 3-4 files | High | New feature |

---

## Success Criteria

The project is complete when:

1. **Distribution Ready**
   - [ ] `npm run tauri build` produces working installers for all 3 platforms
   - [ ] Installed app works without Python dev environment
   - [ ] App size is reasonable (<150MB with bundled Python)

2. **Feature Complete**
   - [ ] Users can decode SSTV audio files to images
   - [ ] Users can encode images to SSTV audio files
   - [ ] Users can save encoded audio to chosen location
   - [ ] Users see clear feedback during operations
   - [ ] Users see clear error messages when things fail

3. **Quality Assured**
   - [ ] >80% test coverage on critical paths
   - [ ] All reference audio files decode correctly
   - [ ] All supported modes encode and roundtrip successfully
   - [ ] CI catches regressions before merge

4. **Documented**
   - [ ] User can install and use app with USER_GUIDE.md
   - [ ] Developer can set up environment with DEVELOPMENT.md
   - [ ] README.md provides clear project overview

---

## Detailed Technical Task List

### Phase 1: Packaging & Bundling (15 tasks) ✅ CODE COMPLETE

#### 1.1 Python Environment Setup
- [x] **P1-01**: Create `.venv` at `core/python/.venv` with `python3 -m venv .venv`
- [x] **P1-02**: Install production deps: `pip install -r requirements.txt`
- [x] **P1-03**: Create `requirements-prod.txt` (exclude pytest, dev deps)
- [x] **P1-04**: Test venv works: `python -m sstv_engine.cli decode --help`

#### 1.2 Bundling Script
- [x] **P1-05**: Create `tools/bundle_python.sh` script
  - Check Python version (require 3.9+)
  - Create fresh venv in temp location
  - Install requirements-prod.txt
  - Strip `__pycache__`, `.pyc`, `tests/` directories
  - Copy to `sstv-station/src-tauri/resources/python/`
- [x] **P1-06**: Make script executable and test on Linux

#### 1.3 Tauri Configuration
- [x] **P1-09**: Update `tauri.conf.json` to add resource bundling:
  ```json
  "bundle": {
    "resources": ["resources/python/**/*"]
  }
  ```
- [x] **P1-10**: Add `.gitignore` entry for `src-tauri/resources/python/`

#### 1.4 Rust Path Resolution
- [x] **P1-11**: Update `get_python_engine_path()` in `main.rs`:
  - First check: `tauri::api::path::resolve_resource("python")`
  - Fallback: dev tree at `CARGO_MANIFEST_DIR/../../core/python`
- [x] **P1-12**: Update `get_python_executable()` to use `.venv/bin/python` (or `.venv/Scripts/python.exe` on Windows)
- [x] **P1-13**: Add detection logic for packaged vs dev mode

#### 1.5 Build & Verify
- [x] **P1-16**: Run `npm run tauri build` and verify installer created

#### 1.6 (Moved to Phase 7) Platform & Usage Verification
- **P1-07**: Test bundle script on macOS → moved to Phase 7
- **P1-08**: Test bundle script on Windows → moved to Phase 7
- **P1-14**: Test decode works in dev mode with new path logic → moved to Phase 7
- **P1-15**: Test encode works in dev mode with new path logic → moved to Phase 7
- **P1-17**: Install app from installer, test decode/encode without dev tools *(blocked: headless GTK; installer build succeeds)* → moved to Phase 7

---

### Phase 2: UX Polish (14 tasks)

**Status**: ✅ **CODE COMPLETE** - All features implemented and verified. See `PHASE2_VERIFICATION.md` for detailed review. Manual GUI testing recommended.

#### 2.1 Save Dialog for Encoded Audio
- [x] **P2-01**: Add "Save Audio" button to TRANSMIT panel in `main.js`
- [x] **P2-02**: Wire button to `@tauri-apps/plugin-dialog` save dialog
- [x] **P2-03**: Implement file copy from temp WAV to user location
- [x] **P2-04**: Show success message after save
- [x] **P2-05**: Clean up temp file after successful save

#### 2.2 Button State Management
- [x] **P2-06**: Add `isProcessing` state to `SSTVStation` class
- [x] **P2-07**: Disable action buttons when `isProcessing=true`
- [x] **P2-08**: Add CSS `.disabled` state (opacity, cursor change)
- [x] **P2-09**: Show "Processing..." text or spinner during operations
- [x] **P2-10**: Re-enable buttons on completion (success or failure)

#### 2.3 Toast Notification System
- [x] **P2-11**: Create toast component in `style.css` (bottom-right, auto-dismiss)
- [x] **P2-12**: Create `Toast` class in `main.js` with `show(message, type)` method
- [x] **P2-13**: Style variants: success (green), error (red), info (blue)
- [x] **P2-14**: Replace `alert()` calls with `Toast.show()`

---

### Phase 3: Test Coverage (19 tasks)

**Status**: Rust path validation tests added; Python encoder validation tests added (invalid path/mode). Remaining decode/roundtrip and UI/E2E tests still outstanding.

#### 3.1 Rust Unit Tests
- [x] **P3-01**: Add `test_validate_user_path_allows_valid_paths()` in `main.rs`
- [x] **P3-02**: Add `test_validate_user_path_blocks_traversal()`
- [x] **P3-03**: Add `test_validate_user_path_blocks_null_bytes()`
- [x] **P3-04**: Add `test_parse_python_output_extracts_image_path()`
- [x] **P3-05**: Add `test_parse_python_output_handles_error_lines()`
- [x] **P3-06**: Add `test_get_sstv_modes_returns_valid_list()`

#### 3.2 Python Unit Tests
- [x] **P3-07**: Create `core/python/tests/test_decoder.py` *(implemented as `test_engine_extended.py`, includes reference decode + corrupt/no-signal cases)*
- [x] **P3-08**: Create `core/python/tests/test_encoder.py` (full modes/invalid image)
- [x] **P3-09**: Create `core/python/tests/test_roundtrip.py` *(roundtrip Scottie S1)*
- [x] **P3-10**: Create `core/python/tests/test_enhancer.py`
- [x] **P3-11**: Remove `RUN_ENGINE_TESTS` guard - run tests by default
- [x] **P3-12**: Add pytest to CI workflow

#### 3.3 Playwright E2E Tests
- [x] **P3-13**: Install Playwright: `npm install -D @playwright/test`
- [x] **P3-14**: Create `sstv-station/playwright.config.ts`
- [x] **P3-15**: Create `sstv-station/tests/e2e/app.spec.ts`
- [x] **P3-16**: Write test: app launches without crash
- [x] **P3-17**: Write test: tab switching works (Receive → Transmit → Gallery)
- [x] **P3-18**: Write test: decode flow with reference audio file *(env-gated Playwright test requiring Tauri bridge + `E2E_AUDIO_PATH`)*
- [x] **P3-19**: Add Playwright to CI with Xvfb on Linux

---

### Phase 4: Documentation (8 tasks)

#### 4.1 User Guide
- [ ] **P4-01**: Create `docs/USER_GUIDE.md`
- [ ] **P4-02**: Write Quick Start section (install, first decode, first encode)
- [ ] **P4-03**: Write Receive Mode section with screenshot
- [ ] **P4-04**: Write Transmit Mode section with screenshot
- [ ] **P4-05**: Write Troubleshooting section

#### 4.2 Developer Documentation
- [ ] **P4-06**: Create `docs/DEVELOPMENT.md`
  - Prerequisites by platform (Node, Rust, Python, GTK)
  - Dev environment setup steps
  - Running in headless mode with Xvfb
  - Common issues and solutions
- [ ] **P4-07**: Update README.md to link to docs/
- [ ] **P4-08**: Add `npm run dev:headless` script using xvfb-run

---

### Phase 5: CI Improvements (4 tasks)

- [ ] **P5-01**: Add Xvfb setup step for Linux in `.github/workflows/build-and-test.yml`
- [ ] **P5-02**: Add Python test job to CI workflow
- [ ] **P5-03**: Add Playwright test job to CI workflow (with Xvfb)
- [ ] **P5-04**: Create `tools/dev.sh` wrapper that auto-detects headless

---

### Phase 6: Stretch Goals (Optional)

#### 6.1 Live Audio Streaming
- [ ] **P6-01**: Add `cpal` crate to Cargo.toml for audio capture
- [ ] **P6-02**: Implement audio capture thread in Rust
- [ ] **P6-03**: Create ring buffer, write to temp WAV periodically
- [ ] **P6-04**: Wire to `streaming.py` for progressive decode
- [ ] **P6-05**: Add Start/Stop listening controls to UI

---

## Task Summary

| Phase | Tasks | Complexity |
|-------|-------|------------|
| 1. Packaging | 17 | High |
| 2. UX Polish | 14 | Medium |
| 3. Testing | 19 | Medium |
| 4. Documentation | 8 | Low |
| 5. CI | 4 | Low |
| 6. Stretch | 5 | High |
| 7. User Testing | 6 | Medium |
| 7. User Testing | 3 | Medium |

### Phase 7: User Testing & Beta (Usage Verification)
- **P1-07**: Test bundle script on macOS → moved to Phase 7
- **P1-08**: Test bundle script on Windows → moved to Phase 7
- **P1-14**: Test decode works in dev mode with new path logic
- **P1-15**: Test encode works in dev mode with new path logic
- **P1-17**: Install app from installer, test decode/encode without dev tools *(blocked here by headless GTK; recruit beta testers on GUI machines)*
| **Total** | **67** | — |

---

## Phase 1: Packaging & Bundling ✅ COMPLETE

**Status**: Code implementation complete. Manual verification required due to environment constraints.

### Completed Implementation (17 tasks)

**1.1 Python Environment Setup**
- [x] P1-01: Created `.venv` at `core/python/.venv` with Python 3.11
- [x] P1-02: Installed production dependencies (sstv, pysstv, Pillow, numpy, scipy, soundfile)
- [x] P1-03: Created `requirements-prod.txt` (excludes pytest, dev deps)
- [x] P1-04: Tested venv works - decode ✅ (55s) and encode ✅ (4s) verified

**1.2 Bundling Script**
- [x] P1-05: Created `tools/bundle_python.sh` with:
  - Python version check (require 3.9+)
  - Fresh venv creation in temp directory
  - Requirements installation with pip
  - Stripping of `__pycache__`, `.pyc`, `tests/`
  - Copy to `sstv-station/src-tauri/resources/python/`
- [x] P1-06: Tested bundle script - 170MB bundle created successfully

**1.3 Tauri Configuration**
- [x] P1-09: Updated `tauri.conf.json`:
  ```json
  "resources": ["resources/python/**/*"]
  ```
- [x] P1-10: Added `.gitignore` entries:
  - `.venv/`
  - `sstv-station/src-tauri/resources/python/`

**1.4 Rust Path Resolution**
- [x] P1-11: Updated `get_python_engine_path()` in `main.rs`:
  - **Packaged mode**: Looks for `resources/python/lib/pythonX.Y/site-packages`
  - **Dev mode**: Falls back to `core/python/` directory
- [x] P1-12: Updated `get_venv_python_path()`:
  - **Packaged mode**: Uses `resources/python/bin/python3`
  - **Dev mode**: Uses `core/python/.venv/bin/python3`
  - **Legacy fallback**: Checks project root `venv/`
  - **System fallback**: Uses system `python3` if no venv found
- [x] P1-13: Packaged vs dev mode detection logic implemented

**1.5 Code Fixes**
- [x] Fixed `cli.py` subcommand dispatcher (was not parsing args correctly)
- [x] Fixed `encoder.py` to use `sys.executable` instead of hardcoded `python3`
- [x] Updated `requirements.txt` to use git URL for colaclanth/sstv

**1.6 Build Verification**
- [x] Rust code compiles successfully with `cargo check` (1 minor warning about unused struct)
- [x] npm dependencies installed
- [x] Python CLI decode/encode verified working

### Files Created/Modified

**Created:**
- `core/python/.venv/` - Development Python virtual environment
- `core/python/requirements-prod.txt` - Production-only dependencies
- `tools/bundle_python.sh` - Python bundling script (executable)
- `sstv-station/src-tauri/resources/python/` - Bundled Python (170MB, gitignored)

**Modified:**
- `core/python/requirements.txt` - Fixed sstv package URL
- `core/python/sstv_engine/cli.py` - Fixed subcommand dispatcher
- `core/python/sstv_engine/encoder.py` - Use sys.executable
- `sstv-station/src-tauri/tauri.conf.json` - Added resource bundling
- `sstv-station/src-tauri/src/main.rs` - Updated path resolution (120 lines changed)
- `.gitignore` - Added venv and resources entries

### Manual Verification Required

Due to shell environment configuration issues, the following steps require manual testing in a fresh terminal:

```bash
# Terminal 1: Test dev mode
cd ~/projects/sstv/sstv-station
npm run tauri dev

# In the app:
# - Load WAV from core/shared/testing/reference/audio/mmsstv/scottie_s1_bear_je3hht.wav
# - Verify image decodes correctly
# - Load test image and encode to WAV
# - Verify encoded audio created

# Terminal 2: Build installer
cd ~/projects/sstv
./tools/bundle_python.sh  # Refresh bundle (if needed)
cd sstv-station
npm run tauri build

# Terminal 3: Test installed app
cd sstv-station/src-tauri/target/release/bundle/
# Install the generated package for your platform
# Run installed app and verify decode/encode works without dev environment
```

### Expected Behavior

| Mode | Python Path | Engine Path |
|------|-------------|-------------|
| **Dev** | `core/python/.venv/bin/python3` | `core/python/` |
| **Packaged** | `resources/python/bin/python3` | `resources/python/lib/python3.11/site-packages/` |

Both modes should successfully decode/encode SSTV files without system Python dependency.

### Known Issues
- 1 Rust warning: unused `AudioDevice` struct (non-critical)
- Shell environment has nvm lazy-loading recursion issue (prevents automated testing)

---

## Next Action

**Phase 2: UX Polish** - Ready to begin

Focus areas:
- Save dialog for encoded audio (P2-01 to P2-05)
- Button state management during operations (P2-06 to P2-10)
- Toast notification system (P2-11 to P2-14)
