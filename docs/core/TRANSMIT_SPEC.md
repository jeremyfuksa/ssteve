# SSTeVe Transmit System Specification

**Version:** 1.0  
**Date:** 2026-01-15  
**Status:** Draft - Ready for Implementation

---

## Philosophy

**Transmit in SSTeVe follows the "messaging app" paradigm:**

- **Smart Reply** for quick CQ responses (80% of use cases)
- **Manual Compose** for custom transmissions (beacons, field day, special events)
- **No template library** - working state instead of saved presets
- **Live preview** - WYSIWYG, confirm before transmit
- **Weak signal guidance** - color warnings based on field research

**Design Mantra Alignment:**
- Calm: Simple zone-based layout, not pixel-perfect positioning
- Passive: Smart defaults, auto-fill where possible
- Confident: Field-tested color recommendations, high-visibility fonts

---

## Architecture Overview

```
┌─ TransmitView ─────────────────────────────────┐
│                                                 │
│  Two Entry Points:                              │
│  ┌────────────────┐  ┌──────────────────────┐ │
│  │ Smart Reply    │  │ Manual Compose       │ │
│  │ (from Gallery) │  │ (new transmission)   │ │
│  └────────────────┘  └──────────────────────┘ │
│                                                 │
│  Shared Components:                             │
│  - Live Preview Canvas                          │
│  - Mode Selection (Robot 36, Martin M1, etc.)  │
│  - Output Device Selection                      │
│  - PTT Configuration                            │
│  - Transmit Button                              │
│                                                 │
└─────────────────────────────────────────────────┘
```

---

## Mode 1: Smart Reply (Default)

### Use Case
Quick response to received SSTV image (CQ answer, satellite reply, contest exchange)

### Trigger
User clicks **"Reply"** button in GalleryView image detail panel

### Auto-Fill Logic

**Smart Reply does NOT use OCR** - SSTV image quality is too degraded for reliable callsign recognition.

**Instead, Smart Reply:**
1. **Manual callsign entry** (required field, keyboard focused)
2. **Recent contacts dropdown** (backend remembers last 20 stations contacted)
3. **Auto-calculate RST** from decode quality score
4. **Pre-fill user's callsign** from settings

**Backend provides:**
```json
{
  "recent_contacts": ["K1ABC", "W2XYZ", "VE3DEF"],  // Last 20 unique callsigns
  "rst_calculated": "599",                            // From decode quality_score
  "my_callsign": "KF0NUI",                           // From user settings
  "frequency": "14.230",                              // From session metadata (if available)
  "timestamp": "2026-01-15T14:30:00Z"
}
```

**User workflow:**
1. User clicks "Reply" on received image
2. Callsign field is **empty but focused** (ready for typing)
3. Dropdown shows recent contacts for quick selection
4. User types or selects callsign
5. RST and message pre-filled with smart defaults

### UI Layout

```
┌─ Reply to K1ABC ─────────────────────────────────────┐
│                                                       │
│  To Station                                           │
│  ┌────────────────────────────────────────────────┐  │
│  │ Callsign:  [__________ ▼]  (Recent: K1ABC, W2XYZ) │  │
│  │ Signal:    [599                              ] │  │
│  │ Message:   [73!                              ] │  │
│  └────────────────────────────────────────────────┘  │
│                                                       │
│  Layout                                               │
│  ┌────────────────────────────────────────────────┐  │
│  │ Background: [Solid Color ▼]  [Dark Blue #1A2B3C] │
│  │ Text Color: [White      ▼]                     │  │
│  │ Layout:     [Standard   ▼]                     │  │
│  │             Callsign (top), RST + Message (mid),│  │
│  │             Your callsign (bottom)              │  │
│  └────────────────────────────────────────────────┘  │
│                                                       │
│  Preview                                              │
│  ┌────────────────────────────────────────────────┐  │
│  │ ╔══════════════════════════════════════════╗   │  │
│  │ ║                                          ║   │  │
│  │ ║   K1ABC                                  ║   │  │
│  │ ║                                          ║   │  │
│  │ ║   599  73!                               ║   │  │
│  │ ║                                          ║   │  │
│  │ ║                                          ║   │  │
│  │ ║                            KF0NUI        ║   │  │
│  │ ║                                          ║   │  │
│  │ ╚══════════════════════════════════════════╝   │  │
│  └────────────────────────────────────────────────┘  │
│                                                       │
│  Mode & Device                                        │
│  ┌────────────────────────────────────────────────┐  │
│  │ Mode:   [Robot 36  ▼]  ⏱ ~36 seconds          │  │
│  │ Output: [USB Audio ▼]  PTT: [Serial RTS ▼]    │  │
│  └────────────────────────────────────────────────┘  │
│                                                       │
│  [ Cancel ]                          [ Transmit ]     │
└───────────────────────────────────────────────────────┘
```

### Layout Options (Smart Reply)

| Layout | Description | Text Placement |
|--------|-------------|----------------|
| **Standard** | Callsign top, RST+Message middle, Your callsign bottom | Header: Their call (large, center)<br>Body: RST + Message (normal, left)<br>Footer: Your call (normal, right) |
| **Minimal** | Compact single-line | Body: "K1ABC 599 73! de KF0NUI" (center) |
| **Contest** | Contest-style exchange | Header: Their call (large, center)<br>Body: Serial number or zone (large, center)<br>Footer: Your call (normal, center) |

**Default:** Standard layout

### Background Options (Smart Reply)

- **Solid Color:** Single color (default: dark blue #1A2B3C)
- **Gradient:** Two-color gradient (vertical or horizontal)
- **Image:** Upload custom background (remembers last used)

### Workflow

1. User clicks "Reply" in GalleryView
2. TransmitView opens with Smart Reply mode
3. Form auto-fills: Callsign, RST, Message ("73!")
4. User edits message if desired (or accepts default)
5. Preview updates live
6. User clicks "Transmit"
7. Confirmation modal: "Transmit to K1ABC on Robot 36?"
8. Transmission begins

**Average time:** 10-20 seconds

---

## Mode 2: Manual Compose

### Use Case
Custom transmission not tied to received image:
- Calling CQ
- Field day beacon
- Special event station ID
- Contest CQ
- Satellite QSO initiation

### Trigger
User clicks **"New Transmission"** in TransmitView

### UI Layout

```
┌─ New Transmission ─────────────────────────────────────────────┐
│                                                                 │
│  ╔═══════════════════════════════╦═══════════════════════════╗ │
│  ║ Compose                       ║ Preview                   ║ │
│  ╠═══════════════════════════════╣                           ║ │
│  ║ Background                    ║  ┌─────────────────────┐  ║ │
│  ║ ┌──────────────────────────┐  ║  │ ╔═════════════════╗ │  ║ │
│  ║ │ Type: [Solid Color  ▼]   │  ║  │ ║ KF0NUI          ║ │  ║ │
│  ║ │                           │  ║  │ ║                 ║ │  ║ │
│  ║ │ [Dark Blue] [Change...]  │  ║  │ ║ Field Day 2026  ║ │  ║ │
│  ║ │                           │  ║  │ ║ 4A Maryland     ║ │  ║ │
│  ║ └──────────────────────────┘  ║  │ ║                 ║ │  ║ │
│  ║                               ║  │ ║                 ║ │  ║ │
│  ║ Text Zones                    ║  │ ║      14.230 MHz ║ │  ║ │
│  ║ ┌──────────────────────────┐  ║  │ ╚═════════════════╝ │  ║ │
│  ║ │ ▼ Header (Top)           │  ║  └─────────────────────┘  ║ │
│  ║ │                           │  ║                           ║ │
│  ║ │ Text:                     │  ║  Weak Signal Preview:     ║ │
│  ║ │ [KF0NUI                 ] │  ║  S9: ████████ Clear       ║ │
│  ║ │                           │  ║  S5: ████░░░░ Readable    ║ │
│  ║ │ Font: [Eurostile ▼]       │  ║  S3: ██░░░░░░ Marginal    ║ │
│  ║ │ Size: [Large    ▼]        │  ║                           ║ │
│  ║ │ Color: [White   ▼]        │  ║                           ║ │
│  ║ │ Align: [Center  ▼]        │  ║                           ║ │
│  ║ │ [ ] Bold                  │  ║                           ║ │
│  ║ └──────────────────────────┘  ║                           ║ │
│  ║                               ║                           ║ │
│  ║ ┌──────────────────────────┐  ║                           ║ │
│  ║ │ ▼ Body (Middle)          │  ║                           ║ │
│  ║ │                           │  ║                           ║ │
│  ║ │ Text: (multi-line)        │  ║                           ║ │
│  ║ │ [Field Day 2026         ] │  ║                           ║ │
│  ║ │ [4A Maryland            ] │  ║                           ║ │
│  ║ │ [                       ] │  ║                           ║ │
│  ║ │                           │  ║                           ║ │
│  ║ │ Font: [Eurostile ▼]       │  ║                           ║ │
│  ║ │ Size: [Normal   ▼]        │  ║                           ║ │
│  ║ │ Color: [White   ▼]        │  ║                           ║ │
│  ║ │ Align: [Left    ▼]        │  ║                           ║ │
│  ║ │ [ ] Bold                  │  ║                           ║ │
│  ║ └──────────────────────────┘  ║                           ║ │
│  ║                               ║                           ║ │
│  ║ ┌──────────────────────────┐  ║                           ║ │
│  ║ │ ▼ Footer (Bottom)        │  ║                           ║ │
│  ║ │                           │  ║                           ║ │
│  ║ │ Text:                     │  ║                           ║ │
│  ║ │ [14.230 MHz             ] │  ║                           ║ │
│  ║ │                           │  ║                           ║ │
│  ║ │ Font: [Eurostile ▼]       │  ║                           ║ │
│  ║ │ Size: [Normal   ▼]        │  ║                           ║ │
│  ║ │ Color: [Yellow  ▼]        │  ║                           ║ │
│  ║ │ Align: [Right   ▼]        │  ║                           ║ │
│  ║ │ [ ] Bold                  │  ║                           ║ │
│  ║ └──────────────────────────┘  ║                           ║ │
│  ║                               ║                           ║ │
│  ╚═══════════════════════════════╩═══════════════════════════╝ │
│                                                                 │
│  Mode & Device                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Mode:   [Robot 36  ▼]  ⏱ ~36 seconds                    │  │
│  │ Output: [USB Audio ▼]  PTT: [Serial RTS ▼]              │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  [ Reset ]  [ Save as Default ]            [ Transmit ]        │
└─────────────────────────────────────────────────────────────────┘
```

### Zone System

**3 Zones with automatic positioning:**

| Zone | Vertical Position | Default Content |
|------|-------------------|-----------------|
| **Header** | Top 20% of image | Station callsign, title |
| **Body** | Middle 60% of image | Main message, multi-line text |
| **Footer** | Bottom 20% of image | Frequency, grid square, timestamp |

**Each zone independently configurable:**
- Text content (multi-line supported)
- Font family
- Font size
- Text color
- Alignment (Left, Center, Right)
- Bold toggle

**Zones can be empty** (e.g., Header-only transmission is valid)

### Alignment Options

**Each zone has 3 alignment options:**

| Alignment | Behavior | Visual Example |
|-----------|----------|----------------|
| **Left** | Text flush to left margin | `KF0NUI         ` |
| **Center** | Text centered horizontally | `    KF0NUI     ` |
| **Right** | Text flush to right margin | `         KF0NUI` |

**Safe Area (NTSC-style):**

SSTV transmissions suffer from edge degradation due to:
- Sync pulse timing variations
- Slant correction artifacts
- Clipping at receiver
- Display overscan on some radios

**Safe area margins:**
- **Action Safe:** 5% margin (edges may be visible but distorted)
- **Title Safe:** 10% margin (guaranteed readable text area)

**Implementation:**
- All text zones use **Title Safe** boundaries (10% margin)
- Background images/gradients extend to full frame (0% margin)
- User-visible safe area guide in preview (toggleable grid overlay)

**Pixel calculations (Robot 36: 320×240):**
- Title Safe: 32px margin on all sides → 256×176 usable text area
- Action Safe: 16px margin → 288×208 visible area

**Visual Reference:**
```
┌─────────────────────────────────────┐ ← Full frame (320×240)
│ ┌─────────────────────────────────┐ │ ← Action Safe (16px margin)
│ │ ┌───────────────────────────┐   │ │ ← Title Safe (32px margin)
│ │ │                           │   │ │    ALL TEXT HERE
│ │ │   SAFE TEXT ZONE          │   │ │
│ │ │   (256×176 pixels)        │   │ │
│ │ │                           │   │ │
│ │ └───────────────────────────┘   │ │
│ └─────────────────────────────────┘ │
└─────────────────────────────────────┘
    ← Backgrounds/gradients fill entire frame
```

**Preview Grid Overlay (toggleable):**
- **Off (default):** Clean preview, no guides
- **On:** Shows dashed lines for Action Safe and Title Safe boundaries
- **Toggle:** Keyboard shortcut `G` or button in preview toolbar

### Font Selection

**High-Visibility Font Library:**

| Font | Description | Use Case | Sample |
|------|-------------|----------|--------|
| **Eurostile Bold** | Geometric sans-serif, excellent SSTV readability | Callsigns, headers | `KF0NUI` |
| **DIN Bold** | Industrial sans-serif, high contrast | Signal reports, technical data | `599 73!` |
| **Perfect DOS VGA 437** | Pixel font, nostalgic, crisp at low res | Retro aesthetic, grid squares | `FN31pr` |
| **Inter Bold** | Modern humanist sans, web-safe fallback | General purpose text | `Field Day 2026` |

**All fonts selected for:**
- High contrast at weak signal levels
- Crisp rendering at SSTV resolutions (320×256, 320×240)
- Wide character spacing (reduces blur at S3 levels)
- Available under SIL Open Font License (Google Fonts - redistributable)
- **Full Unicode support** (Latin, Cyrillic, CJK, Greek)

**Font loading:**
- Downloaded from Google Fonts API during build
- Bundled with app (no web fonts, works offline)
- Full Unicode character set (no subsetting) to support international operators
- Fallback chain: Selected font → Inter → System sans-serif

**Unicode Coverage:**
| Script | Support Level | Use Case |
|--------|---------------|----------|
| Latin Extended | Full | Western Europe, Americas |
| Cyrillic | Full | Eastern Europe, Russia (R3, UA, etc.) |
| Greek | Full | Greece (SV), Cyprus (5B) |
| Japanese (Hiragana, Katakana) | Full | Japan (JA, 7K, etc.) |
| CJK Ideographs | Partial (common chars) | China (BY, B), Korea (HL, D9), Japan |
| Arabic | Full | Middle East, North Africa |

### Font Size

**3 pre-calibrated sizes:**

| Size | Point Size (at 320px width) | Use Case | Character Width |
|------|----------------------------|----------|-----------------|
| **Large** | 36pt | Callsigns, station ID | ~10-12 chars per line |
| **Normal** | 24pt | Messages, signal reports | ~15-18 chars per line |
| **Small** | 18pt | Frequency, grid square | ~20-25 chars per line |

**Auto line-wrapping** enabled for all sizes (word boundaries, no hyphenation)

### Background Options

#### Option 1: Solid Color

**UI:**
```
Type: [Solid Color ▼]
Color: [████ Dark Blue] [Change...]
```

**Color Picker:**
- Standard HSL color picker
- Quick presets:
  - Dark Blue (#1A2B3C)
  - Black (#000000)
  - White (#FFFFFF)
  - Dark Green (#1A3B2C)
  - Dark Red (#3B1A1C)

**Remembers last selected color**

---

#### Option 2: Gradient

**UI:**
```
Type: [Gradient ▼]
Start: [████ Dark Blue ] [Change...]
End:   [████ Light Blue] [Change...]
Direction: [Vertical ▼]
           (options: Vertical, Horizontal, Diagonal)
```

**Gradient Rendering:**
- Linear gradient only (no radial)
- Smooth interpolation in RGB color space
- Direction options: Top→Bottom, Left→Right, TopLeft→BottomRight

**Remembers last gradient setup**

---

#### Option 3: Image Upload

**UI:**
```
Type: [Image ▼]
File: [background.jpg            ] [Browse...]
Fit:  [Cover ▼] (options: Cover, Contain, Stretch)
```

**Supported Formats:**
- JPEG, PNG, BMP
- Max resolution: 1920×1080 (downscaled to SSTV mode resolution)
- Auto-scales to selected SSTV mode (Robot 36: 320×256, Martin M1: 320×256, etc.)

**Fit Options:**
| Option | Behavior |
|--------|----------|
| **Cover** | Image fills frame, crops to aspect ratio (default) |
| **Contain** | Image fits within frame, letterbox if needed |
| **Stretch** | Image stretched to exact frame size (may distort) |

**Remembers last uploaded image path**

---

### Text Color Selection

**Color Picker with Weak Signal Guidance:**

```
┌─ Text Color ──────────────────────────────────┐
│                                                │
│  Quick Presets:                                │
│  [White] [Yellow] [Cyan] [Black] [Custom...]  │
│                                                │
│  Weak Signal Visibility:                       │
│  ┌──────────────────────────────────────────┐ │
│  │ Signal Level    Your Color (White)       │ │
│  │ ─────────────────────────────────────────│ │
│  │ S9 (Strong):    ████████ Clear           │ │
│  │ S5 (Medium):    ████████ Clear           │ │
│  │ S3 (Weak):      ███████░ Good            │ │
│  │                                           │ │
│  │ ✓ High contrast - readable at all levels │ │
│  └──────────────────────────────────────────┘ │
│                                                │
│  ⚠️  Warning: Red/Orange degrades first       │
│      at weak signals. Use for accents only,   │
│      not critical text like callsigns.        │
│                                                │
│  [ Cancel ]                       [ Select ]   │
└────────────────────────────────────────────────┘
```

**Color Recommendations (Based on Field Research):**

| Color | Contrast Rating | S3 Readability | Recommended For |
|-------|----------------|----------------|-----------------|
| **White** | Excellent | ✓✓✓ | Callsigns, critical info |
| **Yellow** | Excellent | ✓✓✓ | Callsigns, highlights |
| **Cyan** | Very Good | ✓✓ | Technical data |
| **Black** | Excellent (on light bg) | ✓✓✓ | Light backgrounds only |
| **Light Gray** | Good | ✓ | Secondary info |
| **Red** | Poor | ✗ | Avoid for text |
| **Orange** | Poor | ✗ | Avoid for text |

**System automatically calculates:**
- Luminance contrast ratio vs background
- Simulated weak signal degradation (S3 preview)
- Warning if contrast < 4.5:1 (WCAG AA minimum)

---

### Working State Persistence

**Manual Compose remembers:**
- Last used background (type + color/gradient/image)
- All 3 zones: text content, font, size, color, alignment, bold
- Mode selection (Robot 36, Martin M1, etc.)
- Output device + PTT method

**Saved to:**
- Local storage (browser)
- Backend preference: `GET /config/transmit/working-state`

**User controls:**
- **"Reset" button:** Clears working state, returns to blank template
- **"Save as Default" button:** Saves current state as default for new transmissions

**This enables "rapid fire" workflow:**
1. User sets up Field Day template once
2. Updates only the recipient callsign for each contact
3. Transmits immediately (no reconfiguration)

---

## Shared Components

### Live Preview Canvas

**Always visible in both modes**

**Rendering:**
- Real-time preview as user types/changes settings
- Exact pixel-accurate representation of transmission
- Shows actual font rendering, colors, positioning
- Updates at 100ms debounce (not per-keystroke)

**Preview Modes:**

| Mode | Purpose |
|------|---------|
| **Full Quality** | Default - shows exact transmission |
| **Weak Signal (S3)** | Simulates image at weak signal level (noise, reduced contrast) |
| **Grid Overlay** | Shows zone boundaries (Header/Body/Footer) |

**User can toggle between preview modes** with dropdown above canvas

---

### Mode Selection

**Dropdown of supported SSTV modes:**

| Mode | Resolution | Duration | Common Use |
|------|-----------|----------|------------|
| **Robot 36** | 320×240 | 36 sec | Satellites, fast QSOs |
| **Martin M1** | 320×256 | 114 sec | HF ragchewing |
| **Scottie S1** | 320×256 | 110 sec | HF ragchewing |
| *Future: PD 120* | 640×496 | 126 sec | High-res DX |

**Shows estimated duration** next to mode name

**Mode changes:**
- Update canvas aspect ratio in preview
- Recalculate zone pixel boundaries
- Re-render text at new resolution

---

### Output Device Selection

**Dropdown of available audio output devices:**
```
Output Device: [USB Audio Codec ▼]
               [Built-in Speaker  ]
               [HDMI Audio        ]
```

**Populated from:** `GET /devices/audio`

**Shows:**
- Device name
- Channel count (mono/stereo)
- Sample rate

**Remembers last selected device** across sessions

---

### PTT Configuration

**Inline dropdown (not separate modal for quick workflows):**

```
PTT: [Serial RTS ▼]
     [Serial RTS    ] ← Current selection
     [Serial DTR    ]
     [Hamlib CAT    ]
     [VOX           ]
     [None          ]
     [Configure...  ] ← Opens PTT settings modal
```

**Quick selection** for users who've already configured PTT in Devices view

**"Configure..." option** opens full PTT setup modal:
- Serial port selection
- Hamlib radio model picker
- VOX preamble duration
- Pre/post TX delay

---

### Transmit Button

**Behavior:**
1. User clicks "Transmit"
2. Validation:
   - Preview has content (not blank)
   - Output device selected
   - PTT configured (if not "None")
3. Confirmation modal appears (unless disabled in settings)
4. Transmission begins

**Confirmation Modal:**
```
┌─ Confirm Transmission ─────────────────────┐
│                                             │
│  Transmit on Robot 36                       │
│  Device: USB Audio Codec                    │
│  Duration: ~36 seconds                      │
│  PTT: Serial RTS (COM3)                     │
│                                             │
│  [ ] Don't ask again (this session)         │
│                                             │
│  [ Cancel ]                  [ Transmit ]   │
└─────────────────────────────────────────────┘
```

**During Transmission:**
```
┌─ Transmitting ─────────────────────────────┐
│                                             │
│  Robot 36 (36 seconds)                      │
│                                             │
│  Progress: ██████████░░░░░░░░░░ 47%        │
│            Scanline 120 of 256              │
│                                             │
│  [ Abort ]                                  │
└─────────────────────────────────────────────┘
```

**Keyboard shortcut:** 
- Ctrl/Cmd+Enter to transmit (skips confirmation)
- Escape to cancel

---

## Backend API Requirements

### New Endpoints

#### `POST /transmit/preview`

**Purpose:** Generate preview image for live canvas rendering

**Request:**
```json
{
  "mode": "robot_36",
  "background": {
    "type": "solid_color",  // or "gradient" or "image"
    "color": "#1A2B3C",
    "gradient": {
      "start": "#1A2B3C",
      "end": "#3B5C7D",
      "direction": "vertical"
    },
    "image_path": "/path/to/background.jpg",
    "fit": "cover"
  },
  "zones": [
    {
      "zone": "header",
      "text": "KF0NUI",
      "font": "rajdhani_bold",
      "size": "large",
      "color": "#FFFFFF",
      "alignment": "center",
      "bold": true
    },
    {
      "zone": "body",
      "text": "Field Day 2026\n4A Maryland",
      "font": "rajdhani_bold",
      "size": "normal",
      "color": "#FFFFFF",
      "alignment": "left",
      "bold": false
    },
    {
      "zone": "footer",
      "text": "14.230 MHz",
      "font": "rajdhani_bold",
      "size": "normal",
      "color": "#F2B451",
      "alignment": "right",
      "bold": false
    }
  ]
}
```

**Response:**
```json
{
  "preview_url": "/api/v1/preview/temp_abc123.png",
  "weak_signal_preview_url": "/api/v1/preview/temp_abc123_s3.png",
  "contrast_analysis": {
    "header": {
      "contrast_ratio": 12.5,
      "wcag_aa": true,
      "s3_readable": true
    },
    "body": {
      "contrast_ratio": 11.2,
      "wcag_aa": true,
      "s3_readable": true
    },
    "footer": {
      "contrast_ratio": 8.3,
      "wcag_aa": true,
      "s3_readable": true
    }
  }
}
```

---

#### `POST /transmit/smart-reply`

**Purpose:** Provide Smart Reply defaults (NO OCR, manual callsign entry)

**Request:**
```json
{
  "source_image_id": "abc123"  // ID from gallery (for context only)
}
```

**Response:**
```json
{
  "recent_contacts": [
    {"callsign": "K1ABC", "last_contact": "2026-01-15T14:25:00Z"},
    {"callsign": "W2XYZ", "last_contact": "2026-01-15T13:10:00Z"},
    {"callsign": "VE3DEF", "last_contact": "2026-01-14T19:45:00Z"}
  ],
  "rst_calculated": "599",
  "rst_source": "decode_quality",     // or "manual" if user entered
  "my_callsign": "KF0NUI",
  "default_message": "73!",
  "frequency": "14.230",              // If available from session
  "timestamp": "2026-01-15T14:30:00Z"
}
```

**User must manually type or select callsign** (no OCR auto-fill)

---

#### `GET /config/transmit/working-state`

**Purpose:** Retrieve user's last Manual Compose setup

**Response:**
```json
{
  "background": {
    "type": "solid_color",
    "color": "#1A2B3C"
  },
  "zones": {
    "header": {
      "text": "KF0NUI",
      "font": "rajdhani_bold",
      "size": "large",
      "color": "#FFFFFF",
      "alignment": "center",
      "bold": true
    },
    "body": {
      "text": "Field Day 2026\\n4A Maryland",
      "font": "rajdhani_bold",
      "size": "normal",
      "color": "#FFFFFF",
      "alignment": "left",
      "bold": false
    },
    "footer": {
      "text": "14.230 MHz",
      "font": "rajdhani_bold",
      "size": "normal",
      "color": "#F2B451",
      "alignment": "right",
      "bold": false
    }
  },
  "mode": "robot_36",
  "output_device_id": "usb_audio_codec",
  "ptt_config": {
    "method": "serial_rts",
    "port": "COM3"
  }
}
```

---

#### `POST /config/transmit/working-state`

**Purpose:** Save user's current Manual Compose setup

**Request:** Same structure as GET response above

**Response:**
```json
{
  "saved": true,
  "timestamp": "2026-01-15T14:35:00Z"
}
```

---

#### `POST /transmit/start`

**Purpose:** Begin SSTV transmission (modified from existing endpoint)

**Request:**
```json
{
  "mode": "robot_36",
  "composition": {
    "background": { /* ... */ },
    "zones": [ /* ... */ ]
  },
  "output_device_id": "usb_audio_codec",
  "ptt_config": {
    "method": "serial_rts",
    "port": "COM3",
    "pre_delay_ms": 500,
    "post_delay_ms": 200
  }
}
```

**Response:**
```json
{
  "session_id": "tx_abc123",
  "estimated_duration_sec": 36,
  "websocket_url": "/api/v1/ws/transmit/tx_abc123"
}
```

**WebSocket Events:**
```json
// PTT keyed
{"event": "ptt_keyed", "timestamp": "2026-01-15T14:35:00Z"}

// Scanline progress
{"event": "scanline_transmitted", "line": 120, "total": 256, "progress": 0.47}

// Transmission complete
{"event": "transmit_complete", "duration_sec": 36.2}

// Error
{"event": "error", "code": "PTT_FAILED", "message": "Serial port not responding"}
```

---

## Frontend Components

### New React Components

#### `TransmitView.tsx` (Modified)
- Main container for transmit UI
- Routing between Smart Reply and Manual Compose

#### `SmartReplyPanel.tsx` (New)
- Auto-fill form
- Layout selection dropdown
- Background/color pickers
- Live preview integration

#### `ManualComposePanel.tsx` (New)
- Zone-based text editor
- Font/size/color controls per zone
- Background configuration
- Working state management

#### `LivePreviewCanvas.tsx` (New)
- WebGL or Canvas2D renderer
- Real-time text rendering
- Preview mode toggle (Full/S3/Grid)
- Contrast analysis overlay

#### `TextZoneEditor.tsx` (New)
- Reusable component for Header/Body/Footer zones
- Collapsible sections
- Font picker dropdown
- Color picker with weak signal preview

#### `BackgroundSelector.tsx` (New)
- Type selector (Solid/Gradient/Image)
- Color pickers
- Image upload/browse
- Fit options for images

#### `ColorPickerWithGuidance.tsx` (New)
- HSL color picker
- Quick presets
- Weak signal simulation
- Contrast warning system

#### `TransmitProgressModal.tsx` (Modified)
- Progress bar
- Scanline counter
- Abort button
- PTT status indicator

---

## Text Rendering Engine (Backend)

### Python Implementation

**New Module:** `sstv_core/src/sstv_core/encoder/text_renderer.py`

**Key Functions:**

```python
from PIL import Image, ImageDraw, ImageFont
from typing import Dict, List, Tuple

class TextRenderer:
    """Renders text zones onto SSTV images with weak signal optimization."""
    
    FONTS = {
        'rajdhani_bold': '/fonts/Rajdhani-Bold.ttf',
        'roboto_condensed_bold': '/fonts/RobotoCondensed-Bold.ttf',
        'vt323': '/fonts/VT323-Regular.ttf',
        'inter_bold': '/fonts/Inter-Bold.ttf'
    }
    
    SIZES = {
        'large': 36,
        'normal': 24,
        'small': 18
    }
    
    def __init__(self, mode: str):
        """Initialize renderer for specific SSTV mode."""
        self.width, self.height = self._get_resolution(mode)
        
        # NTSC-style safe areas
        self.action_safe_margin = int(self.width * 0.05)  # 5% - edges visible but may distort
        self.title_safe_margin = int(self.width * 0.10)   # 10% - guaranteed readable
        self.margin = self.title_safe_margin  # Text uses title safe by default
        
    def render_composition(
        self,
        background: Dict,
        zones: List[Dict]
    ) -> Image:
        """
        Render complete SSTV image with background + text zones.
        
        Args:
            background: {type, color, gradient, image_path, fit}
            zones: [{zone, text, font, size, color, alignment, bold}, ...]
        
        Returns:
            PIL Image ready for SSTV encoding
        """
        # Create background
        img = self._create_background(background)
        draw = ImageDraw.Draw(img)
        
        # Render each zone
        for zone_config in zones:
            if not zone_config['text'].strip():
                continue  # Skip empty zones
                
            self._render_zone(draw, zone_config)
        
        return img
    
    def _create_background(self, bg_config: Dict) -> Image:
        """Create background layer (solid/gradient/image)."""
        if bg_config['type'] == 'solid_color':
            return Image.new('RGB', (self.width, self.height), bg_config['color'])
        
        elif bg_config['type'] == 'gradient':
            return self._create_gradient(
                bg_config['gradient']['start'],
                bg_config['gradient']['end'],
                bg_config['gradient']['direction']
            )
        
        elif bg_config['type'] == 'image':
            return self._load_and_fit_image(
                bg_config['image_path'],
                bg_config['fit']
            )
    
    def _render_zone(self, draw: ImageDraw, zone_config: Dict):
        """Render text in specific zone (header/body/footer)."""
        zone_bounds = self._get_zone_bounds(zone_config['zone'])
        
        # Load font with Unicode support
        font_path = self.FONTS[zone_config['font']]
        font_size = self.SIZES[zone_config['size']]
        
        try:
            font = ImageFont.truetype(font_path, font_size)
        except OSError:
            # Fallback to Inter if selected font unavailable
            font = ImageFont.truetype(self.FONTS['inter_bold'], font_size)
        
        # Apply bold via stroke if enabled
        stroke_width = 2 if zone_config.get('bold', False) else 0
        
        # Calculate text position based on alignment
        text = zone_config['text']
        
        # Normalize Unicode text (NFC normalization for consistent rendering)
        import unicodedata
        text = unicodedata.normalize('NFC', text)
        
        # Detect RTL languages (Arabic, Hebrew)
        rtl_languages = ['\u0600-\u06FF', '\u0590-\u05FF']  # Arabic, Hebrew ranges
        is_rtl = any(any(ord(char) in range(int(r.split('-')[0], 16), int(r.split('-')[1], 16)) 
                        for r in rtl_languages) for char in text)
        
        lines = text.split('\n')
        
        y_offset = zone_bounds['top']
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            
            # Horizontal alignment
            if zone_config['alignment'] == 'left':
                x = zone_bounds['left']
            elif zone_config['alignment'] == 'center':
                x = zone_bounds['left'] + (zone_bounds['width'] - text_width) // 2
            elif zone_config['alignment'] == 'right':
                x = zone_bounds['right'] - text_width
            
            # Draw with optional stroke (bold effect) and RTL support
            draw.text(
                (x, y_offset),
                line,
                font=font,
                fill=zone_config['color'],
                stroke_width=stroke_width,
                stroke_fill=zone_config['color'],
                direction='rtl' if is_rtl else 'ltr'  # Right-to-left for Arabic/Hebrew
            )
            
            y_offset += bbox[3] - bbox[1] + 4  # Line height + spacing
    
    def _get_zone_bounds(self, zone: str) -> Dict:
        """Calculate pixel boundaries for header/body/footer zones."""
        zones = {
            'header': {
                'top': self.margin,
                'bottom': int(self.height * 0.20),
                'left': self.margin,
                'right': self.width - self.margin
            },
            'body': {
                'top': int(self.height * 0.20),
                'bottom': int(self.height * 0.80),
                'left': self.margin,
                'right': self.width - self.margin
            },
            'footer': {
                'top': int(self.height * 0.80),
                'bottom': self.height - self.margin,
                'left': self.margin,
                'right': self.width - self.margin
            }
        }
        
        bounds = zones[zone]
        bounds['width'] = bounds['right'] - bounds['left']
        bounds['height'] = bounds['bottom'] - bounds['top']
        return bounds
    
    def simulate_weak_signal(self, img: Image, snr_db: float = -10) -> Image:
        """
        Simulate image degradation at weak signal levels.
        
        Args:
            img: Source image
            snr_db: Signal-to-noise ratio in dB (lower = noisier)
        
        Returns:
            Degraded image (for S3 preview)
        """
        import numpy as np
        
        # Convert to numpy array
        arr = np.array(img).astype(np.float32)
        
        # Calculate noise level from SNR
        signal_power = np.mean(arr ** 2)
        noise_power = signal_power / (10 ** (snr_db / 10))
        
        # Add Gaussian noise
        noise = np.random.normal(0, np.sqrt(noise_power), arr.shape)
        noisy_arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
        
        # Reduce contrast (simulates sync slips)
        noisy_arr = (noisy_arr * 0.7 + 128 * 0.3).astype(np.uint8)
        
        return Image.fromarray(noisy_arr)
    
    def analyze_contrast(self, img: Image, zones: List[Dict]) -> Dict:
        """
        Calculate contrast ratios for each text zone.
        
        Returns:
            {zone: {contrast_ratio, wcag_aa, s3_readable}}
        """
        analysis = {}
        
        for zone_config in zones:
            zone_name = zone_config['zone']
            text_color = self._hex_to_rgb(zone_config['color'])
            bg_color = self._sample_zone_background(img, zone_name)
            
            contrast = self._calculate_contrast_ratio(text_color, bg_color)
            
            analysis[zone_name] = {
                'contrast_ratio': round(contrast, 2),
                'wcag_aa': contrast >= 4.5,
                's3_readable': contrast >= 7.0  # Higher threshold for weak signals
            }
        
        return analysis
```

---

## Database Schema Updates

### `images` Table (Modified)

Add new field for transmitted images:

```sql
ALTER TABLE images ADD COLUMN composition_json TEXT;
-- Stores full composition (zones, background) for retransmission
```

**Example:**
```json
{
  "background": {
    "type": "solid_color",
    "color": "#1A2B3C"
  },
  "zones": [
    {
      "zone": "header",
      "text": "KF0NUI",
      "font": "rajdhani_bold",
      "size": "large",
      "color": "#FFFFFF",
      "alignment": "center",
      "bold": true
    }
  ]
}
```

**Purpose:** Allows user to re-edit/re-transmit past images

---

### `user_preferences` Table (New)

```sql
CREATE TABLE user_preferences (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, key)
);
```

**Stores:**
- `transmit.working_state` - Last Manual Compose setup
- `transmit.default_template` - User's saved default
- `transmit.confirmation_disabled` - Skip confirmation modal preference

---

### `recent_contacts` Table (New)

```sql
CREATE TABLE recent_contacts (
    id INTEGER PRIMARY KEY,
    callsign TEXT NOT NULL,
    last_contact_utc TEXT NOT NULL,
    frequency TEXT,
    mode TEXT,
    rst_sent TEXT,
    rst_received TEXT,
    UNIQUE(callsign)
);

CREATE INDEX idx_recent_contacts_last_contact 
    ON recent_contacts(last_contact_utc DESC);
```

**Purpose:** Powers Smart Reply callsign dropdown

**Behavior:**
- Auto-populated when user transmits (callsign extracted from composition)
- Limited to 20 most recent unique callsigns
- Ordered by last_contact_utc descending (most recent first)
- UNIQUE constraint prevents duplicates, updates timestamp on retransmit

**Query for Smart Reply dropdown:**
```sql
SELECT callsign, last_contact_utc, frequency, mode
FROM recent_contacts
ORDER BY last_contact_utc DESC
LIMIT 20;
```

---

## Implementation Phases

### Phase 1: Smart Reply Foundation (Week 1-2)
- [ ] Backend: `POST /transmit/smart-reply` endpoint
- [ ] Backend: Text renderer with solid color backgrounds
- [ ] Frontend: SmartReplyPanel component
- [ ] Frontend: Basic live preview (no weak signal simulation)
- [ ] Database: Add composition_json field

**Milestone:** User can reply to received image with auto-filled template

---

### Phase 2: Manual Compose Core (Week 3-4)
- [ ] Backend: Zone-based text rendering
- [ ] Backend: Font loading system (4 fonts)
- [ ] Backend: Gradient background support
- [ ] Frontend: ManualComposePanel with 3 zones
- [ ] Frontend: Font/size/color pickers
- [ ] Frontend: Working state persistence

**Milestone:** User can create custom transmissions with zone-based layout

---

### Phase 3: Advanced Backgrounds (Week 5)
- [ ] Backend: Image upload + fit options (cover/contain/stretch)
- [ ] Frontend: BackgroundSelector component
- [ ] Frontend: Image upload UI with drag-drop

**Milestone:** User can use custom background images

---

### Phase 4: Weak Signal Features (Week 6)
- [ ] Backend: Contrast analysis API
- [ ] Backend: Weak signal simulation (S3 preview)
- [ ] Frontend: ColorPickerWithGuidance component
- [ ] Frontend: Preview mode toggle (Full/S3/Grid)

**Milestone:** User sees weak signal warnings before transmit

---

### Phase 5: Polish & Testing (Week 7)
- [ ] Frontend: Keyboard shortcuts (Ctrl+Enter to transmit)
- [ ] Frontend: "Save as Default" button
- [ ] Frontend: Confirmation modal with "Don't ask again"
- [ ] Testing: E2E tests for both Smart Reply and Manual Compose
- [ ] Documentation: User guide for templating system

**Milestone:** Production-ready transmit system

---

## Success Metrics

**Smart Reply Adoption:**
- Target: >60% of transmissions use Smart Reply (not Manual Compose)
- Measured: Count of Smart Reply vs Manual Compose API calls

**Time to Transmit:**
- Target: <20 seconds from "Reply" click to transmission start
- Measured: User timing analytics

**Working State Usage:**
- Target: >40% of users use "Save as Default" feature
- Measured: Preference saves per user

**Weak Signal Warnings:**
- Target: <5% of users ignore red/orange warnings and transmit anyway
- Measured: Color selection vs warning display

**Template Complexity:**
- Target: Average 2.3 zones used per transmission (not all 3)
- Measured: Zone usage statistics

---

## User Testing Scenarios

### Scenario 1: CQ Response
1. User receives image from K1ABC
2. Clicks "Reply" in Gallery
3. Changes message to "QSL via bureau"
4. Clicks Transmit
5. **Success:** Transmission completes in <30 seconds

### Scenario 2: Field Day Beacon
1. User clicks "New Transmission"
2. Sets Header: "W1ABC/3"
3. Sets Body: "Field Day 2026\n4A Maryland"
4. Sets Footer: "14.230 MHz"
5. Clicks "Save as Default"
6. **Success:** Can rapidly transmit similar images by changing header only

### Scenario 3: Weak Signal Warning
1. User picks red text for callsign
2. System shows S3 preview with illegible text
3. User changes to white text
4. S3 preview shows readable callsign
5. **Success:** User understands color impact before transmitting

---

## Open Questions

1. **Grid overlay toggle:** Should grid overlay (showing zone boundaries) be permanent, or only visible during editing?
   - **Pro permanent:** Helps users understand zone system
   - **Con permanent:** Clutters preview canvas

3. **Font expansion:** Should we add more fonts in future versions, or keep the library minimal (4 fonts)?
   - Research shows users rarely change fonts once they find one they like

4. **Multi-language support:** Should text rendering support Unicode (Cyrillic, Japanese, etc.)?
   - Amateur radio is global, but SSTV bandwidth limits may make non-ASCII impractical

---

## Appendix: Font Licenses

**All fonts included under permissive licenses:**

| Font | License | Source |
|------|---------|--------|
| Eurostile Bold | Commercial (Adobe) | Bundled, licensed |
| DIN Bold | SIL OFL 1.1 | Google Fonts |
| Perfect DOS VGA 437 | CC0 Public Domain | https://dafont.com |
| Inter Bold | SIL OFL 1.1 | Google Fonts |

**Font files bundled in:** `sstv_core/assets/fonts/`

**Build-time font download script:**
```bash
# scripts/download_google_fonts.sh
# Downloads TTF files from Google Fonts API during build
curl -o fonts/Rajdhani-Bold.ttf "https://fonts.google.com/download?family=Rajdhani"
curl -o fonts/RobotoCondensed-Bold.ttf "https://fonts.google.com/download?family=Roboto+Condensed"
curl -o fonts/VT323-Regular.ttf "https://fonts.google.com/download?family=VT323"
curl -o fonts/Inter-Bold.ttf "https://fonts.google.com/download?family=Inter"
```

---

## Key Design Decisions Summary

**Based on user feedback and field research:**

1. ✅ **NO OCR for Smart Reply** - SSTV image quality too degraded for reliable callsign recognition
   - Users manually type or select from recent contacts dropdown (last 20 unique callsigns)
   
2. ✅ **NTSC-style Safe Areas** - Prevents text clipping at image edges
   - Title Safe: 10% margin (guaranteed readable, all text here)
   - Action Safe: 5% margin (visible but may distort)
   - Backgrounds fill entire frame (no safe area restriction)
   
3. ✅ **Google Fonts Only** - All fonts from Google Fonts (SIL OFL 1.1 license)
   - Rajdhani Bold, Roboto Condensed Bold, VT323 (pixel font), Inter Bold
   - Downloaded at build time, bundled for offline use
   
4. ✅ **Full Unicode Support** - Global amateur radio community
   - Latin, Cyrillic, Greek, CJK (Chinese/Japanese/Korean), Arabic
   - Right-to-left (RTL) text rendering for Arabic/Hebrew operators
   - NFC normalization for consistent rendering

5. ✅ **4 Fonts for v1.0** - Minimal set, evaluate usage before expanding
   - Research shows users rarely change fonts once they find one they like

---

**This specification is ready for implementation. Backend and frontend teams can work in parallel on Phase 1 starting immediately.**
