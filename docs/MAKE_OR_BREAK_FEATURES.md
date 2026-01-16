# Make-or-Break Features: Implementation Status

**Source:** User research synthesis - features that cause app deletion if missing
**Last Updated:** 2026-01-16
**Purpose:** Track critical DSP features identified as ship-blockers

---

## ⚠️ **CRITICAL STATUS UPDATE (2026-01-16)**

**All 4 critical DSP features are NOT IMPLEMENTED in the current backend.**

Per `BACKEND_TASKS.md` Reality Check section:
- ❌ Hough Transform Auto-Slant Correction - **NOT IMPLEMENTED** (uses simple sync or manual slider)
- ❌ Correlation-Based VIS Detection - **NOT IMPLEMENTED** (uses simple tone detection)
- ❌ Bandpass Filter (1200-2300 Hz) - **NOT IMPLEMENTED** (no acoustic noise rejection)
- ❌ Real-Time Audio Level Monitoring - **NOT IMPLEMENTED** (no WebSocket `audio_levels` event)

**Impact:** Without these 4 features, users will delete SSTeVe and return to MMSSTV/Black Cat.

**Timeline:** +3-4 weeks backend work to implement all 4 features.

---

## Feature Status Matrix

| # | Feature | Implementation Status | Priority | Timeline |
|---|---------|----------------------|----------|----------|
| 1 | Hough Transform Auto-Slant | ❌ NOT IMPLEMENTED | **CRITICAL** | +1 week |
| 2 | Bandpass Filter (1200-2300 Hz) | ❌ NOT IMPLEMENTED | **CRITICAL** | +3-4 days |
| 3 | Real-Time Audio Level Monitoring | ❌ NOT IMPLEMENTED | **CRITICAL** | +2-3 days |
| 4 | Correlation-Based VIS Detection | ❌ NOT IMPLEMENTED | **CRITICAL** | +1 week |
| 5 | Waterfall Display | ✅ UI Component exists | **HIGH** | Backend wiring needed |
| 6 | Offline Field Day Capability | ✅ Filesystem-native design | **HIGH** | Already covered |
| 7 | Smart Reply System | ✅ IMPLEMENTED (Phase 5) | **HIGH** | Complete |

---

## Feature 1: Hough Transform Auto-Slant

### Research Says:
> "If a user decodes an image and it is tilted due to sample rate mismatch, they view the app as 'broken.' Users are migrating away from legacy apps specifically because they are tired of 'pesky slant' issues."

### SSTeVe Status:

**Frontend Spec (Section 20.2):**
- Auto Mode: "Slant Correction (Auto/Manual with slider)"
- Manual Mode: "Slant Correction toggle (Auto/Manual) with manual slider"

**Python Core:** ❓ Unknown algorithm

**RESEARCH_MANTRA_ANALYSIS Conclusion:**
> "Hough Transform slant correction: Perfectly straight images without manual slider. Research: 'Differentiates from 90% of free market.'"

### Critical Gap:

**We don't know if the Python core uses Hough Transform or simple sync detection.**

**Action Required:**
1. ✅ Review `/to_reuse/python_core/sstv_engine/decoder.py` - does slant correction exist?
2. ✅ If exists: Is it Hough Transform or simple sync pulse detection?
3. ❌ If simple sync: **Backend work required** - upgrade to Hough Transform

**Priority:** 🔴 **CRITICAL - Ship Blocker**

**Rationale:** Research says this is THE differentiator. Users delete apps that produce slanted images.

---

## Feature 2: Acoustic Coupling Optimization ("Driveway Mode")

### Research Says:
> "A huge portion of your user base (especially the ISS crowd) will not use cables; they will hold their phone microphone up to a handheld radio speaker."

### Components Required:

#### 2A: Visual Volume Indicator (Traffic Light)

**Research:**
> "Large, clear 'Traffic Light' (Green/Red) meter that tells the user instantly if the volume is too loud (clipping) or too soft."

**SSTeVe Status:**
- ✅ FRONTEND_MANTRA_ALIGNMENT added specification (Section 7.6): "Real-Time Volume Meter (Acoustic Coupling Guidance)"
- ✅ Location: Always visible in CaptureView, bottom-right corner
- ✅ Visual states: Green (-18dB to -6dB), Yellow (-6dB to -3dB), Red (>-3dB or clipping), Gray (<-40dB)
- ⚠️ Backend: Requires WebSocket event `audio_levels` (left, right, peak, clipping) at 10 Hz

**Action Required:**
1. ✅ Frontend spec updated (already done in FRONTEND_MANTRA_ALIGNMENT)
2. ❓ Verify Python core emits `audio_levels` WebSocket event
3. ❌ If missing: **Backend work required** - add real-time level monitoring

**Priority:** 🔴 **CRITICAL - ISS Event Chaser #1 Pain Point**

---

#### 2B: Noise Gating / Bandpass Filter (1200-2300 Hz)

**Research:**
> "A specific setting to filter out wind noise and background conversations, focusing only on the 1200Hz–2300Hz SSTV range."

**SSTeVe Status:**
- ❓ Python core DSP pipeline unknown
- ❌ Not mentioned in frontend-spec.md
- ❌ Not mentioned in backend-spec.md

**Action Required:**
1. ✅ Check `/to_reuse/python_core/sstv_engine/decoder.py` - is there a bandpass filter?
2. ❌ If missing: **Backend work required** - add 1200-2300 Hz bandpass preprocessing
3. ✅ Frontend: No UI needed (automatic, always active)
4. ⚠️ Optional: Settings toggle "Acoustic Coupling Mode" (enables aggressive noise gating)

**Priority:** 🔴 **CRITICAL - Acoustic Coupling Success Rate**

**Rationale:** Research says users fail to decode because of ambient noise (dog barking, car passing, wind). Bandpass filter is table stakes.

---

## Feature 3: Background Decoding

### Research Says:
> "Mobile users want to leave the phone next to the radio and walk away. If the app stops when the screen sleeps, it is useless for long sessions."

### SSTeVe Status:

**Platform:** Desktop-first (React/Tauri) per CLAUDE.md

**CLAUDE.md:**
> "SSTeVe SSTV Platform - Build-Ready Blueprint: Build a modular SSTV platform with a headless Python core engine exposing a REST API and WebSocket interface, paired with a lightweight React/Tauri **desktop UI**."

**Mobile Support:** Future platform (not v1)

**Verdict:** ❌ **Out of Scope for v1 (Desktop Only)**

**Future Mobile Version:**
- Android: Implement Foreground Service
- iOS: Implement Background Audio session
- Critical for mobile ISS Event Chasers

**Action Required:** None for v1. Document as mobile-platform requirement.

**Priority:** ⚪ **N/A for Desktop v1, CRITICAL for Future Mobile**

---

## Feature 4: High-Sensitivity VIS Detector

### Research Says:
> "Users judge an SSTV app by its ability to 'hear' what they cannot. 'Weak signal' performance is the primary reason users pay for premium apps like Black Cat SSTV."

### Technical Requirement:

**Research (User Research Analysis):**
> "Use Correlation Detection (matched filtering) to identify the VIS header even when it is buried in static. NOT simple tone detection."

**Black Cat SSTV Benchmark:**
- Works at -15 dB SNR (correlation detection)
- Free apps fail at -5 dB SNR (simple tone detection)

### SSTeVe Status:

**Frontend Spec (Section 20.3):**
- "Auto-detect runs on 'Start Capture' click"
- No mention of VIS detection algorithm

**Python Core:** ❓ Unknown algorithm

**Action Required:**
1. ✅ Review `/to_reuse/python_core/sstv_engine/decoder.py` - VIS detection method?
2. ✅ Check for correlation detection vs simple tone detection
3. ❌ If simple tone: **Backend work required** - upgrade to correlation-based VIS detection

**Implementation Notes:**
- Correlation detection: Cross-correlate incoming audio with known VIS waveforms
- Even if VIS is buried at -15 dB SNR, correlation peak identifies mode
- Black Cat's "killer feature" - this is how they justify $25 price

**Priority:** 🔴 **CRITICAL - Primary Differentiator**

**Rationale:** Research says users switch to Black Cat specifically for weak signal VIS detection. If SSTeVe can match this, it's a major competitive advantage.

---

## Feature 5: Waterfall + Timeline View

### Research Says:

#### 5A: Live Waterfall
> "A scrolling spectrogram that allows users to tap on a signal to tune to it."

**SSTeVe Status:**
- ✅ Waterfall exists in frontend-spec.md (Section 20.4)
- ✅ Location: Bottom 25% of canvas (Auto Mode) or dedicated section (Manual Mode)
- ✅ Scrolling: 10-30 seconds of history
- ⚠️ Interaction: "Tap to Tune" mentioned but deferred to Advanced Controls drawer

**Action Required:**
- ✅ Keep waterfall as specified
- ⚠️ "Tap to Tune" = advanced feature (not passive posture) - remains in Advanced Controls

**Priority:** ✅ **Covered**

---

#### 5B: Timeline View (Chat-Style History)

**Research:**
> "Received images should appear in a chronological feed (like a chat history), not a gallery grid."

**SSTeVe Status:**
- ⚠️ Frontend spec has `LogView` (table + detail panel)
- ⚠️ FRONTEND_MANTRA_ALIGNMENT renamed to `GalleryView` (table + detail panel)
- ❌ No "timeline view" (chat-style bubbles)

**Conflict Analysis:**

| Aspect | Research Wants | SSTeVe Spec |
|--------|----------------|-------------|
| **Layout** | Vertical timeline with bubbles (WhatsApp-style) | Table (left) + Detail panel (right) |
| **Metaphor** | Messaging app (Signal, WhatsApp) | Photo gallery (Apple Photos, Google Photos) |
| **Posture** | Conversational (active) | Review later (passive) |

**This is the "Chat Interface Paradigm" from earlier research.**

**DESIGN_MANTRA Decision (Section 9):**
> "History should behave like a calm gallery: chronological by default, searchable/filterable."

**Mantra chose Gallery, Research wants Timeline.**

### Critical Question:

**Are "Timeline View" and "Gallery View" the same thing, or different?**

**Possible Interpretation 1:** Timeline = chronological list (which Gallery already is)
- If this is the case: ✅ Already covered (GalleryView shows chronological table)

**Possible Interpretation 2:** Timeline = chat bubbles (not table)
- If this is the case: ⚠️ Conflicts with Gallery paradigm

**Action Required:**
- ✅ Clarify with user: Does "Timeline View" mean chronological table, or chat-style bubbles?
- ⚠️ If chat bubbles: This is the conversational UI we deferred (2-3 months of work)

**Priority:** 🟡 **HIGH - Needs Clarification**

---

## Feature 6: Offline Field Day Capability

### Research Says:
> "The app must be fully functional offline. It should save images to the local device gallery automatically and allow for log creation without a server connection."

### SSTeVe Status:

**Architecture (CLAUDE.md):**
> "Local-first, filesystem-native (images saved as files)."

**Frontend Spec (Section 19.4):**
- `POST /images` saves decoded image to database + filesystem
- Gallery reads from local database

**Backend Spec:** API is local (not cloud-dependent)

**Verdict:** ✅ **Already Covered**

**SSTeVe is desktop-first with local Python core. No internet required.**

**Priority:** ✅ **Satisfied**

---

## Feature 7: Smart Template Editor

### Research Says:
> "Users should be able to create a 'Reply' template where the `{Callsign}` and `{RST}` (Signal Report) are automatically filled in based on the station they just received."

### SSTeVe Status:

**V1_FEATURE_LIST (Transmit):**
> "Minimum Viable Transmit (v1): User uploads a PNG/JPEG (pre-created in external app), selects mode, clicks Transmit. No text overlays, no templates, no macros."

**Frontend Spec (Section 19.2 - TransmitPage):**
- `TransmitImagePanel`: Image upload, mode selection, brightness/contrast
- No template editor, no macro system

**RESEARCH_MANTRA_ANALYSIS:**
> "Template editor is a 2-month feature (layer engine, text rendering, macro parser). Serves HF Ragchewers (active conversation, not mantra target). REJECT for v1."

### Critical Conflict:

**Research says:** "Template editor is make-or-break."

**SSTeVe v1 spec says:** "Basic TX only, no templates."

### Why This Matters:

**Target Archetype Split:**
- **ISS Event Chasers** (passive RX, rarely TX) → Don't need templates
- **HF Ragchewers** (active conversation, rapid TX replies) → NEED templates

**If templates are "make-or-break," then HF Ragchewers will delete SSTeVe v1 and use MMSSTV.**

**This is acceptable IF the strategic target is ISS Event Chasers (passive), NOT HF Ragchewers (active).**

### Decision Required:

**Option A: Keep v1 Scope (No Templates)**
- Target: ISS Event Chasers (passive RX, basic TX for field operators)
- HF Ragchewers continue using MMSSTV for conversational SSTV
- Template editor deferred to v2+ if demand exists

**Option B: Add Templates to v1 (Scope Expansion)**
- Serve both ISS Event Chasers AND HF Ragchewers
- Template editor = +2-3 months development
- Timeline: 8 weeks → 16+ weeks

**Option C: Minimal Template System (Compromise)**
- Single template with 3 macros: `{Callsign}`, `{RST}`, `{MyCallsign}`
- Text overlay only (no image layers, no drag-drop)
- Timeline: +2-3 weeks (not 2-3 months)

**My Recommendation:** **Option C (Minimal Template System)**

**Rationale:**
- Research says this is "make-or-break"
- User research shows: "The random text is hard... I'm not quick enough to do random text on the fly"
- Minimal template (text overlay with macros) gives 80% of the value with 20% of the effort
- Still serves passive posture (user pre-creates template once, reuses it)

**Priority:** 🔴 **CRITICAL - Decision Required Before UI Redesign**

---

## Summary: Critical Gaps Identified

### Backend Verification Required (Can't Ship Without Answers):

1. ❓ **Hough Transform slant correction** - Does Python core have this? (Make-or-break)
2. ❓ **Correlation VIS detection** - Simple tone detect or correlation? (Make-or-break)
3. ❓ **Bandpass filter (1200-2300 Hz)** - Is acoustic noise rejection built in? (Make-or-break)
4. ❓ **Real-time audio level monitoring** - Does backend emit `audio_levels` WebSocket event? (Make-or-break)

**Action:** Review Python core DSP pipeline immediately. These 4 features are non-negotiable per research.

---

### Frontend Specification Gaps:

5. ⚠️ **Timeline View vs Gallery View** - Need clarification: Chronological table or chat bubbles? (Make-or-break)
6. ⚠️ **Template Editor** - Research says make-or-break, v1 spec says deferred. Decision required. (Make-or-break)

**Action:** Clarify Timeline View interpretation + decide on template editor scope before finalizing UI redesign.

---

### Already Covered (No Action):

7. ✅ **Waterfall display** - Spec'd correctly
8. ✅ **Offline capability** - Desktop-first architecture satisfies this
9. ✅ **Volume meter** - Added in FRONTEND_MANTRA_ALIGNMENT

---

## Prioritized Action Items

### Before UI Redesign Can Proceed:

**CRITICAL (Ship Blockers):**
1. 🔴 Review Python core slant correction algorithm (Hough or simple sync?)
2. 🔴 Review Python core VIS detection algorithm (correlation or tone detect?)
3. 🔴 Review Python core audio preprocessing (bandpass filter exists?)
4. 🔴 Review Python core WebSocket events (audio_levels emitted?)
5. 🔴 Decide on template editor scope (v1 or v2? Minimal or full-featured?)
6. 🔴 Clarify "Timeline View" (chronological table OK or need chat bubbles?)

**HIGH (Critical UX):**
7. 🟡 Verify acoustic coupling optimizations are feasible with current backend
8. 🟡 Update frontend spec with volume meter (already done in FRONTEND_MANTRA_ALIGNMENT)

**If any of the 6 CRITICAL items are missing/wrong, SSTeVe will not compete with MMSSTV/Black Cat per user research.**

---

## Next Steps

1. **Backend Review Session:** Answer the 4 backend questions (Hough, Correlation VIS, Bandpass, Audio Levels)
2. **Strategic Decision:** Template editor scope (v1 minimal, v1 full, or v2 defer?)
3. **UX Clarification:** Timeline View = table or bubbles?
4. **Update Specs:** Incorporate make-or-break features into frontend-spec-v2.md

**Timeline Impact:**
- If backend has all 4 DSP features: ✅ No delay
- If backend missing 1-2 features: ⚠️ +1-2 weeks backend work
- If backend missing 3-4 features: 🔴 +3-4 weeks backend work (reconsidering feasibility)
- If template editor added (minimal): ⚠️ +2-3 weeks
- If template editor added (full): 🔴 +8-12 weeks

**Can't finalize UI redesign until these 6 questions are answered.**
