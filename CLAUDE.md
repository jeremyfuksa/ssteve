# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an SSTV (Slow-scan Television) decoder project that has **successfully implemented** a production-quality SSTV decoding engine using the proven colaclanth/sstv Python library. The project creates a robust, cross-platform desktop application using Tauri framework.

**Current Status**: ✅ **PHASE 4B COMPLETE** - Real-time functionality implemented. Live audio capture → SSTV decode pipeline working.

## Shared CLI Tools

The `ai` command is available for interacting with the central `~/.ai-docs` knowledge base.

**Usage:**
- `ai new "topic"`: Create a new document.
- `ai list [filter]`: List recent documents.
- `ai search "term"`: Search document contents.
- `ai open <pattern>`: Fuzzy find and open a document.

## Project Architecture (IMPLEMENTED)

**✅ PRODUCTION ARCHITECTURE:**

1. **SSTV Decoder**: **colaclanth/sstv Python library** (GitHub: colaclanth/sstv)
   - **STATUS**: ✅ FULLY INTEGRATED - Produces perfect reference-quality results
   - **IMPLEMENTATION**: Real-time streaming decoder with progressive image rendering
   - **INTEGRATION**: Python subprocess calls via Tauri backend commands

2. **SSTV Encoder**: **PySSTV Python library**
   - **STATUS**: ✅ FULLY INTEGRATED - Supports multiple SSTV modes
   - **MODES**: ScottieS1, ScottieS2, ScottieDX, MartinM1, MartinM2, Robot36
   - **INTEGRATION**: Tauri command interface with progress feedback

3. **Desktop Framework**: **Tauri v2** (Rust backend + Vanilla JS frontend)
   - **STATUS**: ✅ FULLY OPERATIONAL - Cross-platform desktop application
   - **BACKEND**: Rust with audio state management and subprocess handling
   - **FRONTEND**: Modern vanilla JavaScript with phosphor green retro UI theme

4. **UI Architecture**: **Tab-based Dynamic Interface**
   - **STATUS**: ✅ FULLY FUNCTIONAL - All 4 modes working correctly
   - **MODES**: Receive, Transmit, Gallery, Setup with mode-specific controls
   - **RECENT FIX**: DOM timing issue resolved for proper tab switching

5. **Image Enhancement Pipeline**: **PIL-based Image Processing**
   - **STATUS**: ✅ FULLY INTEGRATED - Professional image enhancement capabilities
   - **FEATURES**: Contrast, brightness, saturation, auto-level, gamma, white balance, sharpening
   - **PRESETS**: 5 built-in presets (conservative, moderate, aggressive, white_balance_only, auto_level_only)
   - **INTEGRATION**: Tauri commands with both preset and manual control options

## ⚠️ CRITICAL LIBRARY DECISION - DO NOT OVERRIDE

**SSTV Library: colaclanth/sstv (Python)**
- **Status**: FINAL CHOICE - Produces perfect reference-quality results
- **Repository**: https://github.com/colaclanth/sstv  
- **Integration**: Python subprocess calls via Tauri backend
- **Quality**: Near-perfect matches to MMSSTV reference images
- **DO NOT**: Attempt to replace, port, or "improve" this library

## Development Workflow

### Key Principles
- Try the simple approach first, optimize only if needed
- Build features that actually get used
- Don't over-engineer hobby software
- Commit working code frequently
- Each Phase should be a branch. When we verify that phase works, we can merge it back into the main branch and then start a new branch for the next phase.

### Straightforward Development
**✅ ACTUALLY COMPLETED:**
- **Phase 1**: Library Selection → ✅ SUCCESS (colaclanth/sstv works perfectly)
- **Phase 4A**: Framework & UI → ✅ SUCCESS (Complete UI with tab-based interface)
- **Phase 4B**: Real-time Functionality → ✅ SUCCESS (Live audio capture → SSTV decode pipeline working)

**🚧 CURRENT PHASE:**
- **Phase 5**: Signal Analysis - Add features that enhance real-world usage

**📋 NEXT PHASES:**
- **Phase 5**: Add features if Phase 4B works fine, or fix performance if it doesn't
- **Phase 6**: More features based on actual usage
- **Future**: Whatever seems useful after using the app

## Current Implementation Status

### ✅ **WORKING FEATURES**
- **Real-time SSTV Decoding**: Progressive image rendering with streaming decoder
- **SSTV Image Encoding**: Multiple modes (Scottie S1/S2/DX, Martin M1/M2, Robot36)
- **Image Enhancement System**: Complete PIL-based enhancement pipeline with presets and manual controls
- **Tab-based UI**: Receive, Transmit, Gallery, Setup modes with dynamic controls
- **Audio State Management**: Mute/unmute functionality with audio passthrough
- **Test System**: Built-in test files with real MMSSTV and Essex Ham samples
- **Cross-platform Desktop**: Tauri app builds on macOS, Windows, Linux

### ✅ **COMPLETED FEATURES (Phase 4A: Framework & UI)**
- **Gallery Management**: Complete browsing, organization, file operations, and folder access
- **Settings Persistence**: JSON-based configuration save/load with import/export
- **Sample Images Integration**: Full sample image browser with thumbnail gallery
- **Audio Input Framework**: UI and backend commands for device selection and capture control
- **Error Handling**: Comprehensive user feedback with proper status messages
- **UI Polish**: Professional color schemes, smooth animations, and complete interactions
- **File Management**: Save, delete, copy, cleanup operations with native folder access

### ✅ **COMPLETED FEATURES (Phase 4B: Real-time Functionality)**
- **Live Audio Capture**: ✅ CPAL-based microphone input with real-time recording
- **Real-time SSTV Processing**: ✅ Live audio → PCM → WAV → Python decoder pipeline
- **Native File Dialogs**: ✅ Tauri dialog plugin for proper file selection
- **Live Processing UI**: ✅ "Process Live Audio" button with status feedback
- **Performance**: ✅ File-based approach handles real-time audio without blocking

### 📋 **PLANNED FEATURES (Phase 5: Signal Analysis - "Good Enough" Approach)**
- **Basic FFT Spectrogram**: Simple Web Audio API spectrum display with canvas rendering
- **Signal Quality Metrics**: Basic SNR estimation and signal strength indicators
- **Basic Hamlib Integration**: Simple CAT control for popular transceivers
- **Improved VIS Detection**: Better mode detection without complex algorithms
- **Basic Image Correction**: Simple skew and timing adjustments

### 🔄 **FUTURE ENHANCEMENTS (Phase 6+)**
- **Single TNC Integration**: Basic KISS protocol support for one popular TNC (Mobilinkd TNC3)
- **Retro UI Theming**: CSS-based color schemes (phosphor green, amber) and subtle styling
- **Plugin Architecture**: Extension points for future protocol additions
- **Advanced Image Processing**: Additional enhancement algorithms and batch processing
- **Extended Signal Analysis**: More sophisticated SNR and signal quality metrics

### ❌ **EXPLICITLY REJECTED (Over-Ambitious)**
- **Multi-TNC Universal Protocol Stack**: Too complex, limited benefit
- **GPU-Accelerated FFT Processing**: Over-engineered for SSTV bandwidth
- **Complete UI Redesign**: Working UI shouldn't be thrown away
- **Experimental Protocol Implementation**: M17/HamDRM premature for adoption
- **Research-Level DSP**: Academic features beyond practical application scope

## Development Notes
- **Python Environment**: Using brew version of python3, no venv needed
- **Testing Structure**: Results saved to `testing/results/decode` and `testing/results/encode`
- **Commit Strategy**: Major feature changes require descriptive git commits
- **Library Constraints**: NEVER replace colaclanth/sstv - it produces perfect results
- make extensive use of TODOs in code and a TODO file
- as you work, leave TODO comments with unfinished tasks or subtasks that need to be completed in the future, and reference them in TODO.md

## UI Development Workflow
- After making UI changes:
  - npm run build          # Update dist with latest frontend
  - npm run tauri dev      # Launch with fresh UI

  This prevents the cached/stale frontend issues we just experienced.

## MCP Server Capabilities

I have access to several MCP servers that provide different capabilities:

### Filesystem Operations
- **mcp__filesystem__*** - File reading, writing, editing, directory operations, search, etc.

### Memory/Knowledge Graph
- **mcp__memory__*** - Create entities, relations, observations, search nodes, etc.

### Sequential Thinking
- **mcp__sequential-thinking__sequentialthinking** - Structured problem-solving through thought processes

### Context7 Documentation
- **mcp__context7__resolve-library-id** - Resolve library names to IDs
- **mcp__context7__get-library-docs** - Fetch up-to-date library documentation

### GitHub Integration
- **mcp__github__*** - Repository operations, file management, issues, PRs, search, etc.

### Built-in Tools
- **Task** - Launch agents for complex searches and analysis
- **Bash** - Execute shell commands
- **Glob/Grep** - File pattern matching and content search
- **Read/Write/Edit** - Direct file operations
- **LS** - Directory listing
- **WebFetch/WebSearch** - Web content retrieval
- **TodoRead/TodoWrite** - Task management

## Communication Style

- Skip affirmations and compliments. No "great question!" or "you're absolutely right!" - just respond directly
- Challenge flawed ideas openly when you spot issues
- Ask clarifying questions whenever my request is ambiguous or unclear
- When I make obvious mistakes, point them out with gentle humor or playful teasing

**Example behaviors:**
- Instead of: "That's a fascinating point!" → Just dive into the response
- Instead of: Agreeing when something's wrong → "Actually, that's not quite right because…"
- Instead of: Guessing what I mean → "Are you asking about X or Y specifically?"
- Instead of: Ignoring errors → "Hate to break it to you, but 2+2 isn't 5…"

Overall, remember that I am autistic and smalltalk and needless conversational fluff stesses me out and makes my work harder.

## Communication Rules
- The phrase "You're absolutely right!" is banned. See other rules on how to communicate.
# brain_version: 1.1.0