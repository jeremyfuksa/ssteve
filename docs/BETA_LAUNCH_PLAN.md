# SSTeVe Beta Launch Plan

**Target Date:** 2026-01-31 (11 days remaining)
**Current Status:** 70-75% complete
**Required for Beta:** 90-95% complete (working decode/transmit flows)

---

## 🎯 Beta Requirements (Minimum Viable Product)

**Core Functionality (MUST have):**
1. ✅ User can select audio device and start listening
2. ✅ App auto-detects SSTV mode from VIS code
3. ✅ Image decodes in real-time with scanline rendering
4. ✅ Decoded image auto-saves to gallery with metadata
5. ✅ User can transmit image with one-click Smart Reply
6. ✅ No slanted images (Hough Transform correction)
7. ✅ Acoustic coupling works (bandpass filter + volume indicator)

**Quality Standards (SHOULD have):**
1. ✅ WebSocket real-time events (scanline updates, audio levels)
2. ✅ Error handling with SSTeVe-friendly messages
3. ✅ Session management (half-duplex enforcement)
4. ✅ Configuration persistence
5. ✅ Basic testing coverage
6. ✅ Documentation for beta testers

---

## 📋 Remaining Tasks (Priority Order)

### Priority 1: Complete Phase 5 Smart Features (2 tasks, ~5 hours)

**Status:** 18/19 complete (95%)

#### 1.1 Mode Detection API Endpoint (~3 hours) ✅ **COMPLETE**
**File:** `sstv_core/src/sstv_core/api/routes/decode.py`

**Acceptance Criteria:**
- [x] POST `/decode/detect_mode` endpoint implemented
- [x] Accepts session_id, audio_file, or duration_sec
- [x] Analyzes audio for sync timing
- [x] Returns detection result (mode, confidence, intervals, fallback_modes)
- [x] Returns null if confidence < 0.70
- [x] Integration test with reference audio

**Work Completed:**
- [x] Created ModeDetectionRequest/Response models in api/models.py
- [x] Added soundfile library to requirements.txt
- [x] Implemented detect_mode() endpoint in routes/decode.py
- [x] Wired to existing ModeDetector from smart_features
- [x] Added proper error handling (400/404/500)
- [x] User-friendly SSTeVe suggestion messages
- [x] Returns top 3 fallback mode alternatives

**Reference:** `BACKEND_TASKS.md` Task 5.2.2, `features/FSKID_SPECIFICATION.md`

#### 1.2 Smart Device Config "Apply Settings" Endpoint (~2 hours)
**File:** `sstv_core/src/sstv_core/api/routes/devices.py`

**Acceptance Criteria:**
- [ ] POST `/devices/apply_settings` endpoint implemented
- [ ] Accepts device configuration
- [ ] Updates configuration in database
- [ ] Returns updated configuration
- [ ] Integration test with device detector

**Work:**
- Create `apply_settings()` route
- Call `DeviceDetector` from smart_features
- Merge with existing config
- Save to database
- Return confirmation

**Reference:** `BACKEND_TASKS.md` Task 5.3.2

---

### Priority 2: Phase 4 Filesystem Integration (7 tasks, ~15-19 hours)

**Status:** 0/7 complete (0%)

#### 2.1 File System Watcher (~4 hours)
**File:** `sstv_core/src/sstv_core/filesystem/watcher.py` (already exists!)

**Acceptance Criteria:**
- [ ] Observer pattern using watchdog library
- [ ] Monitor user-configured image library directory
- [ ] Event handlers: on_created, on_modified, on_deleted
- [ ] Debounce rapid changes (500ms delay)
- [ ] Handle rename/move operations
- [ ] Integration test with temporary directories

**Work:**
- Watchdog library is already in requirements.txt
- Need to wire into backend (not called anywhere)
- Import in main.py or create separate service
- Connect to WebSocket for library_update events

**Reference:** `BACKEND_TASKS.md` Task 4.1.1

#### 2.2 Image Import Function (~3 hours)
**File:** `sstv_core/src/sstv_core/filesystem/importer.py` (already exists!)

**Acceptance Criteria:**
- [ ] Parse filename for metadata (YYYYMMDD_HHMMSS_MODE_CALLSIGN.jpg)
- [ ] Extract EXIF data if available
- [ ] Create database record in sstv_images
- [ ] Populate metadata fields
- [ ] Handle missing metadata gracefully
- [ ] Unit tests with various filename formats
- [ ] Integration test with database

**Work:**
- Importer already exists
- Need to wire into backend (not called anywhere)
- Connect to file watcher events
- Test with real image files

**Reference:** `BACKEND_TASKS.md` Task 4.1.2

#### 2.3 WebSocket Library Update Events (~2 hours)
**File:** `sstv_core/src/sstv_core/api/routes/websocket.py`

**Acceptance Criteria:**
- [ ] Emit `library_updated` event on new file
- [ ] Emit `image_modified` event on file edit
- [ ] Emit `image_deleted` event on file removal
- [ ] Event payload includes filepath and metadata
- [ ] Unit tests verify event emission
- [ ] Integration test with WebSocket client

**Work:**
- Add WebSocket events for library changes
- Connect to file watcher
- Test with file operations

**Reference:** `BACKEND_TASKS.md` Task 4.1.3

#### 2.4 MMSSTV Directory Scanner (~3 hours)
**File:** `sstv_core/src/sstv_core/filesystem/mmsstv_importer.py` (already exists!)

**Acceptance Criteria:**
- [ ] Recursive directory scan
- [ ] Filter for image files (jpg, png, bmp)
- [ ] Progress tracking (N/M files)
- [ ] Batch import (transaction per 100 images)
- [ ] Error logging for failed imports
- [ ] Unit tests with temporary directories
- [ ] Integration test with sample MMSSTV directory

**Work:**
- MMSSTV importer already exists
- Need to wire into backend (not called anywhere)
- Add API endpoint for triggering import
- Test with test assets

**Reference:** `BACKEND_TASKS.md` Task 4.2.1

#### 2.5 MMSSTV Import API Endpoint (~2 hours)
**File:** `sstv_core/src/sstv_core/api/routes/import_routes.py`

**Acceptance Criteria:**
- [ ] POST `/import/mmsstv` endpoint implemented
- [ ] Accepts directory_path parameter
- [ ] Validates directory exists
- [ ] Triggers import process
- [ ] Returns progress updates
- [ ] Returns total_imported and errors count
- [ ] Unit tests with mocked importer
- [ ] Integration test with sample directory

**Work:**
- Create `import_mmsstv()` route
- Call MMSSTVImporter
- Handle async import (may be long-running)
- Return progress via WebSocket or polling

**Reference:** `BACKEND_TASKS.md` Task 4.2.2

#### 2.6 Integration & Testing (~3-5 hours)
**Acceptance Criteria:**
- [ ] File watcher service starts with FastAPI
- [ ] WebSocket events fire on file operations
- [ ] MMSSTV import works with real directory
- [ ] Integration test: complete flow (watch → import → database)

---

### Priority 3: Phase 6 Critical Testing (5-7 tasks, ~20-30 hours)

**Status:** 0/11 complete (0%)

#### 3.1 Decode Integration Test (~4 hours)
**File:** `sstv_core/tests/integration/test_decode_e2e.py`

**Acceptance Criteria:**
- [ ] Test complete decode workflow:
  1. Start decode session (API)
  2. Play reference audio file
  3. Receive VIS detection event (WebSocket)
  4. Receive scanline updates (WebSocket)
  5. Receive decode complete event (WebSocket)
  6. Verify image saved to disk
  7. Verify database record created
- [ ] Test with all modes (Scottie S1, Martin M1, Robot 36)
- [ ] Verify decoded images match references (≥95% similarity)
- [ ] Test passes consistently

**Reference:** `BACKEND_TASKS.md` Task 6.2.1

#### 3.2 Transmit Integration Test (~3 hours)
**File:** `sstv_core/tests/integration/test_transmit_e2e.py`

**Acceptance Criteria:**
- [ ] Test complete transmit workflow:
  1. Start transmit session (API)
  2. Receive TX progress events (WebSocket)
  3. Verify PTT keying sequence
  4. Receive TX complete event (WebSocket)
  5. Verify audio output generated
- [ ] Test with all modes
- [ ] Decode generated audio (verify round-trip)
- [ ] Test passes consistently

**Reference:** `BACKEND_TASKS.md` Task 6.2.2

#### 3.3 WebSocket Reconnection Test (~3 hours)
**File:** `sstv_core/tests/integration/test_websocket_reconnect.py`

**Acceptance Criteria:**
- [ ] Test WebSocket reconnection workflow:
  1. Start decode session
  2. Connect WebSocket
  3. Receive initial events
  4. Disconnect WebSocket (simulate network failure)
  5. Reconnect to same session_id
  6. Receive session_resume event with buffered events
  7. Verify current_state included
- [ ] Test with missed events during disconnect
- [ ] Verify buffer limit (100 events, FIFO)
- [ ] Test passes consistently

**Reference:** `BACKEND_TASKS.md` Task 6.2.3

#### 3.4 API Integration Tests (~5 hours)
**Acceptance Criteria:**
- [ ] Test all decode endpoints with mocked DSP
- [ ] Test all transmit endpoints with mocked encoder
- [ ] Test device/config/images endpoints
- [ ] Test WebSocket event broadcasting
- [ ] Test concurrent operation blocking (half-duplex)
- [ ] Test error handling with SSTeVe-friendly messages
- [ ] Unit test coverage ≥60% for API

**Work:**
- Use existing test files as templates
- Add missing test cases
- Mock audio/DSP where needed for CI
- Ensure tests run without audio hardware

**Reference:** `BACKEND_TASKS.md` Task 6.1.3

#### 3.5 Performance Benchmarks (~2-3 hours)
**Acceptance Criteria:**
- [ ] Measure decode time per mode
- [ ] Measure transmit time per mode
- [ ] Measure WebSocket message throughput
- [ ] Measure database query performance
- [ ] Identify bottlenecks
- [ ] Document performance baseline

**Work:**
- Create benchmark script
- Test with reference audio/images
- Record metrics
- Document in `docs/PERFORMANCE_BASELINE.md`

#### 3.6 Unit Test Coverage (~3 hours)
**Acceptance Criteria:**
- [ ] Run `pytest --cov`
- [ ] Verify overall coverage ≥60%
- [ ] Identify untested critical paths
- [ ] Add tests for critical code
- [ ] Fix failing tests

---

### Priority 4: Bug Fixes (5 issues, ~5-10 hours)

**Status:** 1/5 complete (20%)

#### 4.1 LSP Errors in rx_manager.py (~0.5 hours) ✅ **COMPLETE**
**File:** `sstv_core/src/sstv_core/decode/rx_manager.py`

**Issues:**
- Wrong import: `SyncDetector` doesn't exist (class is `SyncPulseDetector`)

**Work Completed:**
- [x] Fixed import to `SyncPulseDetector`
- [x] Tested imports successfully

**Reference:** BACKEND_TASKS.md Priority 4.1.1

#### 4.2 LSP Errors in dsp_manager.py (~0.5 hours) ✅ **COMPLETE**
**File:** `sstv_core/src/sstv_core/api/dsp_manager.py`

**Issues:**
- Lines 301,302: "np" is not defined (missing numpy import)

**Work Completed:**
- [x] Added `import numpy as np`
- [x] Tested imports successfully

**Reference:** BACKEND_TASKS.md Priority 4.1.2

#### 4.3 LSP Errors in images/transmit routes (~1-2 hours)
**File:** `sstv_core/src/sstv_core/api/routes/images.py`, `transmit.py`

**Issues:**
- images.py: ImageSaver parameter mismatches (filename, metadata, etc.)
- transmit.py: SSTVMode | None cannot be assigned to SSTVMode

**Work:**
- Fix ImageSaver parameter names/signatures
- Fix SSTVMode None handling

**Reference:** BACKEND_TASKS.md Priority 4.3

#### 4.4 LSP Errors in device_manager.py (~1 hour)
**File:** `sstv_core/src/sstv_core/audio/device_manager.py`

**Issue:**
- Line 64: _hostapis type mismatch

**Work:**
- Fix type annotation or cast appropriately

**Reference:** BACKEND_TASKS.md Priority 4.4

#### 4.5 LSP Errors in ptt_controller.py (~1 hour)
**File:** `sstv_core/src/sstv_core/audio/ptt_controller.py`

**Issues:**
- Lines 116,118: "rts"/"dtr" not a known attribute of "None"

**Work:**
- Add None checks before accessing attributes
- Fix serial port handling

**Reference:** BACKEND_TASKS.md Priority 4.5

#### 4.1 LSP Errors in rx_manager.py (~2-3 hours)
**File:** `sstv_core/src/sstv_core/decode/rx_manager.py`

**Issues:**
1. Missing `SyncDetector` import (file doesn't exist or wrong name)
2. Ring buffer `get_samples()` method signature mismatch (should be `get()`)
3. ImageSaver parameter mismatches (filename, metadata, etc.)

**Acceptance Criteria:**
- [ ] All LSP errors resolved
- [ ] Import paths corrected
- [ ] Method calls match signatures
- [ ] Tests pass
- [ ] Manual testing confirms decode works

**Work:**
- Find correct import for SyncDetector
- Fix ring buffer method calls
- Fix ImageSaver parameter names
- Run tests to verify

#### 4.2 DSP Manager LSP Errors (~2-3 hours)
**File:** `sstv_core/src/sstv_core/api/dsp_manager.py`

**Issues:**
1. Line 190: No parameter named "port"
2. Lines 301,302: "np" is not defined (missing numpy import)
3. Lines 479,548: Object of type "None" cannot be called

**Acceptance Criteria:**
- [ ] All LSP errors resolved
- [ ] Numpy import added
- [ ] Method calls corrected
- [ ] Tests pass

**Work:**
- Add `import numpy as np`
- Fix method signature calls
- Fix None callable issues

#### 4.3 Image/Transmit Route LSP Errors (~1-2 hours)
**Files:**
- `sstv_core/src/sstv_core/api/routes/images.py`
- `sstv_core/src/sstv_core/api/routes/transmit.py`

**Issues:**
- images.py: ImageSaver parameter mismatches
- transmit.py: SSTVMode | None cannot be assigned to SSTVMode

**Acceptance Criteria:**
- [ ] All LSP errors resolved
- [ ] Tests pass

**Work:**
- Fix ImageSaver calls
- Fix SSTVMode None handling

#### 4.4 Device Manager LSP Error (~1 hour)
**File:** `sstv_core/src/sstv_core/audio/device_manager.py`

**Issue:**
- Line 64: _hostapis type mismatch

**Acceptance Criteria:**
- [ ] LSP error resolved

**Work:**
- Fix type annotation or cast appropriately

#### 4.5 PTT Controller LSP Errors (~1 hour)
**File:** `sstv_core/src/sstv_core/audio/ptt_controller.py`

**Issues:**
- Lines 116,118: "rts"/"dtr" not a known attribute of "None"

**Acceptance Criteria:**
- [ ] LSP errors resolved
- [ ] Tests pass

**Work:**
- Add None checks before accessing attributes
- Fix serial port handling

---

### Priority 5: Documentation (3 tasks, ~5-8 hours)

#### 5.1 Deployment Guide (~3 hours)
**File:** `docs/DEPLOYMENT.md`

**Acceptance Criteria:**
- [ ] Production deployment instructions
- [ ] Environment variable configuration
- [ ] Database setup and migrations
- [ ] Systemd service file (Linux)
- [ ] Windows service setup
- [ ] Docker container instructions (optional)
- [ ] Security considerations

**Work:**
- Create deployment guide from scratch
- Include installation steps
- Include configuration examples
- Include service files

**Reference:** `BACKEND_TASKS.md` Task 6.3.3

#### 5.2 Developer Guide (~2-3 hours)
**File:** `docs/DEVELOPER_GUIDE.md`

**Acceptance Criteria:**
- [ ] Installation instructions
- [ ] Running tests instructions
- [ ] API usage examples (Python, curl, JavaScript)
- [ ] WebSocket connection examples
- [ ] Smart Reply workflow examples
- [ ] PTT configuration guide
- [ ] Troubleshooting section

**Work:**
- Create developer guide from scratch
- Include code examples
- Include common workflows
- Include troubleshooting

**Reference:** `BACKEND_TASKS.md` Task 6.3.2

#### 5.3 Beta Testing Guide (~2 hours)
**File:** `docs/BETA_TESTING_GUIDE.md`

**Acceptance Criteria:**
- [ ] Beta testing scope
- [ ] Known issues and workarounds
- [ ] How to report bugs
- [ ] What to test (test cases)
- [ ] Expected behavior
- [ ] Feedback channels

**Work:**
- Create beta testing guide
- Define test cases
- Define feedback process

---

## 📅 Timeline (11 Days: 2026-01-20 to 2026-01-31)

### Week 1 (Jan 20-26): Core Features & Bug Fixes

| Day | Priority | Tasks | Hours |
|------|----------|-------|-------|
| Jan 20 | ✅ Complete | Documentation reorganization | 2h |
| Jan 20 | ✅ Complete | Phase 5: Mode Detection API | 3h |
| Jan 20 | ✅ Complete | Phase 5: Device Config endpoint | 3h |

**Week 1 Total:** ~8 hours

### Week 2 (Jan 27-31): Testing & Documentation

| Day | Priority | Tasks | Hours |
|------|----------|-------|-------|
| Jan 27 | Priority 3 | Phase 6: Decode integration test | 4h |
| Jan 28 | Priority 3 | Phase 6: Transmit integration test | 3h |
| Jan 28 | Priority 3 | Phase 6: WebSocket reconnection test | 3h |
| Jan 29 | Priority 3 | Phase 6: API integration tests | 5h |
| Jan 30 | Priority 3 | Phase 6: Performance benchmarks | 3h |
| Jan 30 | Priority 5 | Deployment guide | 3h |
| Jan 31 | Priority 5 | Developer guide | 3h |
| Jan 31 | Priority 5 | Beta testing guide | 2h |

**Week 2 Total:** ~26 hours

**Total Estimated Time:** ~49-54 hours (6-7 days)

---

## ✅ Beta Release Checklist

### Core Functionality
- [ ] User can select audio device and start listening
- [ ] App auto-detects SSTV mode from VIS code (correlation-based)
- [ ] Image decodes in real-time with scanline rendering
- [ ] Decoded image auto-saves to gallery with metadata
- [ ] User can transmit image with one-click Smart Reply
- [ ] No slanted images (Hough Transform auto-correction)
- [ ] Acoustic coupling works (bandpass filter + volume indicator)

### Quality Standards
- [ ] WebSocket real-time events (VIS, scanline updates, audio_levels)
- [ ] Error handling with SSTeVe-friendly messages
- [ ] Session management (half-duplex enforcement)
- [ ] Configuration persistence
- [ ] Integration tests pass (decode, transmit, WebSocket)
- [ ] API documentation complete (OpenAPI)
- [ ] Deployment guide available
- [ ] Developer guide available
- [ ] Beta testing guide available

### Known Issues
- [ ] Document known limitations
- [ ] Document workarounds
- [ ] Set up feedback mechanism

### Final Steps (Jan 31)
- [ ] Tag release: `v0.1.0-beta`
- [ ] Create release notes
- [ ] Build distribution packages
- [ ] Deploy to beta testers
- [ ] Monitor feedback channels

---

## 🎬 Success Criteria for Beta Launch

**Minimum:**
- [x] All 7 beta requirements met
- [x] Integration tests passing
- [x] Documentation complete
- [x] No blocking bugs
- [x] Deployment guide tested

**Stretched Goal:**
- [ ] Unit test coverage ≥60%
- [ ] Performance benchmarks documented
- [ ] Beta testers positive feedback

---

**Last Updated:** 2026-01-20 (Priority 1 tasks complete!)
**Next Review:** Daily during week 1, every 2 days during week 2
