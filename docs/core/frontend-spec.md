
---
title: SSTeVe Frontend Specification - UI/UX & Implementation Blueprint
created: 2025-12-27
derived-from: app-spec.md (branding cleanup)
status: Interaction spec — visual prescription intentionally removed
brand: SSTeVe (Friendly & Nerdy)
scope: Frontend interaction, UX, and implementation blueprint; React/Tauri Desktop App
---

# SSTeVe Frontend Specification

This document defines the frontend **interaction design, UX, and implementation
blueprint** for the SSTeVe desktop UI (React/Tauri).

**For backend/API specifications, see:** `backend-spec.md`
**For durable product truth (users, constraints, principles), see:** `../../PRODUCT.md`

> **Scope note (2026-08-05).** This spec previously carried a palette, typography, and
> design-token system that contradicted a second, equally unimplemented spec. Neither
> was ever built. All visual prescription has been removed so a future visual direction
> can be chosen deliberately rather than inherited by accident.
>
> What remains here is behavior: state machines, component contracts, API mappings,
> error and empty states, accessibility criteria, and the viewport/no-scroll
> constraint. Those are real decisions and still apply.
>
> **Update (2026-08-07).** Two things changed since the note above:
>
> 1. **A visual proposal now exists** — `DESIGN.md`, proven in a working prototype at
>    `prototype/`. The visual world is no longer an open decision in the sense this note
>    described; it is a leading, unshipped candidate.
> 2. **The user archetypes this spec references are retired.** Makers, Activators,
>    Preppers, and Old Guard were unsourced spec inheritance, replaced by operating
>    situations in `PRODUCT.md` "Users". Wherever this document justifies a design
>    choice *by archetype* — notably the Auto/Manual split in §20 — that justification
>    no longer stands. The underlying tension (novice simplicity vs. operational
>    flexibility) is real and remains explicitly undecided.
>
> `PRODUCT.md` is authoritative wherever it conflicts with this document.

---

## 7. SSTeVe UI Concept

### 7.1 Tone

**Intent:** SSTeVe should feel like a helpful radio buddy who's really into SSTV:
friendly, nerdy, and genuinely excited to help without being condescending.

Tone reference: an instrument panel on a well-used workbench — not a lab bench, and not
a themed "darkroom" experience.

Visual expression of that tone (palette, typography, texture, motion vocabulary) is
undecided. See PRODUCT.md § Brand Commitments.

### 7.2 SSTeVe Terminology (UI Vocabulary)

| Domain Concept | SSTeVe Term |
|----------------|------------|
| Start Receive | Listen (F5) |
| Stop Receive | Stop Listening |
| Receiving | Listening / Decoding |
| Decode Progress | Progress (n%) |
| Image Saved | Decode Complete |
| Signal Strength | Signal Level / SNR |
| Mode Selection | SSTV Mode |
| Gallery | Log / Gallery |
| Received Images | Received Images |

Use this vocabulary consistently across buttons, labels, documentation, and audio cues. Keep language simple and friendly - SSTeVe talks like a helpful radio buddy, not a formal instrument.

### 7.3 Decode Experience

Replace the "darkroom" metaphor with a clear decode workflow:
- Primary action: `Listen` (F5) on the main view.
- Status rail across the top of the canvas:
  - `Listening → VIS Detected → Sync Lock → Decoding → Decode Complete`
- Canvas behavior:
  - Show scanline sweep as lines are decoded.
  - On lock, subtly slow the sweep and show lock confidence (0–100%).
  - On completion, the image eases into its final position over ~600–800ms (no theatrical fade).
- Audio (optional): short, analog-flavored confirmation tone on decode complete.

### 7.4 First-Run Experience

**Trigger:** First app launch (empty database, no prior captures).

**Welcome Panel:**
- Title: "Hey! I'm SSTeVe"
- Body copy:
  - "I can help you receive and transmit SSTV images."
  - "Want to decode something? You can start with your radio, or try a sample signal first."
- Actions:
  - `Try a Sample Decode` → Play bundled SSTV audio through the core engine and walk through a full decode.
  - `Set Up Devices` → Open Devices & PTT panel.

**Sample Decode Flow:**
- Runs through the same decode pipeline as a real signal.
- Shows the status rail transitions and the final "Decode Complete" state.
- Automatically writes a first log entry (source: Sample) so users see how received images accumulate over time.

The first-run experience should feel like a helpful friend showing you how things work, not a formal tutorial or one-off "demo mode" gimmick.

---

## SSTeVe SSTV Platform - Build-Ready Blueprint

Build a modular SSTV platform with a headless Python core engine exposing a REST API and WebSocket interface, paired with a lightweight React/Tauri desktop UI. Serve the operating situations in `PRODUCT.md` "Users" through strategic feature choices: PTT control for field ops, stereo sonification for eyes-free operation, and SSTeVe's friendly & nerdy brand voice. Smart automation removes friction without brittle complexity. Gamification and AI extras are explicitly deferred beyond the MVP. (Archetype framing retired 2026-08-07.)

---

## 19. Frontend Implementation Blueprint (SSTeVe)

This section translates the SSTeVe UI concept into implementation-facing structures for a Tauri/React app.

### 19.1 Route & View Structure

Treat each primary view as a route (even in a desktop app):

- `/capture` → CaptureView
- `/transmit` → TransmitView
- `/log` → LogView
- `/devices` → DevicesView
- Field Mode → overlay or `/field` that reuses capture/transmit logic with a simplified layout.

Initial route: `/capture`.

### 19.2 Component Inventory (React)

**Global Shell**
- `AppShell`
  - Props: none (top-level)
  - Children: `TopBar`, `SideNav`, `RouteOutlet`.
- `TopBar`
  - Props: `appState: "idle" | "listening" | "capturing" | "pictureLocked" | "txActive" | "error"`, `snr: number | null`.
- `SideNav`
  - Props: `currentRoute: string`, `onNavigate(route: string)`.

**Capture**
- `CapturePage`
  - Props: none (reads from store)
  - Children: `CaptureControls`, `CaptureCanvas`, `CaptureTelemetry`.
- `CaptureControls`
  - Props:
    - `modes: ModePreset[]`
    - `selectedModeId: string`
    - `inputDevices: AudioDevice[]`
    - `selectedInputId: string | null`
    - `stereoGuidanceEnabled: boolean`
    - `slantErrorDeg: number | null`
    - `locked: boolean`
    - `onModeChange(id: string)`
    - `onInputChange(id: string)`
    - `onToggleGuidance()`
    - `onStartCapture()`
    - `onStopCapture()`
    - `isCapturing: boolean`
- `CaptureCanvas`
  - Props:
    - `status: "idle" | "listening" | "vis" | "locked" | "decoding" | "complete" | "error"`
    - `progress: number` (0–100)
    - `lockConfidence: number | null`
    - `imageUrl: string | null`
    - `scanlineCount: { current: number; total: number } | null`
- `StatusRail`
  - Props: `status`, `lockConfidence` (as above)
- `CaptureTelemetry`
  - Props:
    - `snr: number | null`
    - `rms: number | null`
    - `peak: number | null`
    - `bufferHealth: "good" | "ok" | "bad"`
    - `events: CaptureEvent[]`

**Transmit**
- `TransmitPage`
  - Children: `TransmitImagePanel`, `TransmitOutputPanel`.
- `TransmitImagePanel`
  - Props:
    - `image: LoadedImage | null`
    - `modes: ModePreset[]`
    - `selectedModeId: string`
    - `onImageSelect(file: File)`
    - `onModeChange(id: string)`
    - `adjustments: { brightness: number; contrast: number }`
    - `onAdjustmentsChange(partial: Partial<Adjustments>)`
- `TransmitOutputPanel`
  - Props:
    - `outputDevices: AudioDevice[]`
    - `selectedOutputId: string | null`
    - `pttConfig: PttConfig`
    - `onOutputChange(id: string)`
    - `onPttConfigChange(partial: Partial<PttConfig>)`
    - `onTestPtt()`
    - `onPlayTestTone()`
    - `onTransmit()`
    - `onCancelTransmit()`
    - `txState: { status: "idle" | "transmitting" | "complete" | "error"; progress: number; remainingSec: number | null }`

**Log**
- `LogPage`
  - Children: `LogFilters`, `LogList`, `LogDetail`.
- `LogFilters`
  - Props: `filters: LogFiltersState`, `onChange(partial: Partial<LogFiltersState>)`.
- `LogList`
  - Props:
    - `entries: ImageLogEntry[] | QsoLogEntry[]`
    - `viewMode: "grid" | "list"`
    - `selectedId: string | null`
    - `onSelect(id: string)`
    - `onLoadMore()`
- `LogDetail`
  - Props:
    - `entry: ImageLogEntry | QsoLogEntry | null`
    - `onRedeocodeFromAudio(id: string)`
    - `onAssociateQso(id: string)`
    - `onOpenInFolder(id: string)`
    - `onUpdateNotes(id: string, notes: string)`

**Devices**
- `DevicesPage`
  - Children: `AudioDevicesPanel`, `PttPanel`, `DefaultsPanel`.
- `AudioDevicesPanel`
  - Props:
    - `inputs: AudioDevice[]`
    - `outputs: AudioDevice[]`
    - `selectedInputId: string | null`
    - `selectedOutputId: string | null`
    - `onSelectInput(id: string)`
    - `onSelectOutput(id: string)`
    - `onPlayTestTone()`
    - `onMonitorInput()`
- `PttPanel`
  - Props:
    - `pttConfig: PttConfig`
    - `onPttConfigChange(partial: Partial<PttConfig>)`
    - `onTestPtt()`
    - `testStatus: "idle" | "testing" | "success" | "failure"`
- `DefaultsPanel`
  - Props:
    - `defaultsSummary: string`
    - `isDefaultEnabled: boolean`
    - `onToggleDefault()`

**Field Mode**
- `FieldModePage`
  - Props: none (reads from store)
  - Includes: big Capture/Transmit buttons, simplified meters, mode chips, small log strip.

### 19.3 Frontend Store Shape (Zustand)

Types shown in TypeScript-esque pseudocode.

```ts
type AppState = {
  routing: {
    currentRoute: "/capture" | "/transmit" | "/log" | "/devices" | "/field";
  };
  capture: {
    status: "idle" | "listening" | "vis" | "locked" | "decoding" | "complete" | "error";
    sessionId: string | null;
    selectedModeId: string;
    selectedInputId: string | null;
    stereoGuidanceEnabled: boolean;
    lockConfidence: number | null;
    progress: number; // 0-100
    scanline: { current: number; total: number } | null;
    lastImage: ImageLogEntry | null;
    events: CaptureEvent[];
    error: string | null;
  };
  transmit: {
    status: "idle" | "transmitting" | "complete" | "error";
    txId: string | null;
    image: LoadedImage | null;
    selectedModeId: string;
    selectedOutputId: string | null;
    progress: number; // 0-100
    remainingSec: number | null;
    error: string | null;
  };
  devices: {
    inputs: AudioDevice[];
    outputs: AudioDevice[];
    serialPorts: SerialPort[];
    selectedInputId: string | null;
    selectedOutputId: string | null;
    pttConfig: PttConfig;
    testStatus: "idle" | "testing" | "success" | "failure";
  };
  log: {
    pictures: ImageLogEntry[];
    qsos: QsoLogEntry[];
    pictureFilters: LogFiltersState;
    qsoFilters: LogFiltersState;
    selectedPictureId: string | null;
    selectedQsoId: string | null;
    hasMorePictures: boolean;
    hasMoreQsos: boolean;
  };
  field: {
    enabled: boolean;
  };
};
```

Include actions in the store for each major event (e.g., `startCapture`, `receiveDecodeEvent`, `finishCapture`, `startTransmit`, `updateTransmitProgress`, `completeTransmit`, `setDevices`, `updatePttConfig`, `appendLogEntries`).

### 19.4 API → UI Mapping

**Capture**
- `Start Capture` button:
  - Calls `POST /decode/start` with `{ mode, device_id, enable_auto_save }`.
  - On success: store `sessionId`, set `status = "listening"`, open WebSocket `ws/decode/{sessionId}`.
- WebSocket events `vis_detected`, `scanline_update`, `decode_complete`, `error`:
  - Map to `capture.events` and update `status`, `progress`, `scanline`, `lockConfidence`, `lastImage` as appropriate.
- `Stop Capture` button:
  - Calls `POST /decode/stop/{sessionId}`.
  - Closes WebSocket and sets `status = "idle"` (or `"error"` if failure).

**Transmit**
- `Transmit` button:
  - Calls `POST /transmit` with `{ image_path, mode, device_id, ptt_method }`.
  - On success: store `txId`, set `status = "transmitting"`, open `ws/transmit/{txId}`.
- WebSocket events `tx_progress`, `tx_complete`, `error`:
  - Map to `transmit.progress`, `remainingSec`, `status`, and `error`.
- `Cancel transmit` (if implemented):
  - Calls `POST /transmit/cancel/{txId}` and sets `status = "idle"`.

**Devices**
- On Devices view mount or on demand:
  - `GET /devices/audio` → set `devices.inputs`, `devices.outputs`.
  - `GET /devices/serial` → set `devices.serialPorts`.
- `Test PTT` button:
  - Executes a dedicated endpoint, or reuses `/transmit` with special test-flag image and audio suppressed in UI.

**Log**
- `GET /images` with filters → populate `log.pictures` and `hasMorePictures`.
- `GET /images/{id}` → used to populate detail view when needed.
- `GET /qsos` / `GET /qsos/{id}` similarly for QSO tab.

**Propagation**
- On Capture view mount, and on demand thereafter:
  - `GET /propagation?band={band}` → set `propagation.state` (`OPEN` | `CLOSED` |
    `STORM` | `UNKNOWN`), `propagation.explanation`, and the indices behind disclosure.
  - `503` → set `propagation.state = "unavailable"` and surface the response's
    `detail.message` and `detail.suggested_action`. Do **not** fall back to an empty
    or neutral panel; see 19.5.
- The verdict sentence (`explanation`) is the primary rendering. `solar_flux`,
  `k_index`, `a_index`, `sunspots`, and `xray` sit behind progressive disclosure.
- Poll no faster than the source updates (~15 min); this is not a live instrument.

### 19.5 Error & Empty States (Per View)

**Capture**
- Empty: show message and `Start Capture` button.
- No input devices: show warning banner with link to Devices view.
- Error from WebSocket or decode:
  - Set `status = "error"`, display inline message (`"We lost this one – [reason]"`) and a `Retry` button.

**Transmit**
- No image selected: disable `Transmit` with tooltip (`"Load an image to start"`).
- No output device: inline warning and disabled `Transmit`.
- PTT error (HTTP 500): show inline banner in PTT panel with `"Transmit without PTT"` option.

**Log**
- Empty: first-run copy and button to `Try a sample capture` or `Open capture view`.
- Network or DB errors: toast or inline error with `Retry` option.

**Devices**
- No devices found: message and short troubleshooting hints.
- PTT test failure: inline error plus link to documentation.

**Propagation**
- `OPEN` + a silent canvas: this is the informative case. The panel says the band
  should be carrying signal, which points at the receive chain rather than the
  ionosphere.
- `CLOSED` / `STORM`: silence is the correct answer; the panel must say so plainly so
  the operator stops looking for a fault that is not there.
- `UNKNOWN`: no band condition reported. Render as inconclusive — never as OPEN.
- **Sources unreachable (503): must be visually louder than the empty state.** A blank
  or absent panel reads as "nothing to report", which is the opposite of the truth.
  This is the single error state in this spec where silent degradation is a
  correctness failure rather than a cosmetic one: a healthy receiver has twice been
  diagnosed as broken hardware from exactly this ambiguity. See PRODUCT.md,
  Interaction Requirement 13.
- The panel states whether the path is *supported*, never whether anyone is
  transmitting. Copy must not let `OPEN` imply an expected picture.

### 19.6 Design Tokens

Removed. Colors, typography scale, radii, and spacing steps are part of the visual
world, which PRODUCT.md records as an open decision. The only layout value this spec
still binds is the viewport budget in §20.11, which is an operational constraint (field
laptops at 1280×720) rather than a stylistic one.

### 19.7 Accessibility Criteria

- Capture:
  - Status rail uses `role="status"` or `aria-live="polite"` to announce transitions.
  - Canvas region labelled (e.g., `aria-label="SSTV capture image"`) with textual equivalents in the log.
- Transmit:
  - All controls reachable via tab; visible focus outlines.
  - Progress bar uses `role="progressbar"` with `aria-valuenow`, `aria-valuemin`, `aria-valuemax`.
- Log:
  - Grid/list items use buttons or links with descriptive labels (`"Picture locked · Scottie S1 · 2025-12-03 14:30"`).
- Devices:
  - PTT test button clearly labelled and announces success/failure via `aria-live`.

### 19.8 MVP vs Post-MVP Flags

Mark each element in this section as:

- `MVP` – needed for the initial 12-week desktop release.
- `Post-MVP` – may be stubbed or omitted initially.

Examples:
- Capture view, Transmit view, basic Log (Pictures tab), Devices audio + serial PTT, stereo guidance toggle → MVP.
- QSOs tab, brightness/contrast adjustments, re-decode from audio UI, Field Mode overlay → Post-MVP.

This blueprint, combined with the existing API spec and the SSTeVe UI concept sections, should be sufficient for a coding agent to scaffold and implement the full desktop UI against the Python core.

---

## 20. UX Architecture & Progressive Disclosure Strategy

### 20.1 Four-Expert UX Review Summary (December 2025)

In December 2025, four specialized agents conducted a comprehensive evaluation of the SSTeVe interface design, resulting in critical findings that shape the MVP implementation strategy.

**Participants:**
1. **UX Design Strategist** - Evaluated visual hierarchy, interaction patterns, accessibility
2. **UX Researcher** - Quantified usability issues, predicted testing outcomes, demanded evidence
3. **Brand Messaging Strategist** - Assessed brand alignment, operational vs. aesthetic features
4. **SSTV Domain Expert** - Validated technical constraints, operational requirements, signal variability

**Consensus Findings:**

| Issue | All Experts Agreed | Priority |
|-------|-------------------|----------|
| **Canvas Invisibility** | Canvas must show content during listening phase (not just during decode) | CRITICAL |
| **Waterfall Display** | Must be present and visible (bottom 20-30% or dedicated column) | CRITICAL |
| **Status Display Redundancy** | Dual status rails (horizontal + vertical) create visual noise | HIGH |
| **Control Density** | 27+ visible controls create cognitive overload for novice users | HIGH |
| **Settings Hierarchy** | Palette Mode/Motion settings prioritized over Storage location | MEDIUM |

**Critical Conflicts:**

| Issue | Positions | Resolution |
|-------|-----------|------------|
| **Palette Mode** | UX: "Aesthetic theater" / SSTV: "Operational necessity" / Brand: "Reframe naming" | **KEEP** but rename to "Operating Conditions" (Standard/Night Vision/Sunlight) |
| **Auto-Detection** | Brand: "Design defaults so good users forget" / SSTV: "Auto-detect fails 30-40%" | **HYBRID:** Auto-detect sets defaults, manual overrides accessible |
| **Control Count** | Brand/UX: "8 essential controls" / SSTV: "12-15 minimum for signal variability" | **TEST BOTH:** Option C (see §20.2) |

### 20.2 Option C: Hybrid Approach with User Testing

**Decision:** Implement two UI modes and conduct user testing to validate which approach serves users best.

**Phase 1: Build Both Modes (Weeks 1-2)**

#### Auto Mode (Simplified - 8 Essential Controls)

**Target Situations:** at-the-desk monitoring, receive-only, first-run. *(Was justified by the Makers/Preppers archetypes; retired 2026-08-07. The split itself remains undecided — see the header note and `PRODUCT.md` §Explicitly undecided.)*

**Primary Interface Elements:**
1. Input Device dropdown (with "Auto-detect" option if feasible)
2. Mode Selection buttons (Auto / Scottie S1 / Martin M1 / Robot 36)
3. **Start Capture** button (large, primary action)
4. **Stop / Manual SYNC** button (context-dependent, appears when capture active)
5. **Canvas** (60% of viewport, always visible - shows last image in idle, progressive decode during capture)
6. **Status Indicator** (single horizontal rail: "Listening" / "VIS Detected: Scottie S1" / "Decoding 45%" / "Picture Locked")
7. **Settings** button (opens modal with advanced controls)
8. **Waterfall Display** (bottom 25% of canvas area or integrated into status area)

**Auto-Detection Behavior:**
- Input gain: Auto-detect optimal level from first 2 seconds of audio
- Squelch: Auto-threshold based on noise floor measurement
- AFC: ON by default with ±100 Hz range (suitable for 90% of HF operation)
- **When auto-detect fails:** Status shows actionable message ("Signal too weak - try adjusting gain in Settings") with link to manual controls

**Advanced Controls (Settings Modal):**
- Input Gain slider (0-200%) with "Auto" toggle
- Squelch threshold slider (-60dB to 0dB) with "Auto" toggle
- AFC Range selector (±50 / ±100 / ±200 Hz) with ON/OFF toggle
- Frequency Offset slider (±500 Hz)
- Slant Correction (Auto/Manual with slider)
- Operating Conditions (Standard / Night Vision / Sunlight)

**Success Criteria:**
- 70%+ of novice users complete first decode in <10 minutes
- 85%+ success rate with good signal conditions (SNR > 12dB)
- <5 clicks required to fix auto-detect failure

---

#### Manual Mode (Expert-Friendly - 12-15 Visible Controls)

**Target Situations:** degraded signal, field ops. *(Was justified by the Activators/Old Guard archetypes; retired 2026-08-07. The split itself remains undecided — see the header note and `PRODUCT.md` §Explicitly undecided.)*

**Primary Interface Elements:**
1. Input Device dropdown
2. Mode Selection (Auto / Scottie S1 / Martin M1 / Robot 36 with "Force Mode" indicator)
3. **Input Gain** slider (0-200%) - always visible
4. **Squelch** slider (-60dB to 0dB) with visual threshold indicator - always visible
5. **AFC Toggle** (ON/OFF) with Range selector (±50/±100/±200 Hz) - always visible
6. **Frequency Offset** slider (±500 Hz) with detected frequency display
7. **Slant Correction** toggle (Auto/Manual) with manual slider when enabled
8. **Start / Stop** buttons
9. **Manual SYNC** button (large, accessible with keyboard shortcut: Space)
10. **Canvas** (50-60% of viewport, always visible)
11. **Status Rail** (single horizontal indicator)
12. **Waterfall Display** (bottom 30% of viewport, always visible)
13. **Telemetry Panel** (always visible, collapsible: SNR, RMS, Peak, Frequency)
14. **Settings** button (for less-frequently-used controls)
15. **Thumbnail History Strip** (optional, bottom edge: last 5-10 images for quick review)

**No Auto-Detection:**
- All controls default to safe values (Gain: 100%, Squelch: -40dB, AFC: ON ±100Hz)
- Operator adjusts as needed based on real-time telemetry feedback
- No "smart" behavior that could surprise experienced users

**Collapsible Sections (Optional Enhancement):**
- Telemetry panel can collapse to show only SNR (most critical metric)
- Thumbnail strip can hide if screen space is limited
- **But:** Primary signal processing controls (Gain/Squelch/AFC) never hide

**Success Criteria:**
- Experienced operators complete first decode in <2 minutes
- <2 seconds to adjust any control (no Settings modal required for common adjustments)
- Operators using satellites (ISS SSTV) can switch AFC to ±200Hz and OFF without confusion

---

### 20.3 Auto-Detection Implementation Details & Limitations

**CRITICAL:** Auto-detection serves as intelligent defaults, NOT as replacement for manual control. Based on SSTV Domain Expert review, the following limitations must be documented:

#### Input Gain Auto-Detection

**Algorithm:**
```python
def auto_detect_gain(audio_stream, duration_sec=2.0):
    """
    Analyze first 2 seconds of audio to set optimal gain.
    Target: -12dB RMS for headroom, avoid clipping.
    """
    samples = capture_audio(duration_sec)
    rms = calculate_rms(samples)
    peak = calculate_peak(samples)

    if peak > 0.95:  # Clipping detected
        return current_gain * 0.7  # Reduce 30%
    elif rms < 0.05:  # Too quiet
        return current_gain * 1.5  # Increase 50%
    else:
        return current_gain  # Acceptable
```

**Failure Modes:**
- **QSB (Signal Fading):** If initial 2 seconds capture a fade peak, gain will be set too high → clipping during strong signal moments
  - **Failure Rate:** 30-40% of weak signals (SNR < 10dB)
  - **Mitigation:** Continuous gain monitoring, suggest manual adjustment if clipping detected >5 times in 10 seconds

- **ALC Pumping:** Transmitter automatic level control causes mid-transmission level changes
  - **Failure Rate:** 10-15% of signals from non-commercial transmitters
  - **Mitigation:** Allow manual gain adjustment during active decode (live update)

**User-Facing Behavior:**
- Auto-detect runs on "Start Capture" click
- If gain adjustment needed, brief (<500ms) status message: "Optimizing gain..."
- If clipping detected mid-decode: Toast notification "Signal clipping - reduce gain?" with quick-access slider

---

#### Squelch Auto-Threshold

**Algorithm:**
```python
def auto_threshold_squelch(audio_stream, duration_sec=1.0):
    """
    Measure noise floor during band silence, set threshold 6dB above.
    """
    samples = capture_audio(duration_sec)
    noise_floor_db = calculate_noise_floor(samples)
    return noise_floor_db + 6  # 6dB above noise for margin
```

**Failure Modes:**
- **Contest QRM:** High RF noise, rapid signal changes → threshold too high, squelch closes prematurely
  - **Failure Rate:** 20% of signals in high-QRM environments (contests, Field Day)
  - **Mitigation:** Allow manual squelch adjustment via Settings, persist user preference

- **Urban RF Noise:** Time-variant noise (computers, power lines) → threshold varies throughout session
  - **Failure Rate:** 15% of urban operators
  - **Mitigation:** Re-measure noise floor every 60 seconds when idle

**User-Facing Behavior:**
- Auto-threshold runs on first "Start Capture"
- Threshold stored as session preference (not reset between decodes)
- If decode aborts unexpectedly: Status hint "Signal lost - try lowering squelch in Settings"

---

#### AFC Auto-Ranging

**DANGER:** AFC auto-ranging without user control is dangerous per SSTV Domain Expert.

**Why Auto-Only AFC Fails:**
- **Off-Frequency Tuning:** If operator tunes 150Hz high, AFC locks onto wrong tone (1350Hz instead of 1200Hz sync) → wrong-mode decode, color inversion
- **Satellite Doppler:** ISS SSTV has ±3kHz Doppler shift → AFC chases Doppler instead of sync pulse → continuous sync loss
  - **Failure Rate:** 100% of satellite operation if AFC range too narrow

**Required Implementation:**
- **Auto Mode:** AFC defaults to ON with ±100 Hz range (safe for HF)
  - Display detected sync frequency (e.g., "AFC Locked: 1198 Hz") so operator can validate correct lock
  - If detected frequency is far from expected (>50Hz offset), suggest manual tuning: "Tune your radio 47Hz lower"

- **Manual Mode:** AFC Toggle + Range selector always visible
  - Range options: OFF / ±50 Hz (VHF) / ±100 Hz (HF) / ±200 Hz (weak/drifting)
  - OFF mode for satellite operation (operator manually tunes for Doppler)

**User-Facing Behavior:**
- Auto Mode: AFC always ON, range auto-selected, detected frequency shown
- Manual Mode: Operator selects range based on band/conditions
- AFC lock indicator distinguishes three states — searching, locked, and locked-but-far-
  from-expected — because a confident lock on the wrong tone is the failure mode that
  silently ruins a decode

---

### 20.4 Canvas & Waterfall Requirements

**Based on unanimous expert agreement:**

#### Canvas Specifications

**Size & Position:**
- **Auto Mode:** 60% of viewport height, 70% of viewport width (centered)
- **Manual Mode:** 50-60% of viewport height, 55-65% of viewport width (left-center, with telemetry panel on right)

**Content States:**
1. **Idle (No Capture Active):**
   - Shows last decoded image (if any)
   - If no previous image: Placeholder graphic with "Start Capture to begin" text
   - **NOT a blank/black canvas** - users need visual confirmation of idle state

2. **Listening (Waiting for VIS):**
   - Prior image recedes but stays visible — it must not read as the live signal
   - Waterfall shows live audio spectrum (this is how the operator tunes)
   - Clearly states that SSTeVe is listening

3. **VIS Detected:**
   - Brief, unmissable acknowledgement that a signal was found (~200ms)
   - Mode badge appears: "Scottie S1 Detected"
   - Canvas prepares for scanline rendering

4. **Decoding (Active):**
   - Progressive scanline reveal (top-to-bottom or mode-specific)
   - Each scanline rendered immediately (no buffering delay)
   - Progress indicator: "%X completed" (top-right corner)

5. **Picture Locked (Complete):**
   - Brief completion acknowledgement (~400ms — a 2-second fade is too slow; the
     operator has already been waiting up to two minutes)
   - Status banner: "Picture Locked" with save confirmation
   - Image remains visible (does NOT clear for next capture)

**Critical:** Canvas must NEVER be blank/invisible during listening phase. Operators need continuous visual feedback to verify signal presence and tuning accuracy.

---

#### Waterfall Display Specifications

**Purpose:** Real-time frequency spectrum visualization for tuning assistance

**Position & Size:**
- **Auto Mode:** Integrated into bottom 25% of canvas area (overlay during listening, hidden during decode)
- **Manual Mode:** Dedicated bottom section, always visible, 20-30% of viewport height

**Frequency Range:**
- Horizontal axis: 300 Hz to 3000 Hz (covers SSTV signal range)
- Center line at 1900 Hz (SSTV center frequency per ITU)
- Vertical axis: Time (scrolls upward, 10-30 seconds of history)

**Intensity Mapping (behavior, not specific colors):**
- Four distinguishable levels must be readable at a glance: noise floor, weak signal,
  strong signal, and detected sync pulse (1200 Hz).
- The sync pulse gets a distinct treatment from raw signal strength — an operator uses
  it to confirm they are tuned correctly, so it must not read as "just a strong bin."
- The mapping must survive every Operating Conditions mode (§20.5), including the
  red-shifted night palette, which rules out any scheme that depends on hue alone.

**Interaction:**
- Click on waterfall to set frequency offset (advanced feature, Manual Mode only)
- Hover shows frequency value tooltip
- Vertical reference line at 1900Hz (SSTV center)

**Performance:**
- FFT update rate: 10-20 Hz (balance between smoothness and CPU usage)
- Configurable FFT size: 512 / 1024 / 2048 bins (more bins = finer frequency resolution, higher CPU cost)

---

### 20.5 Operating Conditions Modes (Reframed from "Palette Mode")

**Brand Strategy Conclusion:** Keep feature but reframe from aesthetic preference to operational accommodation.

**Mode Descriptions:**

| Mode | When to Use | Requirement |
|------|-------------|-------------|
| **Standard** | Indoor operation | Default. Must render the decoded image with accurate color — the operator is judging a received photograph, so the surrounding UI must not tint it. |
| **Night Vision** | Night operation (2 AM Field Day, astronomy observers) | Must preserve scotopic (dark) adaptation: suppress short-wavelength emission across the whole interface. A dark theme is **not** sufficient — blue light at any brightness defeats dark adaptation. |
| **Sunlight** | Outdoor field ops (POTA, SOTA) in bright ambient light | Must stay legible in direct sun: raise contrast to WCAG AAA (7:1 minimum) and thicken strokes and separators so structure survives glare. |

The specific palettes that satisfy these three requirements are part of the visual
world and are undecided. The requirements themselves are not negotiable — each names a
physiological or environmental condition, not a preference.

**Location:** Settings → Operating Conditions (4th item after Audio/Storage/PTT)

**Rationale Copy:**
> "SSTeVe adapts to your operating environment. Night Vision mode reduces blue light to preserve dark adaptation during nighttime astronomy work. Sunlight mode increases contrast for outdoor field operations in bright conditions."

**NOT Aesthetic Preferences:**
- ❌ "Cool (Blue-gray slate tones)" - sounds like interior design
- ✅ "Standard / Night Vision / Sunlight" - operational language

---

### 20.6 Phase 2: User Testing Protocol

**Objective:** Validate whether Auto Mode or Manual Mode better serves the user base, or if hybrid approach is necessary.

**Participants (N=20):**
- 10 Novice operators (licensed <1 year, no SSTV experience)
- 10 Experienced operators (licensed >5 years, MMSSTV/QSSTV experience)

**Test Environment:**
- Pre-tuned radio on 14.230 MHz USB with active SSTV transmission (or pre-recorded audio loop)
- Laptop with SSTeVe installed (both Auto and Manual modes available)
- Audio interface (Digirig or SignaLink) configured
- Test conductor present for observation, but does not provide hints

**Task:**
"Decode and save your first SSTV image in under 10 minutes."

**Measured Metrics:**

| Metric | Auto Mode Target | Manual Mode Target |
|--------|------------------|-------------------|
| **Time to First Decode** | <10 min (novice), <2 min (experienced) | <2 min (experienced), <5 min (novice) |
| **Success Rate** | >70% (novice), >85% (experienced) | >95% (experienced), >60% (novice) |
| **Errors / Abandoned Attempts** | <2 per participant | <1 per participant |
| **User Preference (Survey)** | 60% prefer Auto (novice), 20% prefer Auto (experienced) | 40% prefer Manual (novice), 80% prefer Manual (experienced) |
| **SUS Score (System Usability Scale)** | >70 (industry average) | >70 (industry average) |

**Failure Scenarios to Observe:**
- Squelch too high → signal gated, decode never starts
- Gain too low → weak signal, VIS detection fails
- AFC locks onto wrong frequency → wrong-mode decode
- Operator confusion about mode selection (Auto vs Force Mode)
- Operator cannot find manual controls when auto-detect fails

**Acceptance Criteria:**

| Outcome | Decision |
|---------|----------|
| **Auto Mode wins** (70%+ novice success, high SUS, preferred by 60%+ novices) | Ship Auto Mode as default, Manual Mode as "Expert Mode" toggle in Settings |
| **Manual Mode wins** (95%+ experienced success, preferred by 80%+ experienced, novices eventually succeed) | Ship Manual Mode as default, Auto Mode as "Beginner Mode" toggle in Settings |
| **Tie** (both modes have valid use cases, split preference) | Ship both modes, default to Auto for first launch, remember user preference, add quick-switch button in main UI |
| **Both fail** (<50% success for target users) | Return to design phase, implement progressive disclosure (collapsed sections) instead of mode switching |

---

### 20.7 Phase 3: Implementation Decision

**Timeline:** Week 3 after testing completes

**Decision Matrix:**

```
IF auto_mode_novice_success >= 0.70 AND auto_mode_sus >= 70:
    SHIP auto_mode_as_default
    ADD manual_mode_as_expert_toggle

ELIF manual_mode_experienced_success >= 0.95 AND manual_mode_preferred:
    SHIP manual_mode_as_default
    ADD auto_mode_as_beginner_toggle

ELIF (auto_mode_success >= 0.60 AND manual_mode_success >= 0.80):
    SHIP both_modes
    DEFAULT to_auto_for_first_launch
    REMEMBER user_preference
    ADD quick_switch_button (F7 keyboard shortcut)

ELSE:
    REDESIGN with_progressive_disclosure
    IMPLEMENT collapsible_sections (not_mode_switching)
    RETEST in_2_weeks
```

**Quick-Switch Implementation (If Hybrid Wins):**
- Settings toggle: "Interface Mode: Auto / Manual"
- Keyboard shortcut: F7 (toggles between modes)
- Status bar indicator: Small icon showing current mode (🔰 Auto / 🎚️ Manual)
- Mode persists across sessions (stored in local preferences)

---

### 20.8 Updated Timeline (Reflecting Testing Phase)

**Original 12-Week MVP:**
- Weeks 1-8: Core Engine + MVP features
- Weeks 9-12: Polish + Testing + Release

**Revised 14-Week Timeline (Option C):**
- Weeks 1-6: Core Engine Foundation + API Layer + Base UI
- **Weeks 7-8:** Build Auto Mode + Manual Mode UI variants
- **Weeks 9-10:** User Testing (recruit participants, conduct tests, analyze data)
- **Week 11:** Implement validated approach (remove losing mode or integrate both)
- **Weeks 12-13:** Polish + Bug Fixes + Documentation
- **Week 14:** Release Candidate + Launch

**Risk Mitigation:**
- If testing reveals both modes are needed: +1 week for quick-switch integration
- If testing reveals both modes fail: +2 weeks for progressive disclosure redesign
- Budget contingency: 14-16 weeks for MVP (not 12)

---

### 20.9 Success Metrics (Post-Launch)

**To be measured after 6 months of production use:**

| Metric | Target | Data Source |
|--------|--------|-------------|
| **First-Decode Success Rate** | >80% of users decode an image within first 3 launches | Telemetry: Decode success events |
| **Mode Switching Frequency** | <20% of users switch from default mode within first month | Telemetry: Mode toggle events |
| **Advanced Settings Access** | <30% of users open advanced settings in first week | Telemetry: Settings modal opens |
| **Auto-Detect Override Rate** | <40% of sessions require manual gain/squelch adjustment | Telemetry: Manual control changes |
| **User Satisfaction (SUS)** | >75 (above industry average for technical software) | Post-session survey |
| **Support Tickets: UI Confusion** | <10% of total tickets | Support ticket categorization |

**Red Flags (Trigger Redesign):**
- First-decode success rate <60% (users failing to complete core task)
- >50% users switch modes (default mode not serving majority)
- >50% sessions require manual overrides (auto-detect not working)
- SUS score <65 (poor usability)

---

### 20.10 Implementation Notes for Developers

**State Management:**
```typescript
interface UiMode {
  mode: "auto" | "manual";
  autoDetect: {
    gain: boolean;
    squelch: boolean;
    afcRange: boolean;
  };
  manualOverrides: {
    gain?: number;
    squelch?: number;
    afcRange?: number;
  };
}
```

**Component Architecture:**
- `CaptureView.tsx` should accept `mode` prop to render Auto or Manual layout
- Shared components: `Canvas`, `Waterfall`, `StatusRail`
- Mode-specific components: `AutoControls`, `ManualControls`
- Settings modal: Always available, contains advanced options for both modes

**Testing Strategy:**
- Unit tests: Auto-detect algorithms with mock audio data
- Integration tests: Mode switching, preference persistence
- E2E tests: Complete decode flow in both Auto and Manual modes
- Accessibility tests: Keyboard navigation, screen reader compatibility

---

### 20.11 Viewport Constraints & No-Scroll Discipline

**CRITICAL DESIGN CONSTRAINT:** The entire application UI must fit within a 16:9 frame with zero scrolling of the main shell.

#### Target Resolution & Rationale

**Minimum Target:** 1280×720 (720p)
- **Why:** Common field laptop resolution, portable display minimum, ensures usability in resource-constrained environments (POTA, SOTA, emergency comms)
- **Design Resolution:** 1366×768 (most common laptop resolution per StatCounter 2024-2025)
- **Optimal Resolution:** 1920×1080 (1080p - desktop/modern laptop standard)

**No-Scroll Policy:**
- **Main Application Shell:** NEVER scrolls (horizontal or vertical)
- **Progressive Disclosure (Modals, Panels):** CAN scroll if necessary, but design should strive for 0% scrolling even within modals
- **Rationale:**
  - Instrument interfaces don't scroll (oscilloscopes, spectrum analyzers, radio transceivers)
  - Scrolling suggests poor information hierarchy
  - Field operators using gloves/touchpads cannot easily scroll
  - Scrolling hides critical information (what's off-screen might be essential)

#### Viewport Budget Allocation (1280×720)

**Total Available Space:** 1280px (W) × 720px (H)

**Reserved Space:**
- Window chrome (title bar, borders): ~40px vertical
- Top status bar (if any): ~32px vertical
- **Remaining Workspace:** 1280px (W) × 648px (H)

---

#### Auto Mode Viewport Budget (720p)

**Layout:** Single-column centered with sidebar navigation

```
┌──────────────────────────────────────────────────────┐
│ Top Bar (32px): Status, SNR indicator, Settings     │
├──┬───────────────────────────────────────────────────┤
│S │                                                   │
│i │  Canvas (60% height = ~390px)                    │
│d │  + Waterfall overlay (bottom 25% of canvas)      │
│e │                                                   │
│b │                                                   │
│a │───────────────────────────────────────────────────│
│r │  Status Rail (40px): "Listening / Decoding 45%"  │
│  │───────────────────────────────────────────────────│
│6 │  Mode Selection (48px): [Auto][Scottie][Martin]  │
│4 │───────────────────────────────────────────────────│
│p │  Controls Row (56px):                            │
│x │  [Input Device ▾] [Start Capture] [Settings]     │
│  │───────────────────────────────────────────────────│
│  │  Reserve (80px): Telemetry collapse/expand       │
└──┴───────────────────────────────────────────────────┘

Vertical Budget:
- Top Bar: 32px
- Canvas + Waterfall: 390px
- Status Rail: 40px
- Mode Selection: 48px
- Controls Row: 56px
- Reserve: 80px
- Total: 646px (fits within 648px budget ✓)

Horizontal Budget:
- Sidebar: 64px
- Content: 1216px (plenty for canvas + margins)
```

**Auto Mode Compliance:** ✅ Fits in 720p with no scrolling

---

#### Manual Mode Viewport Budget (720p)

**Layout:** Three-column (controls | canvas | telemetry)

```
┌────────────────────────────────────────────────────────────┐
│ Top Bar (32px): Status, SNR, Settings                     │
├────┬──────────────────────────┬──────────────────────┬────┤
│Sid│ Left Controls (180px)    │ Canvas (700px)       │Tele│
│eba│                          │                      │metr│
│r  │ Mode [Auto▾]             │                      │y   │
│64p│ ──────────────────────   │  Canvas ~320px       │148p│
│x  │ Input Device [▾]         │  height              │x   │
│   │ ──────────────────────   │                      │    │
│   │ Input Gain               │                      │SNR │
│   │ [████████░░] 100%        │                      │RMS │
│   │ ──────────────────────   │                      │Peak│
│   │ Squelch                  │                      │Freq│
│   │ [██████████] -40dB       │                      │    │
│   │ ──────────────────────   ├──────────────────────┤    │
│   │ AFC [ON] Range           │ Waterfall (200px)    │    │
│   │ [±50][±100][±200]        │                      │    │
│   │ ──────────────────────   │                      │    │
│   │ Freq Offset              │                      │    │
│   │ [─────●─────] +12Hz      │                      │    │
│   │ ──────────────────────   │                      │    │
│   │ Slant [Auto]             │                      │    │
│   │ ──────────────────────   ├──────────────────────┤    │
│   │ [Start] [Manual SYNC]    │ Status (40px)        │    │
└───┴──────────────────────────┴──────────────────────┴────┘

Horizontal Budget:
- Sidebar: 64px
- Left Controls: 180px
- Canvas: 700px
- Telemetry: 148px
- Margins: 188px
- Total: 1280px (exact fit ✓)

Vertical Budget:
- Top Bar: 32px
- Canvas: 320px
- Waterfall: 200px
- Status: 40px
- Controls padding: 56px
- Total: 648px (fits within budget ✓)
```

**Manual Mode Challenge:** 12-15 controls in 180px width × 616px height is TIGHT.

**Solutions:**
1. **Compact Sliders:** 32px height instead of 48px
2. **Inline Labels:** "Gain: 100%" not separate label + value
3. **Icon Buttons:** Use icons for ±50/±100/±200 AFC buttons
4. **Collapsible Sections:** Group "Advanced" controls (Freq Offset, Slant) under expander
5. **Horizontal Button Groups:** [Start][Stop][Sync] in single row

**Manual Mode Compliance:** ⚠️ Requires compact design, may need collapsible sections

---

#### Waterfall Display Sizing

**Auto Mode:**
- Integrated into canvas area (overlay during listening)
- 25% of canvas height = ~98px at 390px canvas
- Minimum: 80px (sufficient for 10 seconds of FFT history at 10Hz update rate)

**Manual Mode:**
- Dedicated section below canvas
- Fixed height: 200px (30 seconds of history, clear frequency resolution)
- Always visible (no collapse)

**FFT Display Quality:**
- 1024-bin FFT at 720p gives ~1.5 Hz/pixel horizontal resolution (acceptable)
- 2048-bin FFT requires more CPU but gives ~0.75 Hz/pixel (excellent)

---

#### Settings Modal Constraints

**Maximum Modal Size:** 1100px (W) × 580px (H) (allows 90px margins on all sides at 720p)

**Organization for No-Scroll:**

**Option A: Tabbed Layout (Recommended)**
```
┌─────────────────────────────────────────────────────┐
│ Settings                                      [X]   │
├─────────────────────────────────────────────────────┤
│ [Audio] [Operation] [Station] [Operating Cond] [+] │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Audio Tab Content (fits in 520px height):         │
│  ─────────────────────────────────────────────      │
│  Input Device: [USB Audio Interface ▾]             │
│  Output Device: [Built-in Speakers ▾]              │
│                                                     │
│  Input Level: [▓▓▓▓▓▓▓▓░░] 78%                     │
│                                                     │
│  ─────────────────────────────────────────────      │
│  (remaining controls fit without scroll)           │
│                                                     │
├─────────────────────────────────────────────────────┤
│                              [Cancel] [Save]        │
└─────────────────────────────────────────────────────┘
```

**Option B: Accordion Sections (Alternative)**
- Expandable sections: Audio, Operation, Station, Operating Conditions, Advanced
- Only one section expanded at a time (auto-collapse others)
- Each section content: max 400px height

**Rule:** If a tab/section requires >520px, split into sub-tabs or use two-column layout within modal.

**Settings Modal Compliance:** ✅ Fits with tabbed or accordion layout

---

#### Responsive Behavior (>720p)

**At 1366×768 (most common laptop):**
- Canvas grows to 450px height (more comfortable viewing)
- Controls remain same size (don't waste space on larger buttons)
- More breathing room between elements (+8px margins)

**At 1920×1080 (desktop/modern laptop):**
- Canvas grows to 600px height (optimal)
- Waterfall grows to 280px (Manual Mode)
- Telemetry panel can show more metrics (Peak hold graphs, SNR history)
- BUT: Core layout remains fixed (no reflow, no responsive breakpoints)

**Scaling Strategy:** Fixed layout with breathing room at larger sizes, NOT responsive reflow.

---

#### Enforcement Mechanisms

**CSS Constraints:**
```css
/* Main application shell */
.app-shell {
  width: 100vw;
  height: 100vh;
  overflow: hidden; /* NEVER scroll */
  display: grid;
  grid-template-rows: 32px 1fr; /* Top bar + content */
}

/* Content area */
.app-content {
  overflow: hidden; /* NEVER scroll */
  display: flex; /* or grid */
  height: 100%;
}

/* Modals/panels CAN scroll if necessary */
.settings-modal-content {
  max-height: 520px;
  overflow-y: auto; /* Allow scroll as last resort */
}
```

**Development Checklist:**
- [ ] Test every view at 1280×720 (zoom browser to 100%, no scrollbars visible)
- [ ] Use browser dev tools to force viewport to 1280×720, verify no overflow
- [ ] Test with 125% OS scaling (Windows common default) → 1024×576 effective
- [ ] If any component causes overflow, redesign (collapse, paginate, or remove)

---

#### Impact on Previous Specifications

**Canvas Sizing (§20.4) - UPDATED:**
- **Auto Mode:** 60% of available height = ~390px (not "60% of viewport" which is ambiguous)
- **Manual Mode:** ~320px fixed (allows waterfall + controls to fit)

**Manual Mode Controls (§20.2) - UPDATED:**
- 12-15 controls must fit in 180px (W) × 616px (H) = **requires compact design**
- Solution: Collapsible "Advanced" section for Freq Offset + Slant (expandable, not separate modal)

**Waterfall Display (§20.4) - UPDATED:**
- **Auto Mode:** 98px height (not "25% of canvas" which exceeded budget)
- **Manual Mode:** 200px fixed (not "20-30% of viewport")

**Telemetry Panel (Manual Mode) - UPDATED:**
- **Width:** 148px (not flexible)
- **Height:** Full content area (616px)
- **Content:** SNR, RMS, Peak, Frequency (4 values + labels + visual bars)
- **Optional:** Collapsible to show only SNR (saves vertical space if needed)

---

**Summary:** The no-scroll constraint forces disciplined design and ensures SSTeVe works reliably on field laptops, portable displays, and resource-constrained environments. Every pixel is budgeted. Progressive disclosure (modals, expanders) provides depth without breaking the fixed-frame discipline. This constraint aligns with the "instrument panel" design philosophy - professional radio equipment has fixed layouts, not scrolling interfaces.

---

Summary:: Modern, modular SSTV platform with headless Python core and React/Tauri desktop UI, centered on reliable RX/TX, accessibility (stereo sonification), and SSTeVe's friendly & nerdy brand voice. Features validated UX architecture with Auto/Manual modes pending user testing.