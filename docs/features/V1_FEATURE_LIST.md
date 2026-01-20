# SSTeVe v1.0 - Minimal Feature List

**Last Updated:** 2026-01-16
**Implementation Status:** ~50-60% complete (backend focus)
**Success Criteria:** "Calm to leave running, reliably produces decodes without constant babysitting"

## ⚠️ Status Update (2026-01-16)

**Backend Status:**
- ✅ Core DSP modules complete (decoders, encoders, PTT)
- ✅ Database schema and migrations
- ✅ Smart features (Smart Reply, QSO Logging)
- ❌ API not wired to DSP (simulation only)
- ❌ Critical DSP features missing (auto-slant, VIS, bandpass, audio levels)

**Frontend Status:**
- ✅ UI components exist (CaptureView, TransmitView, LogView)
- ⚠️ Integration pending (waiting for API wiring)

**See `PROJECT_STATUS.md` for detailed status.**

---

## Core Workflow (Minimum Viable Experience)

### 1. First Launch → Listening → First Decode → Review

**User completes this sequence successfully:**

1. **Open app** → Lands on Receive view
2. **Select audio input** (once) → Device remembered for next session
3. **Click "Start Listening"** → App begins passive monitoring
4. **SSTV signal detected** → Visual feedback (no alarms)
5. **Image decodes** → Auto-saved to history with metadata
6. **User reviews** → Opens History, sees image with timestamp/mode/quality
7. **User adds note** → "ISS pass, strong signal" (optional)

**If this workflow succeeds, v1 is viable.**

---

## Feature Matrix

### ✅ Essential (Ship-Blocker)

These features are required for the app to fulfill its core purpose.

#### **Receive (Passive Listening)**

| Feature | Description | Backend Requirement |
|---------|-------------|---------------------|
| **Audio input selection** | Dropdown of available devices, persists selection | `GET /devices/audio` |
| **Start/Stop listening** | Single button to begin/end monitoring | `POST /decode/start`, `DELETE /decode/stop` |
| **SSTV mode detection** | Auto-detect VIS code (Robot 36, Martin M1, Scottie S1) | Decoder VIS detection |
| **Live decode canvas** | Real-time scanline rendering as image builds | WebSocket `/ws/decode/{session_id}` |
| **Status progression** | Calm visual feedback: Listening → VIS → Sync → Decoding → Complete | WebSocket events |
| **Auto-save on completion** | Image saved to history with metadata (no confirmation) | `POST /images` (internal) |
| **Toast notification** | "Saved to history" (bottom-right, 2-second fade) | Frontend only |
| **Manual SYNC button** | Override sync detection (SPACE or S key) | `POST /decode/force-sync` |

**Operating Condition:**
- Canvas dominates viewport (60-70% width)
- Controls collapsed to narrow sidebar (expandable with C key)
- No flashing/reactive telemetry by default

---

#### **History (Memory Layer)**

| Feature | Description | Backend Requirement |
|---------|-------------|---------------------|
| **Chronological gallery** | Table: Timestamp, Mode, Callsign (if detected), Quality | `GET /images` |
| **Image detail view** | Full-size preview, metadata display | `GET /images/{id}` |
| **Notes field** | Textarea for user annotations (optional, saves on blur) | `PATCH /images/{id}` |
| **Basic metadata** | Auto-captured: Time (UTC + local), Mode, Quality score, Audio source | Decoder output |

**Gallery feels calm:**
- No pagination (infinite scroll acceptable)
- Images displayed with generous whitespace
- Quality scores visible but not alarming (87% is fine, not a warning)

---

#### **Transmit (Send Image)**

| Feature | Description | Backend Requirement |
|---------|-------------|---------------------|
| **Image upload** | Drag-drop or file picker (PNG/JPEG/BMP) | Frontend file handling |
| **Mode selection** | Dropdown: Scottie S1, Martin M1, Robot 36 | Encoder mode parameter |
| **Output device selection** | Dropdown of available audio devices | `GET /devices/audio` |
| **PTT method selection** | Radio buttons: None / Serial / VOX | `POST /transmit` with ptt_config |
| **Serial PTT configuration** | Port selector, RTS/DTR checkboxes, Pre/Post-TX delay sliders | PTT controller params |
| **Transmit confirmation** | Modal: "Transmit on [device] using [mode]?" → Confirm/Cancel | Frontend only |
| **Transmit progress** | Progress bar with scanline counter | WebSocket `/ws/transmit/{session_id}` |

**Prevent accidents:**
- Confirmation modal required (no auto-transmit)
- Disable transmit button until image loaded
- Clear feedback during transmission ("Transmitting line 120/256...")

**Smart defaults for readable QSOs:**
- Use high-contrast text colors by default (white/yellow on dark, black on light)
- Avoid red/orange text for callsigns (degrades first at weak signal levels, causes QSO failures)
- *See docs/FIELD_RESEARCH_NOTES.md for weak signal visibility research*

---

#### **Devices (Configuration)**

| Feature | Description | Backend Requirement |
|---------|-------------|---------------------|
| **Audio device enumeration** | List available input/output devices with channels/sample rates | `GET /devices/audio` |
| **Set default device** | Button to persist selection for future sessions | `POST /config/devices` |
| **Input level meter** | Real-time audio level visualization (prevent clipping) | WebSocket `/ws/audio-levels` |
| **Serial port enumeration** | List available COM/USB ports for PTT | `GET /devices/serial` |
| **Test PTT button** | Trigger PTT signal without transmitting (verify hardware) | `POST /devices/serial/test-ptt` |

**Configuration is bounded:**
- Separate view (not cluttering Receive screen)
- Clear navigation (sidebar icon)
- Changes persist across sessions

---

#### **Settings (Operating Conditions)**

| Feature | Description | Backend Requirement |
|---------|-------------|---------------------|
| **Operating Conditions modes** | Cool (blue-gray) / Warm (sepia) / Field (high contrast) | Frontend theme state |
| **Motion & Animation** | Full / Reduced / Minimal (eye fatigue consideration) | Frontend animation intensity |
| **Auto-save preference** | Toggle: Auto-save (Mode A) vs Confirmation sheet (Mode B) | Frontend + backend save behavior |
| **Image format** | Default save format: PNG / JPEG / BMP | `POST /images` format parameter |
| **Save location** | Path input for image storage directory | Backend file I/O |

**Settings are reversible:**
- Clear "Reset to Defaults" button
- Changes apply immediately (no "Save" button required)
- Modal closes with Escape key

---

### ⚠️ Important (Should Have for v1, Defer if Blocked)

These features significantly improve UX but are not ship-blockers.

| Feature | Description | Rationale |
|---------|-------------|-----------|
| **Command palette** | Cmd+K / Ctrl+K opens fuzzy search for all actions | Power user efficiency |
| **Keyboard shortcuts** | SPACE (manual sync), C (toggle controls), H (history), Escape (cancel) | Desktop app expectation |
| **Advanced Decoder drawer** | Relocate Gain, AFC, Slant controls to separate modal (Cmd+D) | Keeps Receive screen calm |
| **Squelch control** | Threshold slider + OPEN/CLOSED indicator (prevents false triggers) | Essential for noisy environments |
| **Force Mode override** | Checkbox to disable VIS auto-detection (use selected mode) | Handles corrupted VIS codes |
| **Waterfall spectrum** | FFT visualization with frequency markers (1200/1500/2300 Hz) | Visual confidence for signal presence |
| **Quality score display** | Show decode confidence % during/after completion | Helps user decide to keep/discard |

**If time allows:** Implement all. If blocked, defer to v1.1 in priority order (Command palette → Keyboard shortcuts → Advanced Decoder).

---

### 🔮 Future (Explicitly Out of Scope for v1)

These features align with DESIGN_MANTRA but are deferred to later versions.

| Feature | Rationale for Deferral |
|---------|------------------------|
| **Auto-session grouping** | "Tonight's ISS pass" time-proximity clustering | Requires heuristics, can be manual for v1 |
| **Search/filter in History** | Full-text search across notes, mode filters | Manual table scanning acceptable for v1 |
| **Favorites/keep forever** | Star system for important decodes | Users can add notes "FAVORITE" for v1 |
| **Export/share** | Batch export to ZIP, share via email/social | Users can navigate to save directory for v1 |
| **Retry with Different Mode** | One-click re-decode with mode override | Users can stop/change mode/start for v1 |
| **Mark as Partial** | Explicit "partial decode" flag alongside quality score | Quality % is sufficient indicator for v1 |
| **Slant correction** | Manual rotation adjustment + auto-detect | Rarely needed, defer to advanced features |
| **Callsign overlay (TX)** | Station ID burned into transmitted image | Nice-to-have, not essential for basic TX |
| **Image adjustments (TX)** | Brightness/Contrast sliders before transmit | Users can edit in external app for v1 |
| **Multiple SSTV modes** | PD, Pasokon, BW modes beyond Robot/Martin/Scottie | Start with popular 3 modes, expand in v1.1+ |

---

## Backend API Requirements (Python Core)

### REST Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/devices/audio` | GET | List available audio input/output devices |
| `/devices/serial` | GET | List available serial ports for PTT |
| `/devices/serial/test-ptt` | POST | Trigger PTT signal (hardware test) |
| `/config/devices` | POST | Persist default device selection |
| `/decode/start` | POST | Begin listening on specified device |
| `/decode/stop` | DELETE | Stop current decode session |
| `/decode/force-sync` | POST | Override automatic sync detection |
| `/transmit` | POST | Transmit image with PTT control |
| `/images` | GET | Retrieve saved images with metadata |
| `/images` | POST | Save decoded image (internal, called by auto-save) |
| `/images/{id}` | GET | Retrieve single image with full metadata |
| `/images/{id}` | PATCH | Update image metadata (notes, callsign, etc.) |

### WebSocket Events

| Event | Direction | Payload | Purpose |
|-------|-----------|---------|---------|
| `vis_detected` | Server → Client | `{mode: "Robot 36", frequency: 1200}` | VIS code identified |
| `sync_acquired` | Server → Client | `{confidence: 0.95}` | Sync pulse locked |
| `scanline_update` | Server → Client | `{line: 120, data: [...], progress: 0.47}` | Real-time scanline for canvas |
| `decode_complete` | Server → Client | `{image_id: "...", quality: 0.92}` | Decode finished, image saved |
| `error` | Server → Client | `{code: "AUDIO_DEVICE_LOST", message: "..."}` | Recoverable/fatal errors |
| `audio_levels` | Server → Client | `{left: -12.3, right: -14.1}` | Real-time input levels (dBFS) |
| `ptt_status` | Server → Client | `{keyed: true}` | PTT state for TX progress |
| `transmit_progress` | Server → Client | `{line: 180, total: 256}` | TX scanline counter |

---

## UI Layout Constraints (Mantra-Aligned)

### Receive View (CaptureView)

**Default Layout:**
- Canvas: 60-70% width (fluid, responsive)
- Controls sidebar: 80px width (collapsed, icons + tooltips)
- Status rail: Above canvas (horizontal stepper)
- Telemetry: Hidden by default (toggle with T key)

**Expanded Controls (C key):**
- Controls sidebar: 320px width (shows labels, sliders)
- Canvas: Adjusts to remaining space (min 50% width)

**During Active Decode:**
- Controls auto-collapse to maximize canvas
- Status rail shows: "Decoding line 120/256 (47%)"
- Toast notification on completion: "Saved to history"

---

### History View (LogView)

**Layout:**
- Left: Table (50% width, scrollable)
- Right: Detail panel (50% width, image + metadata + notes)

**Calm Gallery Principles:**
- No pagination stress (infinite scroll or "Load More" button)
- Generous whitespace between rows
- Quality scores visible but not alarming:
  - 90-100%: success-600 (green)
  - 70-89%: warning-500 (amber)
  - <70%: neutral-400 (gray, not red)

---

### Transmit View (TransmitView)

**Layout:**
- Left: Mode selection + PTT config (320px)
- Center: Image preview with upload dropzone (fluid)
- Right: Output device + Transmit button (280px)

**Confirmation Modal:**
- Title: "Confirm Transmission"
- Body: "Transmit [filename] on [device] using [mode]?"
- Actions: Confirm (primary) / Cancel (secondary)
- Keyboard: Enter (confirm), Escape (cancel)

---

### Devices View (DevicesView)

**Layout:**
- Two sections: Audio Devices | PTT Configuration
- Audio: Two-column table (Input | Output)
- PTT: Conditional sections based on method selection (None/Serial/VOX)

---

## Success Metrics (Post-Launch Validation)

**Mantra Section 14: Success Criteria**

> "The app is successful if it feels calm to leave running, reliably produces decodes without constant babysitting, the history/gallery stays tidy over time, saving and annotating is effortless, advanced controls exist without cluttering the main experience."

**Measurable Indicators:**

1. **Time to First Decode:**
   - Target: <2 minutes from launch to first saved image
   - Measured: User completes: Open app → Select device → Start listening → Decode → Review in history

2. **Control Interaction Frequency:**
   - Target: <3 control adjustments per decode session
   - Measured: Log clicks on gain/AFC/squelch/mode during passive listening
   - **If users constantly adjust, defaults are wrong**

3. **History Tidiness:**
   - Target: >80% of saved images have user-added notes within 24 hours
   - Measured: Note field edit events vs total saved images
   - **If notes are empty, users aren't engaged with "memory" concept**

4. **Canvas Visibility:**
   - Target: Canvas visible >90% of decode time
   - Measured: Viewport analysis (is canvas occluded by controls?)
   - **If users expand controls frequently, layout fails "calm" principle**

5. **Auto-Save Adoption:**
   - Target: <10% of users switch to Confirmation Sheet mode (Mode B)
   - Measured: Settings toggle for auto-save preference
   - **If many users disable auto-save, passive posture fails**

---

## Non-Goals (Explicitly Excluded from v1)

**To maintain "calm, patient, confident" posture:**

1. **No real-time contest logging** - Complex QSO management deferred to v2
2. **No CAT radio control** - Frequency tuning via external apps (gqrx, SDR++)
3. **No built-in waterfall tuning** - Users tune radio separately, app decodes audio stream
4. **No image editing** - Brightness/Contrast/Crop deferred or done in external tools
5. **No cloud sync** - Local-first, filesystem-native (images saved as files)
6. **No plugin system** - Core functionality only, extensions deferred to v2+
7. **No multi-mode simultaneous decode** - One SSTV mode at a time (no mode zoo)

**Rationale:** These features increase complexity and violate "passive instrument" posture. If users need them, they're already using dedicated tools (logger apps, SDR software, image editors).

---

## Development Phases (Suggested Order)

### Phase 1: Foundation (Weeks 1-2)
1. Wire backend API endpoints (`/devices/audio`, `/decode/start`, `/decode/stop`)
2. Implement WebSocket for `scanline_update` events
3. Connect CaptureView to real decoder (replace mock state)
4. Render decoded image on canvas (real pixels, not TODO)

### Phase 2: Core Workflow (Weeks 3-4)
5. Implement auto-save on decode completion
6. Add toast notifications ("Saved to history")
7. Wire LogView to saved images database
8. Implement notes field (PATCH `/images/{id}`)

### Phase 3: Transmit (Weeks 5-6)
9. Image upload handling (drag-drop, file picker)
10. Connect TransmitView to encoder
11. Implement PTT control (serial RTS/DTR, VOX preamble)
12. Add transmit progress WebSocket events

### Phase 4: Polish (Weeks 7-8)
13. Redesign CaptureView layout (canvas 60-70%, collapsible controls)
14. Add command palette (Cmd+K)
15. Implement keyboard shortcuts (SPACE, C, H, Escape)
16. Create Advanced Decoder drawer (relocate gain/AFC/slant)
17. Default reactive telemetry to OFF
18. User testing + bug fixes

**Total Estimated Time:** 8 weeks for solo developer (faster with team)

---

## Open Questions (Resolve Before v1 Release)

1. **Squelch Placement:** Primary screen or Advanced Decoder drawer?
   - **Pro primary:** Essential for noisy environments, prevents false triggers
   - **Pro advanced:** Adds visual complexity, most users run in quiet rooms
   - **Decision Required:** User testing with field operators (POTA/SOTA)

2. **Waterfall Necessity:** Is spectrum analyzer essential or nice-to-have?
   - **Pro essential:** Visual confirmation of SSTV signal presence (especially for beginners)
   - **Pro defer:** Adds processing overhead, users can rely on VIS detection
   - **Decision Required:** Validate with "Activators" archetype (field operators)

3. **Quality Score Threshold:** What % triggers "partial decode" warning?
   - Current mock data: 87%, 92%, 95% (all green)
   - **Question:** Is 70% threshold appropriate? Should 50-69% be amber, <50% red?
   - **Decision Required:** Validate with decoder output distribution

4. **Session Auto-Grouping:** Time proximity threshold for "Tonight's ISS pass"?
   - **Options:** 1 hour gap = new session, manual grouping only, or QSO-based grouping
   - **Decision Required:** Defer to v1.1 if complex, validate user need first

5. **Canvas Aspect Ratio:** Fixed 320×256 (Robot 36) or dynamic based on mode?
   - **Options:** Letterbox Martin M1 (320×240), pillarbox Scottie S1 (320×256)
   - **Decision Required:** Validate with UI mockups (does dynamic resize feel calm?)

---

## Deliverables Checklist

**Before v1.0 ships, the following must be true:**

### Functional
- [ ] User can decode Robot 36, Martin M1, Scottie S1 images
- [ ] User can transmit images on those modes
- [ ] Images auto-save to history with metadata
- [ ] Notes field persists user annotations
- [ ] PTT control works (serial RTS/DTR tested on real hardware)
- [ ] Audio device selection persists across sessions
- [ ] Canvas renders real decoded images (not TODO placeholder)
- [ ] WebSocket events update UI in real-time

### UX (Mantra-Aligned)
- [ ] Canvas occupies 60-70% of Receive view
- [ ] Controls can collapse to narrow sidebar (C key)
- [ ] Auto-save is default (no manual button required)
- [ ] Toast notification appears on save ("Saved to history")
- [ ] Reactive telemetry defaults to OFF (whisper, don't flash)
- [ ] Status progression rail shows calm visual feedback
- [ ] Settings modal has clear "Operating Conditions" label (not "Palette Mode")

### Technical
- [ ] Backend API documented (OpenAPI/Swagger)
- [ ] WebSocket events schema defined
- [ ] Error handling covers: Device lost, No VIS detected, Sync failed, PTT error
- [ ] Unit tests for decoder/encoder accuracy (reference images)
- [ ] E2E test for first decode workflow (Playwright)

### Documentation
- [ ] README with installation instructions
- [ ] User guide: "Your First SSTV Decode in 5 Minutes"
- [ ] Troubleshooting: Audio device not found, PTT not working
- [ ] Keyboard shortcuts reference card

---

## Final Guidance

**Before implementing any feature not on this list, ask:**

> "Does this interrupt passive reception?"
> "Could this be a whisper instead of an alert?"
> "Can this be confirmation instead of configuration?"
> "Does this make history lighter, or heavier?"
> "Can advanced stuff live behind an explicit 'Advanced' door?"

**When in doubt, default to less and keep the receive screen calm.**

---

**This feature list defines SSTeVe v1.0 as a "passive reception and decoding instrument" - patient, quiet, and confident.**
