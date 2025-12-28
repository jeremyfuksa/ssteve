# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**SSTeVe** is a modern SSTV (Slow-Scan Television) application for amateur radio operators. The project uses a modular architecture with a headless Python core engine and a React/Tauri desktop UI.

**Architecture:**
- **Python Core Engine** (`to_reuse/python_core/sstv_engine/`) - Handles DSP, SSTV encoding/decoding, audio I/O, PTT control
- **Desktop UI** (`ssteve-ui--figma/`) - React/TypeScript UI components with friendly, approachable interface
- **Legacy Shell** (`to_reuse/desktop_app_shell/`) - Previous Tauri integration (may contain reusable code)
- **Testing Assets** (`to_reuse/testing_assets/`) - Reference audio/images for validation

**Key Principle:** Strict separation between DSP/business logic (Python) and UI (React). Communication happens via REST API and WebSocket.

## Building & Running

### Python Core Engine

```bash
cd to_reuse/python_core

# Create/activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest

# Run CLI tools (after installing: pip install -e .)
sstv-decode --help
sstv-encode --help
```

### Desktop Application (Tauri + React)

```bash
cd to_reuse/desktop_app_shell

# Install dependencies
npm install

# Development mode (starts Vite + Tauri)
npm run dev

# Production build
npm run build

# Run bundled application
npm run tauri
```

### Running Tests

```bash
# Python unit tests
cd to_reuse/python_core
pytest

# Integration/E2E tests
cd to_reuse/desktop_app_shell
npm run test:e2e
```

## Architecture & Code Organization

### Python Core (`to_reuse/python_core/sstv_engine/`)

**Key Modules:**
- `decoder.py` - SSTV signal decoding (VIS detection, sync tracking, scanline extraction)
- `encoder.py` - SSTV image encoding (mode conversion, audio generation)
- `streaming.py` - Real-time audio I/O with sounddevice
- `enhancer.py` - Signal processing (AFC, slant correction, noise reduction)
- `cli.py` - Command-line interface for standalone operation
- `types.py` - Data models and enums (SSTV modes, image formats)
- `wrapper.py` - High-level API for common operations

**Dependencies:**
- `sounddevice` - Cross-platform audio I/O
- `numpy`/`scipy` - Signal processing, FFT, filters
- `Pillow` - Image manipulation
- `fastapi`/`uvicorn` - REST API server (future)
- `pyserial` - PTT control via serial port

**Testing Strategy:**
- Unit tests validate individual decoders/encoders
- Reference audio files in `to_reuse/testing_assets/` provide ground truth
- Pytest fixtures handle audio device mocking

### Desktop UI (`ssteve-ui--figma/`)

**Key Components:**
- `App.tsx` - Root component with view routing
- `components/CaptureView.tsx` - RX interface (listening, decoding, canvas)
- `components/TransmitView.tsx` - TX interface (image upload, mode selection, PTT)
- `components/DevicesView.tsx` - Audio device selection, PTT configuration
- `components/LogView.tsx` - Gallery of received/transmitted images
- `components/ui/` - Reusable UI primitives (shadcn/ui based)

**State Management:**
- Uses Zustand for lightweight global state
- WebSocket subscriptions for real-time decode progress
- REST API calls for device enumeration, image retrieval

**Design System:**
- Based on Tailwind CSS v4.0
- Friendly & approachable aesthetic (dark UI, helpful guidance)
- Color palette: Deep blue-charcoal backgrounds (#0D1016, #151924), lime accents (#7CFF8A for locked state), amber (#F2B451 for progress)
- See `ssteve-ui--figma/DESIGN_RATIONALE.md` for detailed design principles

### API Contract (Planned)

**Reference:** `docs/app-spec.md` defines the REST/WebSocket interface between Python core and UI.

**Key Endpoints:**
- `POST /decode/start` - Begin listening for SSTV signal
- `GET /decode/status/{session_id}` - Check decode progress
- `POST /transmit` - Transmit image with PTT control
- `GET /devices/audio` - Enumerate audio devices
- `GET /devices/serial` - List serial ports for PTT
- `ws://localhost:8000/api/v1/ws/decode/{session_id}` - Real-time scanline updates

## Critical Design Decisions

### UX Philosophy (from recent expert reviews)

**Current State:** The UI has 27+ visible controls in Capture view, optimized for experienced SSTV operators who need simultaneous visibility of signal processing parameters.

**Active Debate:** Four expert reviews (UX Design, UX Research, Brand Strategy, SSTV Domain) recently evaluated the interface:

1. **UX experts recommend:** Progressive disclosure (8 essential controls, advanced hidden by default)
2. **SSTV expert recommends:** Keep manual controls visible (AFC range, gain, squelch) due to signal variability
3. **Brand strategy recommends:** "Design defaults so good users forget configuration"

**Resolution Pending:** The codebase reflects the "instrument panel" philosophy (dense, expert-friendly). Any simplification work should reference the expert reviews in this conversation thread.

### Key Technical Constraints

**Auto-Detection Limitations (per SSTV Expert):**
- Input gain auto-detect from 2 seconds: Fails on QSB (fading) signals (~30-40% failure rate)
- AFC auto-only: Dangerous for satellites (Doppler shift), causes wrong-mode decodes
- Squelch auto-threshold: Fails in contest QRM environments

**Implication:** Manual overrides for gain/squelch/AFC must remain accessible in primary interface, not buried in Settings.

### PTT Control

**Serial PTT:** RTS/DTR signal via pyserial (Digirig, RigBlaster)
**VOX PTT:** Preamble silence injection (SignaLink)
**Timing:** Pre-delay (500ms), post-delay (200ms) configurable

### Accessibility Features

- **Stereo sonification:** Slant error → stereo pan for blind operators
- **Verbose CLI mode:** JSON logging for screen readers
- **WCAG 2.1 AA compliance:** 4.5:1 contrast ratios, keyboard navigation
- **Operating Conditions modes:** Standard, Night Vision (red-shifted), Sunlight (high contrast)

## Development Workflow

### When Working on UI

1. Reference `ssteve-ui--figma/DESIGN_RATIONALE.md` for design principles (friendly & nerdy voice, helpful guidance, approachable interface)
2. Check `docs/app-spec.md` for API contracts before adding backend calls
3. Use shadcn/ui components from `ssteve-ui--figma/components/ui/`
4. Test with realistic signal conditions (use test assets in `to_reuse/testing_assets/`)

### When Working on Python Core

1. All audio I/O goes through `streaming.py` (abstraction layer for device management)
2. Signal processing functions should be stateless where possible
3. Test with reference audio files (`to_reuse/testing_assets/reference/audio/`)
4. Expected decode results in `to_reuse/testing_assets/reference/images/`
5. Use pytest fixtures for audio device mocking (avoid real audio hardware in CI)

### When Bridging UI and Core

1. **Do NOT** implement API endpoints yet - the Python core is currently CLI-only
2. When adding API layer, follow FastAPI + WebSocket pattern in `docs/app-spec.md`
3. WebSocket events must include: `vis_detected`, `scanline_update`, `decode_complete`, `error`
4. Respect the modular boundary: UI never calls audio I/O directly

## Testing Strategy

**Unit Tests (Python):**
- `pytest to_reuse/python_core/tests/`
- Tests validate decoder/encoder accuracy against reference images
- Use `pytest -k test_name` to run single test

**Integration Tests:**
- Cross-validate Python CLI output with UI expectations
- Test PTT timing with mock serial ports

**E2E Tests (Playwright):**
- `npm run test:e2e` in `to_reuse/desktop_app_shell/`
- Cover critical flows: first capture, first transmit, device selection

## User Archetypes (Design Targets)

**Makers:** Technical users wanting scriptable/headless CLI
**Activators:** Field operators (POTA/SOTA) needing fast, offline workflows
**Preppers:** Pragmatists wanting "just works" reliability
**Old Guard:** MMSSTV migrants expecting familiar patterns

Design decisions should serve all four, with progressive disclosure enabling both novice and expert workflows.

## Voice and Messaging

Per `/home/admin/CLAUDE.md` guidance:
- Minimize "I'm building/making" declarations (sounds authoritative without validation)
- This is a project in progress, not a vetted/finished product
- Language should invite collaboration, not claim expertise

## Available Specialized Agents

Claude Code has access to specialized agents via the Task tool. Use these agents for complex, multi-step tasks that require domain expertise.

### Codebase Exploration & Planning

**`Explore` Agent**
- **Purpose:** Fast codebase exploration and search
- **Use when:** You need to find files by patterns, search for keywords, or understand code structure
- **Thoroughness levels:** "quick", "medium", "very thorough"
- **Example:** Finding all SSTV mode implementations, locating API endpoint definitions, understanding decoder architecture
- **When NOT to use:** For specific file paths you already know (use Read instead)

**`Plan` Agent**
- **Purpose:** Software architecture and implementation planning
- **Use when:** Designing implementation strategy for complex features
- **Returns:** Step-by-step plans, critical file identification, architectural trade-offs
- **Example:** Planning the FastAPI/WebSocket layer, designing progressive disclosure for UI controls, architecting auto-detection system
- **When NOT to use:** For simple, straightforward tasks with obvious implementation

**`general-purpose` Agent**
- **Purpose:** Complex research, multi-step tasks, open-ended searches
- **Use when:** Searching for code/files without confidence in finding the right match quickly
- **Example:** Researching how MMSSTV handles AFC, investigating performance patterns across the codebase
- **When NOT to use:** For targeted file reading or specific keyword searches

### Design & User Experience

**`ux-design-strategist` Agent**
- **Purpose:** Expert UX design, visual systems, accessibility, design critique
- **Use when:**
  - Designing new UI components (CaptureView layout, Settings modal)
  - Evaluating existing designs for usability/accessibility
  - Making decisions about visual hierarchy, interaction patterns
  - Ensuring WCAG 2.1 AA compliance
  - Solving interaction design problems (progressive disclosure, status indicators)
- **Example:** "Evaluate the CaptureView control density for novice users" or "Design accessible audio level indicators for blind operators"
- **Context:** This agent reviewed the current SSTeVe UI and provided the "instrument vs debug panel" critique

**`brand-messaging-strategist` Agent**
- **Purpose:** Branding, messaging frameworks, visual identity, marketing positioning
- **Use when:**
  - Developing brand positioning (SSTeVe's "friendly & nerdy" voice)
  - Creating messaging for different user archetypes (Makers, Activators, Preppers, Old Guard)
  - Translating project goals into brand assets
  - Voice and tone guidelines
  - User-facing content strategy
- **Example:** "Develop messaging that balances technical precision with accessibility" or "Frame 'Operating Conditions' modes as operational features, not aesthetic preferences"
- **Context:** This agent reconciled the Palette Mode debate by reframing it from aesthetic to operational

### Documentation & Communication

**`claude-code-guide` Agent**
- **Purpose:** Claude Code features, Agent SDK architecture, development workflows
- **Use when:** User asks about Claude Code capabilities, hooks, slash commands, MCP servers
- **Example:** "How do I write a custom slash command?" or "What Agent SDK patterns should I follow?"
- **Important:** Check if there's already a running claude-code-guide agent to resume (more efficient than spawning new)

**`jeremy-voice-writer` Agent**
- **Purpose:** Written content in Jeremy Fuksa's authentic voice
- **Use when:** Creating blog posts, social teasers, technical observations, comment responses
- **Example:** Developing an SSTV signal processing discovery into a blog post, crafting README copy
- **Note:** This is project-owner specific; use only when Jeremy requests content in his voice

### Agent Usage Guidelines

**Launch Multiple Agents in Parallel:**
When tasks are independent, maximize performance by making multiple Task tool calls in a single message.

**Provide Detailed Context:**
Each agent invocation is stateless. Your prompt should contain a complete task description including:
- What the agent needs to analyze
- What decisions they should make
- What information they should return
- Any relevant project context

**Resume When Possible:**
For claude-code-guide agent, check if there's already a running instance you can resume using the `resume` parameter (maintains context, more efficient).

**Trust Agent Outputs:**
Agents with specialized expertise should generally be trusted. Review their recommendations critically but recognize their domain knowledge.

### Historical Context: The Four-Expert UX Review

In December 2025, a comprehensive UX debate involving four specialized agents evaluated the SSTeVe interface design:

1. **UX Design Strategist** - Identified "nervous system not instrument" problem, recommended canvas dominance (60% viewport), progressive disclosure
2. **UX Researcher** - Quantified issues (33 controls → 45-60min time-to-proficiency), demanded evidence-based validation
3. **Brand Messaging Strategist** - Reconciled aesthetic vs operational needs, coined "design defaults so good users forget configuration"
4. **SSTV Domain Expert** - Validated technical constraints (auto-detect fails 30-40%, AFC auto-only dangerous), defended operational complexity

**Key Outcomes:**
- Canvas visibility during listening is non-negotiable
- Waterfall display is essential
- Auto-detection can set defaults but manual overrides must be accessible
- "Operating Conditions" modes serve real needs (night vision preservation, field contrast)
- 8-control interface vs 15-control interface debate remains unresolved (requires user testing)

**When making UI changes:** Reference this debate. The tension between simplicity and operational flexibility is intentional and reflects real constraints of SSTV signal variability.

## Files to Reference

- `docs/app-spec.md` - Complete API specification and feature requirements
- `ssteve-ui--figma/DESIGN_RATIONALE.md` - UI design philosophy and component decisions
- `/home/admin/CLAUDE.md` - General Claude workflow and tool collaboration patterns
- `GEMINI.md` - Gemini-specific codebase analysis (build commands, conventions)
