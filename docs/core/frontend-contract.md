---
title: SSTeVe Frontend Contract — behavior the engine and UI agree on
created: 2026-08-21
derived-from: frontend-spec.md (retired 2026-08-21)
status: Current. Sections here are cited by shipped source code.
---

# SSTeVe Frontend Contract

What the UI and the core engine agree on: which endpoint each control calls,
which WebSocket events drive which state transitions, how failures must
surface, what the waterfall must show, and where auto-detection is documented
to fail.

**This file is behavior, not layout.** It says what the interface must *do*.
For how the window is arranged, see
`../superpowers/specs/2026-08-21-single-window-activity-log-design.md`. For
durable product truth, see `../../PRODUCT.md`, which is authoritative wherever
it conflicts with this document.

> **Provenance.** This document is the durable half of `frontend-spec.md`,
> which was retired on 2026-08-21. That file had accumulated three layers of
> superseded design: a palette/typography system stripped 2026-08-05, user
> archetypes retired 2026-08-07, and a four-route/Auto-Manual layout model
> abandoned 2026-08-21.
>
> What was extracted here is the half derived from shipped code rather than
> from any design path. Section numbers are preserved from the original
> because source modules cite them: `dsp/spectrum.py`, `api/models.py`,
> `decode/rx_manager.py`, and `api/thumbnails.py` all reference §20.4 or
> §20.11 by number.

---

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

---

### 7.3 Decode Experience

The decode workflow, as a legible progression (PRODUCT.md requirement 6):
- Primary action: `Listen` (F5) on the main view.
- Status rail across the top of the canvas:
  - `Listening → VIS Detected → Sync Lock → Decoding → Decode Complete`
- Canvas behavior:
  - Show scanline sweep as lines are decoded.
  - On lock, subtly slow the sweep and show lock confidence (0–100%).
  - On completion, the image eases into its final position over ~600–800ms (no theatrical fade).
- Audio (optional): short, analog-flavored confirmation tone on decode complete.

---

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

---

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

---

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

---

### 19.8 MVP vs Post-MVP

- **MVP:** receive, transmit, basic log (pictures), audio devices + serial PTT,
  stereo guidance toggle.
- **Post-MVP:** QSO tab, brightness/contrast adjustment, re-decode from audio,
  field-mode simplifications.

> The component inventory this list originally accompanied (§19.2) described a
> four-route shell and was retired 2026-08-21 with that model. The MVP/Post-MVP
> split survives because it is a scope decision, not a layout one; it is cited
> by `tests/api/test_config_completeness.py`.

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

The canvas is sized to the *picture*, not to a share of the viewport. SSTV frames
are small and fixed. The three implemented modes are 320×256 (Scottie S1, Martin M1)
and 320×240 (Robot 36) — verified in `decode/scottie_decoder.py:39`,
`decode/martin_decoder.py:36`, and `decode/robot_decoder.py:37`. PD modes are larger
(commonly cited as 640×496) but have no decoder here, so treat that figure as
unverified until one exists. Either way the frames are small and fixed, so a canvas
expressed as a percentage of viewport height either crops the image or surrounds it
with dead space at every size but one.

Rule: the canvas occupies the smallest area that shows the current mode's frame at
a whole-number scale, plus its status affordances. It grows in integer steps (1×,
2×, 3×) as the window allows, and never claims space it is not using to display
pixels. Whatever it does not need belongs to the log.

> Replaced the previous viewport-percentage rule on 2026-08-21. That rule gave the
> canvas the largest region in the layout and then under-filled it: a 320×256 frame
> labeled "2×" needs 640×512, which does not fit in a 340px-tall canvas.

**Position:** left-center, with the transmit home and/or telemetry to its right.

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

### 20.5 Operating Conditions Modes

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


**Rationale Copy:**
> "SSTeVe adapts to your operating environment. Night Vision mode reduces blue light to preserve dark adaptation during nighttime astronomy work. Sunlight mode increases contrast for outdoor field operations in bright conditions."

**NOT Aesthetic Preferences:**
- ❌ "Cool (Blue-gray slate tones)" - sounds like interior design
- ✅ "Standard / Night Vision / Sunlight" - operational language

---

### 20.11 Viewport Constraint

**Minimum target: 1280×720.** The field-laptop floor, and 1024×576 effective
at Windows' common 125% scaling. This is the size the window must shrink to
without breaking — not the size the interface is designed for.

**No-scroll policy.** The main application shell never scrolls, horizontally
or vertically. Progressive disclosure (modals, expanded panels) may scroll
when necessary.

Rationale: instrument interfaces do not scroll; scrolling hides information
that may be critical, and it is hostile to gloves and touchpads in field
operation.

**Larger viewports gain breathing room, not a different layout.** See the
single-window design doc for how that resolves — a fixed-cost activity
instrument with an elastic log region absorbing the remainder.

> The two layout budgets this section previously carried (Auto Mode and Manual
> Mode, each a distinct arrangement of columns) were retired 2026-08-21 with
> the Auto/Manual split itself. The 1280×720 floor and the no-scroll rule are
> operational constraints and survive; the layouts were design-path residue.

---

## Open: control density

PRODUCT.md records the Auto mode (8 controls) versus Manual mode (12–15
controls) split as **explicitly undecided**. No evidence exists for either;
the 20-participant user test that was to settle it was never run. Any
justification by user archetype no longer stands — the archetypes were retired
2026-08-07.

The §20.3 failure rates below are the strongest evidence in this document that
manual overrides must remain reachable regardless of which density wins.
