# SSTeVe Project Status

**Last Updated:** 2026-01-16
**Current Focus:** Backend implementation (Phases 4-6) + Critical DSP features

---

## Executive Summary

**Overall Progress:** ~50-60% complete

**What's Working:**
- ✅ Database schema and migrations
- ✅ Core decoder/encoder modules (Scottie S1, Martin M1, Robot 36)
- ✅ Basic API structure (FastAPI + WebSocket scaffolding)
- ✅ Smart features library (Smart Reply, Mode Detection, QSO Logging)
- ✅ CLI tools and accessibility modules

**What's NOT Working:**
- ❌ Real DSP/audio pipeline integration (API → DSP wiring)
- ❌ Live decode/transmit operations
- ❌ WebSocket real-time events
- ❌ **All 4 critical DSP features** (auto-slant, VIS detection, bandpass, audio levels)
- ❌ Filesystem watcher and MMSSTV import
- ❌ Comprehensive testing

---

## Phase Completion Status

| Phase | Status | Progress | Notes |
|-------|--------|----------|-------|
| **Phase 1: Foundation** | ✅ Complete | 17/17 | Core DSP, DB models, audio I/O, PTT control |
| **Phase 2: API Layer** | 🟡 In progress | ~12/21 | Routes scaffolded but not wired to DSP |
| **Phase 3: Accessibility** | 🟡 In progress | ~6/10 | Stereo sonification + CLI done |
| **Phase 4: Filesystem** | ⏳ Pending | 0/7 | Auto-import, MMSSTV compatibility |
| **Phase 5: Smart Features** | 🟡 80% | 12/19 | Smart Reply complete, Mode Detection partial |
| **Phase 6: Testing** | ⏳ Pending | 0/11 | Integration tests, validation |

**Estimated Remaining Work:**
- Phase 4: ~19 hours
- Phase 5 completion: ~20-25 hours
- Phase 6: ~39 hours
- **Critical DSP features: +3-4 weeks**

**Total: ~80 hours + 3-4 weeks DSP work**

---

## Critical Path: Ship-Blocking Features

### 🔴 The "Make-or-Break" DSP Features

Per user research (see `MAKE_OR_BREAK_FEATURES.md`), these 4 features **MUST** be implemented or users will delete the app:

#### 1. ❌ Hough Transform Auto-Slant Correction
**Status:** Not implemented
**Current:** Simple sync pulse detection or manual slider
**Required:** Automatic slant correction using Hough Transform
**Timeline:** +1 week
**Priority:** CRITICAL - Users view slanted images as "broken app"

#### 2. ❌ Correlation-Based VIS Detection
**Status:** Not implemented
**Current:** Simple tone detection
**Required:** High-sensitivity correlation detection
**Timeline:** +1 week
**Priority:** CRITICAL - Mode detection reliability

#### 3. ❌ Bandpass Filter (1200-2300 Hz)
**Status:** Not implemented
**Current:** No acoustic noise rejection
**Required:** Bandpass preprocessing for acoustic coupling
**Timeline:** +3-4 days
**Priority:** CRITICAL - ISS crowd uses phone-to-radio, not cables

#### 4. ❌ Real-Time Audio Level Monitoring
**Status:** Not implemented
**Current:** No WebSocket `audio_levels` event
**Required:** Traffic-light volume indicator (Green/Yellow/Red)
**Timeline:** +2-3 days
**Priority:** CRITICAL - Prevents clipping and weak signals

**Impact:** Without these features, SSTeVe cannot compete with MMSSTV/Black Cat.

---

## API → DSP Wiring Status

**Critical Issue:** API routes exist but are **not connected** to DSP modules.

### Current State (Broken):
```
User → POST /decode/start → session_manager.create_session()
                          → operation_manager.start_decode() ← SIMULATION
                          ❌ rx_manager.receive() ← NOT CALLED
```

### Target State (Working):
```
User → POST /decode/start → session_manager.create_session()
                          → rx_manager.receive() ← REAL DSP
                          → WebSocket events (VIS, scanlines, complete)
                          → Database save
```

**Action Required:** See `API_DSP_WIRING_PLAN.md` (1-2 weeks, 40-60 hours)

---

## Recent Completions (Phase 5)

### ✅ Smart Reply System (5/5 tasks)
- Template Engine with Pillow-based rendering
- Field auto-population with fallback hierarchy
- 3 sample templates (QSL Card, Monitor Frame, Minimal Badge)
- API endpoints: list, generate, transmit
- Hot-reload support for user templates

### ✅ Smart QSO Logging (3/3 tasks)
- Auto-population from image metadata
- ADIF 3.1.4 export
- API endpoints: log, list, export

### 🟡 Smart Mode Detection (1/3 tasks)
- ✅ Sync timing analysis algorithm
- ⏳ API endpoint pending
- ⏳ VIS timeout integration pending

### 🟡 Smart Device Configuration (1/2 tasks)
- ✅ USB VID/PID detection for Digirig, SignaLink, RigBlaster
- ⏳ "Apply Settings" endpoint pending

**See `PHASE5_IMPLEMENTATION_SUMMARY.md` for details.**

---

## Documentation Structure

### Core Specifications
- `backend-spec.md` - Complete backend architecture and API contracts
- `frontend-spec.md` - UI components, interactions, and design system
- `TRANSMIT_SPEC.md` - Transmit feature specification

### Implementation Tracking
- `BACKEND_TASKS.md` - Master task breakdown with progress tracking
- `PHASE[1-5]_IMPLEMENTATION_SUMMARY.md` - Detailed completion reports
- `API_DSP_WIRING_PLAN.md` - Critical next step (API integration)

### Feature Planning
- `MAKE_OR_BREAK_FEATURES.md` - Critical DSP features (updated)
- `V1_FEATURE_LIST.md` - Minimum viable feature checklist
- `DESIGN_RATIONALE.md` - UI design decisions and principles

### API Documentation
- `openapi.json` - OpenAPI schema
- `postman/` - Postman collection for API testing

---

## What Works Right Now

### Core DSP Modules
- ✅ VIS detection (`vis_detector.py`)
- ✅ Sync pulse detection (`sync_detector.py`)
- ✅ Scottie S1/S2/DX decoders
- ✅ Martin M1/M2 decoders
- ✅ Robot 36/72 decoders
- ✅ Image preprocessing and encoding
- ✅ PTT control (serial + VOX)

### Database & Configuration
- ✅ SQLAlchemy models (images, QSOs, configurations)
- ✅ Alembic migrations
- ✅ Configuration singleton pattern

### Smart Features (Library Level)
- ✅ Template engine with field population
- ✅ Mode detection from sync timing
- ✅ Device detection (USB VID/PID)
- ✅ QSO logger with ADIF export

### API Structure
- ✅ FastAPI application with CORS
- ✅ Route modules (decode, transmit, devices, config, images, qso, smart_reply)
- ✅ Pydantic request/response models
- ✅ WebSocket manager structure

---

## What Does NOT Work

### API Integration
- ❌ Decode routes don't call actual DSP (use operation_manager simulation)
- ❌ Transmit routes don't call actual encoder
- ❌ Device routes use mocked data
- ❌ Config routes partially stubbed
- ❌ WebSocket events are synthetic

### DSP Features
- ❌ No Hough Transform slant correction
- ❌ No correlation-based VIS detection
- ❌ No bandpass filter (1200-2300 Hz)
- ❌ No real-time audio level monitoring

### Filesystem Integration (Phase 4)
- ❌ No file system watcher
- ❌ No auto-import of dropped images
- ❌ No MMSSTV directory import

### Testing (Phase 6)
- ❌ No integration tests
- ❌ Limited unit test coverage
- ❌ No end-to-end validation

---

## Next Steps (Priority Order)

### 1. Implement Critical DSP Features (3-4 weeks)
**Priority:** 🔴 CRITICAL - Ship blocker

1. Hough Transform Auto-Slant Correction (+1 week)
2. Correlation-Based VIS Detection (+1 week)
3. Bandpass Filter (1200-2300 Hz) (+3-4 days)
4. Real-Time Audio Level Monitoring (+2-3 days)

**Without these, SSTeVe cannot launch.**

### 2. API-DSP Wiring (1-2 weeks, 40-60 hours)
**Priority:** 🔴 CRITICAL - Blocks all testing

- Wire decode routes to `rx_manager`
- Wire transmit routes to encoder
- Connect WebSocket to real events
- Integrate device enumeration
- Connect config to database

**See `API_DSP_WIRING_PLAN.md` for detailed plan.**

### 3. Complete Phase 5 (~20-25 hours)
**Priority:** 🟡 HIGH - Feature completeness

- Add Mode Detection API endpoint
- Integrate VIS timeout flow
- Add Device Config "Apply Settings"
- Create base images for Smart Reply templates
- Write unit tests for smart features

### 4. Phase 4: Filesystem Integration (~19 hours)
**Priority:** 🟡 HIGH - User convenience

- File system watcher with debouncing
- Image import from metadata parsing
- MMSSTV directory import
- WebSocket library update events

### 5. Phase 6: Testing & Documentation (~39 hours)
**Priority:** 🟢 MEDIUM - Quality assurance

- Unit test suites for all modules
- Integration tests (E2E decode/transmit)
- WebSocket reconnection tests
- API documentation
- Developer guide
- Deployment guide

---

## Technical Debt

### Code Quality
- Some endpoints use in-memory storage instead of database
- Operation manager simulation code should be removed after wiring
- Missing error handling in several routes
- Configuration model missing fields (station_callsign, default_frequency_hz)

### Documentation
- OpenAPI schema incomplete (missing some endpoints)
- No migration guide from MMSSTV
- Missing troubleshooting documentation
- Template creation guide incomplete (no base images)

### Testing
- Unit test coverage <50%
- No integration tests
- No performance benchmarks
- No stress testing (concurrent sessions)

---

## Dependencies & Constraints

### External Dependencies (Already in requirements.txt)
- `sounddevice>=0.4.6` - Audio I/O
- `numpy>=1.24`, `scipy>=1.10` - DSP
- `Pillow>=10.0` - Image processing
- `fastapi>=0.104`, `uvicorn>=0.24` - API
- `sqlalchemy>=2.0`, `alembic>=1.12` - Database
- `pyserial>=3.5` - PTT control
- `websockets>=12.0` - Real-time events

### Development Constraints
- Must maintain headless core (no UI coupling)
- API-first communication only
- SQLite for persistence (no external DB required)
- Cross-platform (Windows, macOS, Linux)

---

## Risk Assessment

### High Risk (Likely to Cause Delays)
- ⚠️ **Critical DSP Features** - Never implemented before, complexity unknown
- ⚠️ **API-DSP Wiring** - Integration bugs likely
- ⚠️ **Performance** - Real-time audio processing untested at scale

### Medium Risk
- ⚠️ **Hough Transform** - Algorithm complexity may exceed 1 week estimate
- ⚠️ **WebSocket Stability** - Reconnection logic untested
- ⚠️ **Cross-Platform Testing** - Limited testing on macOS/Linux

### Low Risk
- Smart features implementation (mostly complete)
- Database schema (stable, migrations work)
- Basic API structure (FastAPI is proven)

---

## Success Criteria for v1.0

### Minimum Viable Experience
1. User can select audio device and start listening
2. App auto-detects SSTV mode from VIS code
3. Image decodes in real-time with scanline rendering
4. Decoded image auto-saves to gallery with metadata
5. User can transmit image with one-click Smart Reply
6. No slanted images (Hough Transform correction)
7. Acoustic coupling works (bandpass filter + volume indicator)

### Not Required for v1.0
- ❌ AI image captioning
- ❌ Smart Template Editor (deferred to v2)
- ❌ Multi-receiver support
- ❌ Full-duplex mode
- ❌ Advanced DSP features (noise reduction, AGC)

---

## Timeline Estimates

### Optimistic (Best Case)
- Critical DSP: 3 weeks
- API wiring: 1 week
- Phase 5 completion: 1 week
- Phase 4: 3 days
- Phase 6: 1 week
**Total: ~7 weeks**

### Realistic (Expected)
- Critical DSP: 4 weeks
- API wiring: 2 weeks
- Phase 5 completion: 1.5 weeks
- Phase 4: 1 week
- Phase 6: 1.5 weeks
**Total: ~10 weeks**

### Pessimistic (Worst Case)
- Critical DSP: 6 weeks (if Hough Transform is complex)
- API wiring: 3 weeks (integration bugs)
- Phase 5 completion: 2 weeks
- Phase 4: 1.5 weeks
- Phase 6: 2 weeks
**Total: ~14-15 weeks**

---

## Resources

### Key Documents
- `BACKEND_TASKS.md` - Authoritative task list
- `backend-spec.md` - Architecture reference
- `API_DSP_WIRING_PLAN.md` - Next critical step
- `MAKE_OR_BREAK_FEATURES.md` - Ship-blocking features

### Code Locations
- Core DSP: `sstv_core/src/sstv_core/{decode,encode,audio}/`
- API Layer: `sstv_core/src/sstv_core/api/`
- Smart Features: `sstv_core/src/sstv_core/smart_features/`
- Database: `sstv_core/src/sstv_core/database/`

---

**Last Review:** 2026-01-16
**Next Review:** After API-DSP wiring or critical DSP implementation
