# SSTV Application - Detailed Execution Plan

This document provides a granular, actionable development plan for the
SSTV application, designed for parallel execution by frontend and
backend teams. Each task includes dependencies, acceptance criteria, and
references to guide implementation.

### **Phase 0: Core Architecture & API Contract**

*Goal: Establish the non-negotiable communication contract between the
frontend and backend. This phase must be completed before parallel
development can begin.*

- **Task 0.1: \[JOINT\] Define and Document the Frontend-Backend API**

  - **Description:** Define the precise data structures and command
    formats for all communication.

  - **Dependencies:** None.

  - **References:** TNC and SDR Integration Analysis (for Backend Data
    Flow).

  - **Definition of Done:**

    - A shared specification document (e.g., OpenAPI, Markdown) is
      created.

    - The JSON structure for VisualizationData {fft_bins, vu_level} is
      finalized.

    - The JSON structure for DecodedLine {line_number, pixel_data} is
      finalized.

    - The command format for SetAudioDevice(id) and the structure for
      the AudioDeviceList are finalized.

    - The mechanism for streaming raw audio from frontend to backend is
      agreed upon (e.g., WebSocket binary frames).

### **MVP Launch: Receive-Only**

*Goal: A polished, receive-only application with a strong aesthetic and
core decoding functionality.*

#### **Frontend Workstream (Tauri/Svelte)**

- **Task FE-1.1: Implement Main App Chassis & Theming**

  - **Description:** Create the main application window and core layout
    structure.

  - **Dependencies:** None.

  - **References:** Digital Hi-Fi Aesthetic & Interaction Guide

  - **Definition of Done:**

    - Tauri window is configured to be fixed-size and frameless.

    - The 65%/35% two-column layout is implemented and responsive.

    - The Black and Silver brushed aluminum themes are selectable and
      functional.

    - The selected UI Font (IBM Plex Sans default) is applied globally.

- **Task FE-1.2: Implement Setup & About View**

  - **Description:** Build the user interface for all application
    settings.

  - **Dependencies:** BE-1.2 (for device list), FE-1.1

  - **References:** Digital Hi-Fi Aesthetic & Interaction Guide

  - **Definition of Done:**

    - The \[SETTINGS\] function button is implemented.

    - The UI panel for Audio Input/Output Device Selection is built and
      populates its dropdown from the backend API.

    - Selecting a device correctly calls the SetAudioDevice(id) backend
      command.

    - The static \"About\" panel is implemented and displays the
      required credits.

- **Task FE-1.3: Implement Display & Visualization Components**

  - **Description:** Build the core VFD display and its associated
    visualizations.

  - **Dependencies:** BE-1.3 (for data stream), FE-1.1

  - **References:** SSTV Spectrogram and Waterfall Analysis, Digital
    Hi-Fi Aesthetic & Interaction Guide

  - **Definition of Done:**

    - The VFD-styled Spectrum Analyzer correctly renders the
      VisualizationData stream from the backend.

    - The integrated VU meter updates based on the same data stream.

    - The component correctly renders DecodedLine data, building the
      image line-by-line on the canvas.

    - The display correctly switches between the \"Idle\" (analyzer) and
      \"Decoding\" (image) states.

- **Task FE-1.4: Implement Core UI Controls**

  - **Description:** Build the remaining interactive elements for the
    main screen.

  - **Dependencies:** FE-1.1

  - **References:** Digital Hi-Fi Aesthetic & Interaction Guide

  - **Definition of Done:**

    - The Rotary Selector Knob for mode selection is implemented and
      functional.

    - The Persistent Status Bar is implemented and correctly displays
      status messages received from the backend.

    - The optional manual control buttons (Start/Stop/Save) are
      implemented and hidden by default.

#### **Backend Workstream (Python)**

- **Task BE-1.1: Build Core Audio Pipeline**

  - **Description:** Create the system for ingesting and processing all
    audio.

  - **Dependencies:** Task 0.1

  - **References:** SSTV Spectrogram and Waterfall Analysis

  - **Definition of Done:**

    - The backend can receive a raw audio stream from the frontend.

    - An integrated resampling library correctly converts common sample
      rates (44.1k, 48k) to the internal processing rate (e.g.,
      11.025k).

    - The pipeline can seamlessly switch between live audio and audio
      from a WAV file.

- **Task BE-1.2: Implement Device Enumeration & Selection**

  - **Description:** Create the service to discover and manage audio
    hardware.

  - **Dependencies:** None.

  - **References:** TNC and SDR Integration Analysis (for cross-platform
    enumeration methods).

  - **Definition of Done:**

    - An API endpoint is created that returns a list of all available
      audio input/output devices on the host OS.

    - A command endpoint is created to receive SetAudioDevice(id) from
      the frontend and switch the active audio stream.

- **Task BE-1.3: Implement Visualization & SSTV Decoding Engine**

  - **Description:** The core DSP engine for decoding and analysis.

  - **Dependencies:** Task 0.1, BE-1.1

  - **References:** SSTV Spectrogram and Waterfall Analysis

  - **Definition of Done:**

    - The engine continuously performs FFT and VU analysis on the input
      audio and streams VisualizationData to the frontend.

    - The engine correctly decodes all launch modes (Scottie S1/S2,
      Martin M1, PD120, PD180) from a clean signal.

    - The automatic workflow is functional: the backend detects a VIS
      code, automatically begins sending DecodedLine data, and sends a
      \"complete\" status message upon finishing.
