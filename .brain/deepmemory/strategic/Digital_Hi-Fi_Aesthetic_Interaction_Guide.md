### SSTV Application: Digital Hi-Fi Aesthetic & Interaction Guide

This document outlines the refined user interface and experience (UI/UX)
direction for the SSTV application. It builds upon the initial feature
set by establishing a strong aesthetic metaphor inspired by high-end
stereo component systems of the 1980s and 1990s.

### 1. Guiding Philosophy: The \"Digital Rack Unit\"

The core metaphor for the application is a single, premium piece of
digital rack equipment. The entire user experience should feel like
interacting with a physical device from brands like Pioneer, Sony, or
Technics.

- **Physicality & Tactility:** Interactions should feel tangible.
  Buttons click, knobs turn, and displays glow with purpose. The
  interface is a cohesive faceplate, not a collection of software
  windows.

- **Information Clarity:** Like the best hi-fi gear, the UI should
  present complex information in a clear, legible, and visually pleasing
  way. Function is paramount, but style gives it character.

- **Unified Design:** The application is a single, self-contained unit.
  All functions and displays are integrated into its \"chassis,\"
  avoiding floating windows or disconnected panels that break the
  physical illusion.

### 2. Layout & Chassis: The Faceplate

The application will utilize a single, fixed-size window that serves as
the chassis for the entire device.

- **Chassis:** The window background will feature a subtle,
  photorealistic texture of brushed aluminum. The primary theme options
  will be **Black** and **Silver**.

- **Fixed Layout:** The layout is static and non-resizable, reinforcing
  the physical object metaphor. It is segmented into two primary zones:

  - **Left Zone (approx. 65%): The Main Display.** This area is
    dedicated to the primary visual output (VFD, image decoding).

  - **Right Zone (approx. 35%): The Control Surface.** This area houses
    all interactive controls, grouped by function.

- **Typography:** Labels for controls and sections will be printed
  directly onto the faceplate using a clean, technical sans-serif font
  like **Manrope** or **Space Grotesk** to emulate silkscreened text on
  metal.

### 3. The Main Display: VFD Simulation

The primary display moves beyond a simple image preview to become a
multi-mode Vacuum Fluorescent Display (VFD), the iconic glowing screen
of 80s/90s electronics.

- **Aesthetic:** The display will have a dark background with bright,
  glowing elements. Graphics will use a segmented or dot-matrix style.
  The default color will be a classic **VFD Cyan**, with **Amber** and
  **Phosphor Green** as theme options.

- **Idle State:** When not decoding, the display becomes a large,
  real-time **VFD Spectrum Analyzer**, providing a beautiful and
  functional visualization of the input audio. Key status info (e.g.,
  LISTENING\..., MODE: AUTO) is overlaid in a large, segmented font.

- **Decoding State:** When a signal is detected, the VFD analyzer fades
  out, and the incoming image is rendered line-by-line in the same
  display area.

- **Function States:** When modes like GALLERY or EDITOR are active, the
  display reconfigures to show the relevant interface (e.g., a grid of
  thumbnails, an image with overlay tools).

### 4. Controls & Components: A Tactile Interface

Standard OS UI elements will be replaced by custom components that
emulate their physical hardware counterparts.

- **Function Button Bank:** The primary mode buttons (RECEIVE, TRANSMIT,
  GALLERY, SETUP) will be styled as chunky, physical buttons.

  - **State:** The active mode\'s button will appear **pressed in**.

  - **Feedback:** Each button will feature a small, circular **LED
    indicator graphic** that illuminates when its mode is active.

- **Rotary Selector Knob:** The SSTV mode dropdown will be replaced with
  a graphical rotary knob. Modes are printed on the faceplate around the
  knob, which \"snaps\" to each position.

- **Equalizer Sliders:** All sliders (e.g., Transmit Audio Level, Skew,
  Offset) will be styled to mimic the physical sliders on a graphic
  equalizer, complete with guide markings on the faceplate.

- **Manual Adjustments Panel:** The \"hatch\" for Skew and Offset will
  be a section on the faceplate labeled IMAGE CALIBRATION. This section
  will be hidden by a **graphical flip-down plastic door**. The user
  must click the door to open it, revealing the sliders within,
  enhancing the sense of physical interaction.

### 5. Interaction Model: Function Modes

The workflow is based on switching the operational mode of the entire
\"device,\" not managing separate windows or views.

- **Centralized Control:** Pressing a button in the Function Bank
  reconfigures both the **Main Display** and the **Control Surface** for
  the selected task.

- **Example (Gallery Mode):**

  1.  User presses the \[GALLERY\] button.

  2.  The button\'s LED indicator lights up.

  3.  The Main Display switches from the VFD analyzer to a browser for
      saved images.

  4.  The controls on the right side are replaced by a minimal set of
      new buttons, such as NEXT, PREV, and DELETE.

This model maintains focus, reduces cognitive load, and preserves the
cohesive, single-device experience.
