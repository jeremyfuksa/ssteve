# GEMINI Project Analysis: SSTeVe SSTV Platform

## Project Overview

This project, **SSTeVe**, is a modern, cross-platform Slow-Scan Television (SSTV) application. It is designed with a modular architecture that separates the core signal processing logic from the user interface.

The architecture consists of two main parts:

1.  **Python Core Engine (`to_reuse/python_core/sstv-engine`):** A headless Python service that handles all the digital signal processing (DSP), SSTV encoding/decoding, audio device management, and radio PTT (Push-to-Talk) control. It exposes its functionality through a REST and WebSocket API built with FastAPI.

2.  **Desktop UI (`ssteve-ui--figma/` and `to_reuse/desktop_app_shell`):** A lightweight desktop application built with React and Tauri. The UI, named "SSTeVe", provides a friendly, approachable interface for users to interact with the core engine. It communicates with the Python backend via the exposed APIs.

The project aims to serve a wide range of ham radio operators, from hobbyists to serious practitioners, with a focus on reliability, accessibility, and a high-quality user experience.

### Key Technologies

- **Backend (Core Engine):** Python, FastAPI, WebSockets, NumPy, SciPy, Pillow, SQLAlchemy, PySerial
- **Frontend (Desktop UI):** React, TypeScript, Tauri, Vite, Tailwind CSS
- **Testing:** Pytest (Python), Playwright (E2E), JS/TS-based test runners (`npm test`)

## Building and Running

The project is a monorepo with multiple components. Here are the key commands for building and running the different parts, inferred from the project files.

### Python Core Engine

The Python engine is a standard Python package.

```bash
# Navigate to the python core directory
cd to_reuse/python_core

# Install dependencies
pip install -r requirements.txt

# Run the tests
pytest

# Run the standalone CLI (entry points are defined in setup.py)
# Note: This might require installing the package locally first (`pip install .`)
sstv-decode --help
sstv-encode --help
```

### Desktop Application (Tauri + React)

The desktop application is the primary way to use the SSTeVe platform. The Tauri application manages the Python backend as a subprocess.

```bash
# Navigate to the desktop app shell directory
cd to_reuse/desktop_app_shell

# Install frontend dependencies
npm install

# Run the application in development mode
# This will start the Vite dev server and the Tauri application
npm run dev

# Build the application for production
npm run build

# Run the final bundled application
npm run tauri
```

### End-to-End & Integration Testing

The project includes a comprehensive testing strategy.

```bash
# Run integration tests (likely from the root or a dedicated test runner package)
# This command is mentioned in the testing README
npm test

# Run e2e tests for the desktop app
cd to_reuse/desktop_app_shell
npm run test:e2e
```

## Development Conventions

- **Modular Architecture:** Logic is strictly separated between the Python core and the UI layer. Communication happens exclusively through the defined API.
- **API-First:** The `docs/app-spec.md` defines a clear API contract between the frontend and backend, including REST endpoints and WebSocket events for real-time updates.
- **Configuration as Code:** The application specification is documented in detail in `docs/app-spec.md`, serving as a blueprint for development.
- **Comprehensive Testing:** The project uses a multi-layered testing approach, including unit tests for the Python core (`pytest`), integration tests for the API, and end-to-end tests for the UI (`playwright`). Test assets are well-organized in `to_reuse/testing_assets`.
- **Accessibility:** The application has a strong focus on accessibility, with features like stereo sonification for blind operators and a verbose CLI mode. The design spec mandates WCAG 2.1 AA compliance.
- **Cross-Platform Support:** The use of Python and Tauri is explicitly chosen to support Windows, macOS, and Linux from a single codebase. Build scripts and configurations reflect this goal.
- **State Management:** The React frontend uses Zustand for lightweight state management.
- **UI Components:** The UI is built using `shadcn/ui` and `lucide-react` icons, based on Tailwind CSS.
