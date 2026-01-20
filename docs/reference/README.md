# SSTeVe Documentation

**Last Updated:** 2026-01-16

This directory contains all technical documentation for the SSTeVe SSTV platform.

---

## 📍 Start Here

**New to the project?** Read these in order:

1. **`PROJECT_STATUS.md`** - Current implementation status, what works/doesn't work
2. **`backend-spec.md`** - Complete backend architecture and API contracts
3. **`BACKEND_TASKS.md`** - Master task breakdown with progress tracking

---

## 📚 Core Documentation

### Specifications
- **`backend-spec.md`** - Python core engine, REST API, WebSocket, database schema
- **`frontend-spec.md`** - UI components, interactions, design system
- **`TRANSMIT_SPEC.md`** - Transmit feature specification

### Implementation Tracking
- **`PROJECT_STATUS.md`** - **⭐ Executive summary** of project status
- **`BACKEND_TASKS.md`** - Master task list with detailed breakdowns
- **`PHASE[1-5]_IMPLEMENTATION_SUMMARY.md`** - Completion reports for each phase
- **`API_DSP_WIRING_PLAN.md`** - Critical next step (connect API to DSP modules)

### Feature Planning
- **`MAKE_OR_BREAK_FEATURES.md`** - Critical DSP features (ship-blockers)
- **`V1_FEATURE_LIST.md`** - Minimum viable feature checklist
- **`DESIGN_RATIONALE.md`** - UI design decisions and principles

### API Documentation
- **`openapi.json`** - OpenAPI 3.0 schema
- **`postman/`** - Postman collection for API testing

---

## 🚀 Quick Reference

### What's Complete?
✅ Database schema and migrations
✅ Core DSP modules (decoders, encoders, PTT)
✅ Smart features (Smart Reply, Mode Detection, QSO Logging)
✅ API structure (FastAPI routes, Pydantic models)

### What's NOT Working?
❌ API not wired to DSP (simulation only)
❌ Critical DSP features (auto-slant, VIS, bandpass, audio levels)
❌ WebSocket real-time events
❌ Filesystem integration
❌ Comprehensive testing

### Current Focus
**API-DSP Wiring** - Connect API routes to actual DSP modules
**Critical DSP Features** - Implement 4 ship-blocking features
**See:** `API_DSP_WIRING_PLAN.md` and `MAKE_OR_BREAK_FEATURES.md`

---

## 📖 Documentation by Role

### For Backend Developers
1. `backend-spec.md` - Architecture reference
2. `BACKEND_TASKS.md` - Task breakdown
3. `API_DSP_WIRING_PLAN.md` - Critical implementation plan
4. `PHASE[1-5]_IMPLEMENTATION_SUMMARY.md` - What's been done

### For Frontend Developers
1. `frontend-spec.md` - UI component specifications
2. `DESIGN_RATIONALE.md` - Design principles
3. `openapi.json` - API contracts

### For Project Managers
1. `PROJECT_STATUS.md` - Executive summary
2. `BACKEND_TASKS.md` - Progress tracking
3. `MAKE_OR_BREAK_FEATURES.md` - Critical features

### For Contributors
1. `PROJECT_STATUS.md` - Current state
2. `backend-spec.md` - Architecture overview
3. `BACKEND_TASKS.md` - Find tasks to work on

---

## 📋 Phase Implementation Summaries

- **`PHASE1_IMPLEMENTATION_SUMMARY.md`** - Foundation (Core DSP, DB, Audio I/O)
- **`PHASE2_IMPLEMENTATION_SUMMARY.md`** - API Layer (FastAPI, WebSocket)
- **`PHASE3_IMPLEMENTATION_SUMMARY.md`** - Accessibility & Additional Modes
- **`PHASE3.5_IMPLEMENTATION_SUMMARY.md`** - Additional modes (Martin M1, Robot 36)
- **`PHASE5_IMPLEMENTATION_SUMMARY.md`** - Smart Automation (Smart Reply, QSO Logging)

Missing:
- Phase 4 summary (Filesystem integration - not started)
- Phase 6 summary (Testing - not started)

---

## 🔍 Finding Information

### "How do I...?"

**...understand the current status?**
→ Read `PROJECT_STATUS.md`

**...see what tasks are pending?**
→ Check `BACKEND_TASKS.md`

**...understand the architecture?**
→ Read `backend-spec.md`

**...know what's critical for v1?**
→ Read `MAKE_OR_BREAK_FEATURES.md`

**...integrate the API with DSP?**
→ Follow `API_DSP_WIRING_PLAN.md`

**...see the API contracts?**
→ Check `openapi.json` or run the API server and visit `/docs`

**...understand UI design decisions?**
→ Read `DESIGN_RATIONALE.md`

---

## 🗑️ Removed Documentation

The following files were removed on 2026-01-16 as stale/redundant:

- `DESIGN_MANTRA.md` - Early philosophy (superseded by specs)
- `RESEARCH_MANTRA_ANALYSIS.md` - Exploratory analysis
- `COMPONENT_MANTRA_MAPPING.md` - Outdated UI mapping
- `FRONTEND_MANTRA_ALIGNMENT.md` - Outdated frontend analysis
- `FIELD_RESEARCH_NOTES.md` - Raw research notes
- `USER_JOURNEYS.md` - Early UX (now in specs)
- `USER_WORKFLOW.md` - Early UX (now in specs)
- `USER_EXPERIENCE_WALKTHROUGH.md` - Early UX (now in specs)
- `BACKEND_AGENT.md` - Agent instructions (moved to project root CLAUDE.md)

The insights from these documents have been consolidated into the current specifications and status documents.

---

## 📝 Documentation Standards

### File Naming
- **ALL_CAPS.md** - Major documents (specs, summaries, status)
- **lowercase-dash.md** - Standard specs
- **PHASE#_*.md** - Implementation summaries

### Status Markers
- ✅ Complete
- 🟡 In progress
- ⏳ Pending
- ❌ Not implemented / Blocked
- ⚠️ Issues / Warnings

### Update Frequency
- `PROJECT_STATUS.md` - Update after major milestones
- `BACKEND_TASKS.md` - Update as tasks complete
- `PHASE*_IMPLEMENTATION_SUMMARY.md` - Create when phase completes
- Specs - Update when architecture changes

---

**Questions?** Check `PROJECT_STATUS.md` first, then refer to specific documents above.
