# SSTeVe Documentation

**Last Updated:** 2026-01-20

---

## 📍 Start Here

**New to the project?** Read these in order:

1. **`docs/README.md`** (this file) - Documentation index
2. **`status/PROJECT_STATUS.md`** - Current implementation status, what works/doesn't work
3. **`core/backend-spec.md`** - Complete backend architecture and API contracts
4. **`core/frontend-spec.md`** - UI components, interactions, and design system

**Planning a beta launch?** Read this first:
- **`BETA_LAUNCH_PLAN.md`** - ⭐ Roadmap to beta release (2026-01-31 target)

---

## 📁 Documentation Structure

```
docs/
├── README.md                        # THIS FILE - Documentation index
├── BETA_LAUNCH_PLAN.md            # ⭐ Beta launch roadmap (Jan 31 target)
├── core/                            # Core specifications and API contracts
├── status/                          # Project status and phase summaries
├── features/                        # Feature specifications and tracking
├── design/                          # Design rationale and decisions
├── reference/                       # Reference documentation
├── archive/                         # Historical/archived docs
└── postman/                         # API testing collections
```

---

## 📚 Documentation by Category

### Core Specifications (`core/`)

**What's here:** Architectural specifications and API contracts

- **`core/backend-spec.md`** - Python core engine, REST API, WebSocket, database schema
  - DSP pipeline architecture
  - API endpoint specifications
  - WebSocket event contracts
  - Database models and migrations

- **`core/frontend-spec.md`** - UI components, interactions, and design system
  - Component specifications
  - User workflows
  - Design tokens and principles

- **`core/TRANSMIT_SPEC.md`** - Transmit feature specification
  - Image preprocessing
  - PTT control
  - Audio encoding

- **`core/openapi.json`** - OpenAPI 3.0 schema
  - Auto-generated from FastAPI
  - Complete API contract
  - Use with Swagger/Redoc tools

---

### Project Status (`status/`)

**What's here:** Current implementation status and phase completion reports

- **`status/PROJECT_STATUS.md`** - ⭐ **Master project status document**
  - Executive summary (70-75% complete)
  - What's working / what's not working
  - Phase completion status
  - Next steps and timeline estimates
  - Risk assessment

- **`status/PHASE1_IMPLEMENTATION_SUMMARY.md`** - Foundation phase completion
  - Core DSP, DB models, audio I/O, PTT control (17/17 complete)

- **`status/PHASE2_IMPLEMENTATION_SUMMARY.md`** - API layer completion
  - FastAPI routes, WebSocket manager, Pydantic models (21/21 complete)

- **`status/PHASE3_IMPLEMENTATION_SUMMARY.md`** - Accessibility & modes completion
  - Stereo sonification, CLI, Martin M1, Robot 36

- **``status/PHASE3.5_IMPLEMENTATION_SUMMARY.md`** - Additional modes
  - Martin M2, Robot 72, PD series

- **`status/PHASE5_IMPLEMENTATION_SUMMARY.md`** - Smart features completion
  - Smart Reply, Mode Detection, QSO Logging (19/19 complete)

---

### Feature Specifications (`features/`)

**What's here:** Feature specifications and implementation tracking

- **`features/CRITICAL_DSP_IMPLEMENTATION.md`** - ⭐ **All 4 critical DSP features**
  - Hough Transform auto-slant correction (implemented 2026-01-20)
  - Correlation-based VIS detection (implemented 2026-01-20)
  - Bandpass filter (1200-2300 Hz, implemented 2026-01-20)
  - Real-time audio level monitoring (implemented 2026-01-20)

- **`features/V1_FEATURE_LIST.md`** - Minimum viable feature checklist
  - Required features for v1.0 release
  - Nice-to-have features (deferred to v2.0)

- **`features/FSKID_SPECIFICATION.md`** - FSKID mode specification
  - Frequency-shift keyed identification
  - Auto-RSV signal reports

- **`features/AUTO_RSV_SPECIFICATION.md`** - AUTO-RSV mode specification
  - Receiver Status Verification
  - Automatic RSV generation

---

### Design Documentation (`design/`)

**What's here:** Design decisions and rationale

- **`design/DESIGN_RATIONALE.md`** - UI design decisions and principles
  - Design philosophy (friendly & nerdy voice)
  - Component decisions
  - Color palette and spacing
  - UX research insights

---

### Reference Documentation (`reference/`)

**What's here:** Historical and reference documentation

- **`reference/README.md`** - Original project overview
  - Project background
  - Technology stack
  - Development environment

---

### Archived Documentation (`archive/`)

**What's here:** Historical/archived documentation (no longer actively maintained)

- **`archive/FSKID_IMPLEMENTATION_PLAN.md`** - Original FSKID implementation plan
- **`archive/FSKID_RSV_IMPLEMENTATION_STATUS.md`** - FSKID+AUTO-RSV tracking

---

### API Testing (`postman/`)

**What's here:** API testing collections

- **`postman/SSTeVe.postman_collection.json`** - Complete API test collection
  - All endpoints configured
  - Environment variables
  - Test cases for critical flows

---

## 🚀 Quick Reference

### What's Complete?

**Core Foundation (Phase 1):**
- ✅ Database schema and migrations
- ✅ Core DSP modules (decoders, encoders, PTT)
- ✅ Audio I/O primitives
- ✅ Configuration management

**API Layer (Phase 2):**
- ✅ FastAPI application structure
- ✅ All route modules (decode, transmit, devices, config, images, qso, smart_reply)
- ✅ WebSocket manager
- ✅ Pydantic request/response models
- ✅ API-DSP wiring (rx_manager, tx_manager)

**Accessibility & Modes (Phase 3):**
- ✅ Stereo sonification for slant correction
- ✅ Verbose CLI mode
- ✅ Martin M1, Robot 36 decoders/encoders
- ✅ Scottie S2/DX, Martin M2, Robot 72, PD series modes

**Smart Features (Phase 5):**
- ✅ Smart Reply system (5/5 tasks complete)
- ✅ Smart QSO Logging (3/3 tasks complete)
- ✅ Smart Mode Detection (partial - 1/3 tasks)
- ✅ Smart Device Configuration (partial - 1/2 tasks)

**Critical DSP Features (2026-01-20):**
- ✅ Hough Transform auto-slant correction
- ✅ Correlation-based VIS detection (-15 dB SNR)
- ✅ Bandpass filter (1200-2300 Hz)
- ✅ Real-time audio level monitoring (WebSocket @ 10Hz)

---

### What's NOT Working?

- ❌ Filesystem integration (Phase 4) - File system watcher, MMSSTV import
- ❌ Comprehensive testing (Phase 6) - Integration tests, validation
- ⚠️ Minor LSP errors in rx_manager.py (pre-existing)

---

### Current Focus

**Remaining work by priority:**

1. **Phase 4: Filesystem Integration** (~19 hours)
   - File system watcher with debouncing
   - Image auto-import from metadata
   - MMSSTV directory import
   - WebSocket library update events

2. **Phase 6: Testing & Documentation** (~39 hours)
   - Unit test suites for all modules
   - Integration tests (E2E decode/transmit)
   - WebSocket reconnection tests
   - API documentation completion
   - Developer guide
   - Deployment guide

3. **Minor Issues:**
   - Resolve pre-existing LSP errors
   - Complete remaining Phase 5 tasks (Mode Detection API, Device Config endpoint)
   - Test with real audio hardware

---

## 📖 Documentation by Role

### For Backend Developers

**Start here:** `core/backend-spec.md`

Then read:
1. `status/PROJECT_STATUS.md` - Current implementation state
2. `features/CRITICAL_DSP_IMPLEMENTATION.md` - Critical DSP features (complete!)
3. `status/PHASE[1-5]_IMPLEMENTATION_SUMMARY.md` - What's been implemented

**Key questions:**
- How do I integrate with the API? → `core/backend-spec.md`
- What DSP modules are available? → `status/PHASE1_IMPLEMENTATION_SUMMARY.md`
- What's the database schema? → `core/backend-spec.md` §2.1
- What are the WebSocket events? → `core/backend-spec.md` §3.2

---

### For Frontend Developers

**Start here:** `core/frontend-spec.md`

Then read:
1. `design/DESIGN_RATIONALE.md` - Design principles
2. `core/openapi.json` - API contracts
3. `status/PROJECT_STATUS.md` - Backend readiness

**Key questions:**
- What components should I build? → `core/frontend-spec.md`
- What's the design system? → `design/DESIGN_RATIONALE.md`
- What API endpoints are available? → `core/openapi.json`
- What WebSocket events should I handle? → `core/backend-spec.md` §3.2

---

### For Project Managers

**Start here:** `status/PROJECT_STATUS.md`

Then read:
1. `features/V1_FEATURE_LIST.md` - v1.0 feature scope
2. `features/CRITICAL_DSP_IMPLEMENTATION.md` - Critical features (complete!)
3. `status/PHASE[1-5]_IMPLEMENTATION_SUMMARY.md` - Progress tracking

**Key questions:**
- What's the current status? → `status/PROJECT_STATUS.md`
- What's remaining for v1.0? → `status/PROJECT_STATUS.md` + `features/V1_FEATURE_LIST.md`
- What's the timeline? → `status/PROJECT_STATUS.md` timeline estimates
- What are the risks? → `status/PROJECT_STATUS.md` risk assessment

---

### For Contributors

**Start here:** `status/PROJECT_STATUS.md`

Then read:
1. `core/backend-spec.md` - Architecture overview
2. `features/V1_FEATURE_LIST.md` - Task list
3. `features/CRITICAL_DSP_IMPLEMENTATION.md` - Critical features (reference)

**Key questions:**
- How do I get started? → `reference/README.md` (development environment)
- What should I work on? → `status/PROJECT_STATUS.md` (next steps)
- How do I test my changes? → `status/PHASE[1-5]_IMPLEMENTATION_SUMMARY.md`
- What's the architecture? → `core/backend-spec.md`

---

## 🔍 Finding Information

### "How do I...?"

**...understand the current status?**
→ Read `status/PROJECT_STATUS.md`

**...see what features are implemented?**
→ Read `features/CRITICAL_DSP_IMPLEMENTATION.md` (critical features)
→ Read `status/PHASE[1-5]_IMPLEMENTATION_SUMMARY.md` (phase-by-phase)

**...see what tasks are pending?**
→ Check `status/PROJECT_STATUS.md` - "Next Steps" section
→ Check `features/V1_FEATURE_LIST.md` - v1.0 feature checklist

**...understand the architecture?**
→ Read `core/backend-spec.md` (backend architecture)
→ Read `core/frontend-spec.md` (UI architecture)

**...know what's critical for v1?**
→ Read `features/CRITICAL_DSP_IMPLEMENTATION.md` (all 4 features complete!)

**...see the API contracts?**
→ Check `core/openapi.json` (OpenAPI schema)
→ Run FastAPI server and visit `/docs` (Swagger UI)

**...test the API?**
→ Use `postman/SSTeVe.postman_collection.json`
→ Import into Postman and run test collections

**...understand design decisions?**
→ Read `design/DESIGN_RATIONALE.md`

**...find historical information?**
→ Check `archive/` folder for FSKID and other feature docs
→ Check `reference/README.md` for original project overview

---

## 📝 Documentation Maintenance

### When to Update

- **`status/PROJECT_STATUS.md`** - Update after major milestones
- **`status/PHASE*_IMPLEMENTATION_SUMMARY.md`** - Create when phase completes
- **`core/openapi.json`** - Regenerate when API changes (use `scripts/export_api_docs.py`)
- **`features/CRITICAL_DSP_IMPLEMENTATION.md`** - Update when critical features change
- **Core specs** - Update when architecture changes
- **`postman/SSTeVe.postman_collection.json`** - Update when endpoints change

### File Naming Conventions

- **`FEATURE_NAME.md`** - Feature specifications (e.g., `FSKID_SPECIFICATION.md`)
- **`PHASE#_IMPLEMENTATION_SUMMARY.md`** - Phase completion reports
- **`STATUS_TYPE.md`** - Status tracking (e.g., `PROJECT_STATUS.md`)
- **`SPEC_TYPE-spec.md`** - Architecture specs (e.g., `backend-spec.md`)
- **`README.md`** - Index/overview documents

### Status Markers

- ✅ Complete
- 🟡 In progress / Partial
- ⏳ Pending / Not started
- ❌ Not implemented / Blocked
- ⚠️ Issues / Warnings
- ⭐ Important / Starting point

---

## 📊 Project Completion

**Overall Progress:** ~70-75% complete

| Phase | Status | Progress | Notes |
|-------|--------|----------|-------|
| **Phase 1: Foundation** | ✅ Complete | 17/17 | Core DSP, DB models, audio I/O, PTT control |
| **Phase 2: API Layer** | ✅ Complete | 21/21 | Routes + DSP wiring + WebSocket events |
| **Phase 3: Accessibility** | ✅ Complete | 10/10 | Stereo sonification + CLI + accessibility modules |
| **Phase 4: Filesystem** | ⏳ Pending | 0/7 | Auto-import, MMSSTV compatibility |
| **Phase 5: Smart Features** | 🟡 90% | 17/19 | Smart Reply, QSO logging complete; Mode/Device partial |
| **Phase 6: Testing** | ⏳ Pending | 0/11 | Integration tests, validation |

**Estimated Remaining Work:**
- Phase 4: ~19 hours
- Phase 5 completion: ~5 hours
- Phase 6: ~39 hours
- **Total: ~63 hours (1.5 weeks)**

---

## 🗑️ Removed Documentation

The following files were removed as stale/redundant (consolidated into specs):

**Removed 2026-01-16:**
- `BACKEND_TASKS.md` - 548-line task breakdown (superseded by status/PHASE summaries)
- `API_DSP_WIRING_PLAN.md` - Implementation planning (completed)
- `MAKE_OR_BREAK_FEATURES.md` - Feature tracking (now in `features/CRITICAL_DSP_IMPLEMENTATION.md`)

**Removed earlier:**
- Early UX research docs (consolidated into specs)
- Project manifest and workflow docs
- Agent instruction docs (moved to project root)

---

## 💡 Tips for New Contributors

1. **Start with status** - Read `status/PROJECT_STATUS.md` to understand current state
2. **Understand architecture** - Review `core/backend-spec.md` for backend, `core/frontend-spec.md` for UI
3. **Check critical features** - All 4 critical DSP features are complete (see `features/CRITICAL_DSP_IMPLEMENTATION.md`)
4. **Use API docs** - `core/openapi.json` and `/docs` endpoint are authoritative
5. **Test with Postman** - Import `postman/SSTeVe.postman_collection.json` to explore API
6. **Ask questions** - Refer to specific docs when asking for help

---

**Questions?** Check `status/PROJECT_STATUS.md` first, then refer to specific documents above.
