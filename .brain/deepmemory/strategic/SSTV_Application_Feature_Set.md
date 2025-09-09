# SSTV Application: Feature Set

This document outlines the feature set for a new, modern Slow-Scan
Television (SSTV) application.

### **1. Design & Philosophy**

#### **Guiding Philosophy: The \"Digital Rack Unit\"**

The core metaphor for the application is a single, premium piece of
digital rack equipment from the 1980s/90s. The entire user experience
should feel like interacting with a physical device.

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

#### **Aesthetic & Layout: The Faceplate**

- **Chassis:** The application window is a fixed-size \"chassis\" with a
  photorealistic brushed aluminum texture. Primary themes will be
  **Black** and **Silver**.

- **Layout:** The layout is static and non-resizable, reinforcing the
  physical object metaphor. It is segmented into two primary zones:

  - **Left Zone (approx. 65%): The Main Display (VFD Simulation)**

  - **Right Zone (approx. 35%): The Control Surface**

- **Typography:** Labels will be \"silkscreened\" onto the faceplate
  using a clean, technical sans-serif font like **Manrope** or **Space
  Grotesk**.

#### **Interaction Model: Function Modes**

- **Centralized Control:** The workflow is based on switching the
  operational mode of the entire \"device.\" Pressing a button in the
  Function Bank reconfigures both the Main Display and the Control
  Surface for the selected task. For example, pressing \[GALLERY\]
  changes the main display to an image browser and replaces the standard
  controls with navigation buttons.

### **2. Launch Feature Set (MVP)**

*This defines the \"barebones essential\" features for the initial
release.*

#### **Core Experience & Platform**

- **Receive-First Focus:** The initial launch will be focused
  exclusively on providing a best-in-class receiving and decoding
  experience.

- **Automatic Workflow:** By default, the app is always \"listening\"
  and will automatically start decoding a detected SSTV signal.

- **Cross-Platform Support:** The application will be available for
  **Windows, macOS, and Linux**.

- **Supported SSTV Modes:** The app will support the most popular modes
  covering \>90% of use cases: **Scottie S1 & S2, Martin M1, PD120, and
  PD180**.

#### **Main User Interface Components**

- **Main Display (VFD Simulation):** The primary display area, styled as
  a Vacuum Fluorescent Display.

  - **Aesthetic:** Dark background with bright, glowing elements in a
    dot-matrix or segmented style. The default color will be classic
    **VFD Cyan**, with **Amber** and **Phosphor Green** as theme
    options.

  - **Idle State:** When not decoding, the display functions as a large,
    real-time **VFD Spectrum Analyzer**.

  - **Decoding State:** When a signal is detected, the analyzer fades
    out, and the incoming image is rendered line-by-line in the same
    display area.

- **Rotary Selector Knob:** The primary SSTV mode selector, styled as a
  graphical rotary knob that \"snaps\" to positions labeled on the
  faceplate. Default position is \"AUTO\".

- **Persistent Status Bar:** A dedicated bar provides clear feedback on
  the application\'s current state (e.g., LISTENING, DECODING: SCOTTIE
  S1\...).

#### **File & Setup Handling**

- **Recorded Audio Decoding:** Users can decode from pre-recorded **WAV
  files**. The app will automatically handle various sample rates and
  bit depths.

- **Setup Function:** A \[SETUP\] button in the function bank will open
  a dedicated view on the main display for all configuration.

  - **Essential Settings:** Audio Input/Output Device Selection (must
    support virtual audio cables), Theme Selection (Chassis/VFD Color).

  - **About Section:** Contains application credits for **KF0NUI** and a
    list of any open-source libraries used.

### **3. Post-Launch Roadmap**

#### **Phase 1: Foundational Transmit & Control**

*Goal: Implement a robust, flexible framework for transmission and radio
control based on the \"TNC and SDR Integration Analysis\" research
document.*

- **Transmit Functionality:** A dedicated \[TRANSMIT\] mode will be
  added to the function button bank.

  - **Essential Feature:** A dedicated **Transmit Audio Level** control,
    styled as an equalizer slider.

- **Hamlib Integration:** Integrate the Hamlib library as the core
  engine for all CAT rig control and CAT-based PTT.

- **Decoupled Configuration UI:** The Setup view will be expanded to
  allow independent selection of devices for Rig Control, PTT, Audio In,
  and Audio Out.

- **Core PTT Methods:** The PTT subsystem will be implemented with
  initial support for **CAT (via Hamlib)** and **Serial Port
  (RTS/DTR)**.

#### **Phase 2: Expanded Hardware & UI Features**

*Goal: Broaden hardware support and add core user-facing features.*

- **SDR Integration:** Direct, seamless integration with popular SDR
  software like SDRUno.

- **Expanded PTT Support:** Add support for **C-Media GPIO** and
  software-driven **VOX**.

- **Image Gallery:** A dedicated \[GALLERY\] mode that reconfigures the
  main display into an image browser with list/grid views and management
  options.

- **Manual Adjustments Panel:** A section on the faceplate labeled
  \"IMAGE CALIBRATION,\" hidden by a **graphical flip-down plastic
  door**. Clicking it reveals equalizer-style sliders for fine-tuning
  image Skew and Offset.

- **Image Overlay System:** An intuitive \[EDITOR\] mode for composing
  images with text and shapes, featuring drag-and-drop data fields.

#### **Phase 3: Specialized Protocol Support**

*Goal: Add support for hardware that requires entirely different
communication protocols.*

- **KISS TNC Engine:** Implement a separate software engine to
  communicate with hardware TNCs (e.g., Mobilinkd, TinyTrak4) using the
  KISS protocol.

### **4. Long-Term Vision (\"Crazy Ideas\")**

*This section captures ambitious, long-term goals to be considered well
after the application has matured.*

- **Advanced Signal Processing Engine:** A ground-up rebuild of the
  codec for a high-sensitivity receiver, guided by the \"Technical
  Analysis of Spectrogram\...\" research document.

- **Public SDR Integration:** Connect to remote, public SDRs over a
  network by implementing native client support for protocols like
  **KiwiSDR** and **Spyserver**.

- **Integrated Channel Tuning:** Automatically tune a connected SDR to
  standard SSTV calling frequencies.

- **Automatic Log Enhancement:** Automatically add frequency and band
  data to the log when using an SDR.

- **Mobile Companion App:** A receive-only version for iOS and Android
  that connects to WebSDR and KiwiSDR servers.
