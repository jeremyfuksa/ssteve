# Code Review Template - SSTV Project

## Context Required
- **Layer**: L1+L2 (Core + Development minimum)
- **Focus**: Maintainability, performance, SSTV-specific correctness

## Review Checklist

### 1. Architecture Compliance
- **colaclanth/sstv Integration**: No attempts to replace or reimplement core library
- **Tauri Patterns**: Proper command structure, error handling
- **File-based Audio**: Maintains real-time performance approach
- **Cross-platform**: No platform-specific assumptions

### 2. Code Quality
- **Error Handling**: Proper Result types in Rust, try/catch in JS
- **Resource Management**: File cleanup, subprocess management
- **Performance**: No blocking operations in UI thread
- **Security**: No path injection, subprocess argument validation

### 3. SSTV Domain Logic
- **Audio Timing**: Critical for proper SSTV decoding
- **Mode Detection**: VIS code handling, fallback strategies
- **Image Processing**: Correct dimensions, aspect ratios
- **Signal Quality**: Proper handling of noisy/partial signals

### 4. UI/UX Consistency
- **Tab Integration**: Fits existing interface pattern
- **Status Feedback**: Clear progress indication for long operations
- **Error Messages**: User-friendly, actionable feedback
- **Styling**: Maintains retro phosphor green theme

### 5. Testing Requirements
- **Reference Validation**: Works with known test files
- **Real-world Testing**: Tested with actual SSTV signals
- **Error Conditions**: Graceful handling of invalid inputs
- **Performance**: Real-time processing maintains timing

### 6. Documentation
- **Code Comments**: Complex logic explained
- **TODO Management**: Outstanding work tracked
- **CLAUDE.md Updates**: Architecture changes documented