# SSTV Application - Native Development Requirements

## Executive Summary

This document outlines the requirements for developing a modern SSTV (Slow-Scan Television) application using native development approaches, prioritizing macOS first, then iOS, Android, and Windows. The application embodies the aesthetic and functional qualities of premium 1980s/90s hi-fi equipment while delivering contemporary software performance.

## Development Philosophy & Constraints

### Core Principles
- **Native First**: Platform-specific development to avoid multi-platform tool limitations
- **Cross-Platform UX Consistency**: Identical user experience across all platforms while respecting native conventions
- **Digital Rack Unit**: Single, cohesive interface resembling premium audio equipment
- **Receive-First**: Initial focus on decoding excellence before transmission features
- **Progressive Enhancement**: Start with core functionality, add sophistication iteratively

### Platform Progression
1. **macOS** (Primary platform) - SwiftUI/AppKit hybrid
2. **Windows** (Secondary) - WinUI 3 (C++)
3. **Linux** (Tertiary) - GTK4/C++ or Qt6/C++

## Technical Architecture

### Backend Strategy
- **Python DSP Core**: Centralized signal processing engine leveraging NumPy/SciPy ecosystem
- **Native Interface Layer**: Platform-specific bridges for optimal Python integration
- **Shared Memory Architecture**: Zero-copy audio transfer between native frontend and Python backend
- **Cross-Platform Consistency**: Identical DSP behavior across all desktop platforms

### Frontend Architecture
- **Single Window**: Fixed-size, non-resizable "chassis" design (identical across platforms)
- **State Machine**: Clear mode transitions (Receive → Transmit → Gallery → Setup) with identical behavior
- **Component System**: Reusable UI elements styled as physical hardware with pixel-perfect consistency
- **Theme Engine**: Black/Silver chassis with amber/cyan/green display options (identical color values)
- **Interaction Model**: Consistent touch/click targets and behaviors across platforms
- **Layout System**: Absolute positioning system to ensure pixel-perfect layout matching

## Cross-Platform UX Consistency Strategy

### 1. Design System Foundation

**Shared Design Tokens**
- Exact color values (hex/RGB) maintained across platforms
- Identical typography scale with platform-appropriate fonts
- Consistent spacing units (8px grid system)
- Shared animation timing curves and durations
- Identical component dimensions and positioning

**Reference Implementation**
- macOS version serves as the master reference
- All other platforms must match pixel-perfect (within 1px tolerance)
- Shared design system documentation with exact specifications
- Cross-platform design review process for any changes

### 2. Component Consistency Requirements

**Visual Matching**
- Identical button states, colors, and shadows
- Same knob rotation angles and positions
- Matching VFD display characteristics (glow, font, timing)
- Consistent spectrum analyzer behavior and appearance
- Identical status messages and error states

**Behavioral Consistency**
- Same interaction patterns (tap, drag, hover where applicable)
- Identical state transitions and animations
- Consistent audio processing behavior
- Same timing for all visual feedback
- Identical keyboard shortcuts (where platforms support them)

### 3. Desktop Platform Adaptation Strategy

**Hardware Interface Requirements**
- TNC serial port communication (USB, Bluetooth, RS-232)
- SDR software integration via Virtual Audio Cables
- Professional audio interface support
- Multi-device audio routing capabilities
- Real-time audio processing with <100ms latency

**Native Feel Through**
- Platform-appropriate window management and decorations
- Native audio APIs optimized for each platform
- Platform-specific hardware device enumeration
- Native file dialogs and system integrations
- Appropriate platform conventions for accessibility and keyboard shortcuts

**Consistent UX Through**
- Identical application layout and component positioning
- Same visual design language and color schemes
- Consistent interaction paradigms and feedback
- Identical feature set and hardware capabilities
- Same information architecture and navigation patterns

## Phase 1: macOS Foundation (MVP)

### 1.1 Core Application Structure (Master Reference)

**Main Window (720x480pt fixed) - EXACT DIMENSIONS FOR ALL PLATFORMS**
- Non-resizable, centered window with platform-appropriate title bar
- Brushed aluminum background texture (identical across platforms)
- Two-column layout: 65% display, 35% controls (exact pixel positions documented)
- Desktop-class audio device permission handling
- Hardware interface status indicators (TNC connection, SDR status)

**Main Window (720x480pt fixed)**
- Non-resizable, centered window with title bar
- Brushed aluminum background texture
- Two-column layout: 65% display, 35% controls
- Window-level audio device permission handling

**Color Themes**
- Black Chassis: Dark aluminum with warm highlights
- Silver Chassis: Light aluminum with cool highlights
- Display Colors: Cyan (default), Amber, Phosphor Green

### 1.2 Main Display Component (VFD Simulation)

**Idle State - Spectrum Analyzer**
- Real-time FFT visualization styled as VFD display
- Glowing cyan/amber/green elements on dark background
- Segmented font for status text ("LISTENING...", "MODE: AUTO")
- Smooth 60fps animation with appropriate decay

**Decoding State - Image Preview**
- Line-by-line image rendering as decoding progresses
- Smooth transition from spectrum to image display
- Progress indication via status text
- Image scaling/fitting algorithms for different SSTV modes

**Technical Requirements**
- Metal/Core Graphics rendering for performance
- Perceptually uniform colormaps (Viridis, Cividis)
- Configurable FFT parameters (1024/2048 samples)
- Memory-efficient image buffer management

### 1.3 Control Surface Components

**Function Button Bank**
- Four chunky buttons: RECEIVE, TRANSMIT, GALLERY, SETUP
- Active state: pressed appearance with LED indicator
- Inactive state: raised appearance, dimmed LED
- Smooth state transitions with tactile feedback

**Rotary Mode Selector**
- Graphical knob with printed mode labels on faceplate
- Snap-to-position behavior with haptic feedback (macOS)
- Modes: Auto, Scottie S1, Scottie S2, Martin M1, PD120, PD180
- Mode information display with duration and format specs

**Audio Level Indicators**
- VU meter with green/amber/red segments
- Real-time audio level monitoring
- Proper ballistics (attack/decay timing)
- Overload indication and clipping warnings

### 1.4 Backend Integration (macOS)

**Audio System**
- Core Audio integration for low-latency capture
- Professional audio interface support (USB, Thunderbolt)
- Virtual Audio Cable detection and integration
- Audio device enumeration and selection
- Automatic sample rate conversion to 11.025kHz
- Real-time buffering with overflow protection
- MIDI device integration for PTT control

**Python Bridge**
- Native Swift → Python communication via embedded interpreter
- Audio streaming via shared memory buffer (mmap)
- Control messages via MessagePack serialization
- Persistent Python process to avoid startup overhead
- Error handling with graceful recovery mechanisms

**DSP Engine (Python)**
- NumPy/SciPy-based signal processing for proven correctness
- STFT implementation with configurable parameters (scipy.signal.spectrogram)
- Perceptually uniform colormaps (Viridis, Cividis) for accurate visualization
- VIS code detection using robust FSK demodulation
- Automatic slant correction via Hough Transform
- Multi-mode SSTV decoding (Scottie, Martin, PD families)
- Real-time audio processing with <100ms total latency

### 1.5 User Experience Requirements

**Startup Behavior**
- Immediate audio device detection
- Auto-select default input device
- Begin spectrum analyzer immediately
- No configuration required for basic operation

**Status Communication**
- Persistent status bar at bottom of window
- Clear, non-technical language
- States: "Listening on [Device]", "Decoding [Mode]", "Image Complete"
- Error states with actionable messages

**Settings Panel**
- Audio input/output device selection with professional interface support
- TNC connection configuration (serial ports, Bluetooth)
- SDR integration settings (Virtual Audio Cable routing)
- Display color theme selection
- Hardware interface status and diagnostics
- Manual control toggle (Start/Stop/Save buttons)
- About panel with credits and version info

## Phase 2: Windows Implementation (UX Consistency Priority)

### 2.1 Technology Stack - WinUI 3 (C++)

**Implementation Requirements**
- Native performance for custom component rendering
- Direct Windows API access for audio and hardware
- Maximum control over exact UI rendering to match macOS reference
- WASAPI integration for professional audio interfaces
- Windows-specific hardware enumeration (COM ports, USB devices)

### 2.2 Windows-Specific Features (Without UX Changes)

**Hardware Integration**
- WASAPI for low-latency audio with professional interface support
- Windows serial port enumeration (COM ports)
- USB device detection and management
- Virtual Audio Cable integration (VB-Cable, VoiceMeeter)
- Windows audio device routing and exclusive mode support

**System Integration**
- Native Windows notifications (maintaining identical content)
- File type associations for WAV files
- Windows registry integration for settings
- Windows Store packaging and auto-update
- All system integrations maintain identical application UI

### 2.3 Platform Integration Rules

**What Changes (Native Feel)**
- Windows-specific audio device enumeration
- Serial port discovery and management
- File system access patterns
- Windows notification system
- Hardware device permission flows

**What Stays Identical (Consistent UX)**
- All application UI components and positioning
- Hardware interface status displays
- Audio processing behavior and latency
- TNC and SDR integration workflows
- Feature functionality and access patterns

## Phase 3: Linux Implementation (UX Consistency Priority)

### 3.1 Technology Stack Decision

**Option A: GTK4 (C++) - RECOMMENDED**
- Modern Linux desktop integration
- Good hardware access capabilities
- Cross-distribution compatibility
- Native package management integration

**Option B: Qt6 (C++)**
- Excellent cross-platform consistency tools
- Superior custom rendering capabilities
- Commercial licensing considerations
- Potentially easier to match macOS reference exactly

### 3.2 Linux-Specific Features (Without UX Changes)

**Hardware Integration**
- ALSA/PulseAudio for professional audio interface support
- Linux serial port enumeration (/dev/ttyUSB*, /dev/ttyACM*)
- USB device detection via udev
- Linux virtual audio solutions (JACK, PipeWire)
- Audio device routing and low-latency configuration

**System Integration**
- Native Linux notifications via D-Bus
- XDG desktop integration (file associations, .desktop files)
- Linux package management (deb, rpm, AppImage)
- System-wide configuration management
- All system integrations maintain identical application UI

### 3.3 Distribution Strategy

**Package Formats**
- AppImage for universal Linux distribution
- Native packages for major distributions (Ubuntu/Debian, Fedora/CentOS)
- Flatpak for sandboxed distribution
- Source code availability for custom builds

**Hardware Compatibility**
- Support for common USB-to-serial adapters
- Amateur radio interface compatibility (SignaLink, RigBlaster)
- RTL-SDR and other common SDR hardware
- Professional audio interface support (Focusrite, PreSonus)

## Phase 4: Post-Launch Hardware Integration

### 4.1 TNC Integration (Phase 1 Extension)

**Supported Hardware**
- Mobilinkd TNC3/TNC4 (USB CDC, Bluetooth SPP)
- Byonics TinyTrak4 (RS-232, USB-to-serial)
- Kantronics KPC-3+ and similar (RS-232)
- Modern USB-based TNCs

**KISS Protocol Implementation**
- Standard KISS frame handling
- G8BPQ extensions for advanced features
- Automatic TNC configuration where possible
- Connection state management and recovery

### 4.2 SDR Integration (Phase 2 Extension)

**Local SDR Support**
- SDRUno integration via Virtual Audio Cable + CAT control
- Direct SDRplay API integration (future)
- RTL-SDR support via SDR# or similar
- Professional SDR hardware support

**Network SDR Support**
- KiwiSDR protocol implementation
- Spyserver protocol support
- WebSDR integration (with appropriate limitations)
- Public SDR directory integration (Receiverbook.de)

## Python DSP Engine Architecture

### 6.1 Technology Stack Justification

**Python Core Decision**
- **Scientific Ecosystem**: NumPy/SciPy provide battle-tested, validated implementations of STFT, FFT, and filtering algorithms essential for SSTV decoding
- **Algorithm Complexity**: Sophisticated features like automatic slant correction via Hough Transform, robust VIS code detection, and multi-mode support are significantly faster to implement and debug in Python
- **Correctness Priority**: SSTV decoding accuracy is more critical than raw performance - Python's scientific libraries ensure correctness
- **Cross-Platform Consistency**: Identical DSP behavior across macOS, Windows, and Linux with single codebase
- **Development Velocity**: Rapid iteration on decoding algorithms essential for amateur radio market

**Performance Analysis**
- **Adequate Performance**: Python DSP processing adds ~5-10ms latency on modern hardware
- **SSTV Nature**: Slow-scan television is inherently slow (71-180 second transmissions)
- **User Priority**: Decode accuracy and visual polish matter more than microsecond optimizations
- **Real-Time Capable**: Total processing latency <100ms easily achievable with optimized Python

### 6.2 Native-Python Integration Architecture

**Shared Memory Audio Pipeline**
```
Native Audio → Circular Buffer (mmap) → Python DSP → Results Buffer → Native Display
```

**Implementation Details**
- **Zero-Copy Transfer**: Memory-mapped circular buffer for audio samples
- **Persistent Python Process**: Embedded Python interpreter stays running to avoid startup costs
- **Message Passing**: MessagePack serialization for control commands and status updates
- **Error Recovery**: Native watchdog monitors Python process health with automatic restart

**Platform-Specific Integration**

**macOS (Swift)**
- Python.h embedded interpreter integration
- Core Audio → mmap buffer → Python processing
- Swift structured concurrency for background Python tasks
- Native Swift types bridged to Python via PyObjC patterns

**Windows (C++/WinUI3)**
- Python C API integration with WASAPI
- Windows shared memory objects for audio buffers
- C++ thread pool for Python task management
- Win32 error handling for Python process monitoring

**Linux (GTK4/Qt6)**
- Python C API with ALSA/PulseAudio integration
- POSIX shared memory for cross-process audio buffers
- Linux process monitoring and automatic restart
- D-Bus integration for system notifications

### 6.3 DSP Engine Implementation

**Core Processing Pipeline**
```python
# Simplified architecture example
class SSTVProcessor:
    def __init__(self):
        self.sample_rate = 11025  # Resampled from native rates
        self.fft_size = 1024      # Configurable for time/freq resolution
        self.window = 'hann'      # Optimal for SSTV signal characteristics
        
    def process_audio_buffer(self, samples):
        # Real-time STFT using scipy.signal.spectrogram
        frequencies, times, Sxx = signal.spectrogram(
            samples, 
            fs=self.sample_rate,
            window=self.window,
            nperseg=self.fft_size,
            scaling='density'
        )
        
        # VIS code detection using FSK demodulation
        vis_code = self.detect_vis_code(samples)
        
        # Mode-specific decoding if VIS detected
        if vis_code:
            decoded_line = self.decode_scanline(samples, vis_code)
            return {'type': 'line_data', 'data': decoded_line}
        
        # Return visualization data for spectrum display
        return {'type': 'spectrum', 'data': Sxx}
```

**Advanced Features**
- **Automatic Slant Correction**: Hough Transform implementation for timing drift correction
- **Multi-Mode Support**: Modular decoder architecture for Scottie, Martin, and PD families
- **Robust Sync Detection**: Matched filtering for horizontal sync pulse detection
- **Perceptually Uniform Visualization**: Proper colormap implementation for accurate signal representation

### 6.4 Performance Optimization Strategy

**Current Optimization**
- **Efficient Libraries**: NumPy operations use optimized BLAS/LAPACK
- **Memory Management**: Circular buffers prevent memory allocation overhead
- **Algorithmic Efficiency**: Overlap-add STFT processing for real-time performance
- **Caching**: Pre-computed window functions and filter coefficients

**Future Optimization Path (If Needed)**
1. **Profile First**: Identify actual bottlenecks in production use
2. **Selective C++ Extensions**: Use Cython or pybind11 for critical loops only
3. **Maintain Algorithm Logic**: Keep high-level DSP logic in Python for maintainability
4. **SIMD Optimization**: Vectorized operations for hot paths

**Performance Targets**
- **Audio Processing**: <10ms per buffer (easily achievable)
- **FFT Computation**: <2ms for 1024-point FFT
- **VIS Detection**: <5ms per analysis window
- **Total Latency**: <100ms end-to-end (specification requirement)

### 6.5 Cross-Platform Deployment

**Python Distribution Strategy**
- **Embedded Python**: Bundle Python interpreter with application
- **Dependency Management**: pip-tools for reproducible scientific stack
- **Platform Libraries**: NumPy/SciPy wheels for consistent behavior
- **Version Pinning**: Exact versions to prevent cross-platform differences

**Build System Integration**
- **macOS**: py2app or similar for Python bundling
- **Windows**: PyInstaller integration with WinUI3 installer
- **Linux**: AppImage or native packages with embedded Python
- **Testing**: Automated validation of DSP behavior across platforms

## Cross-Platform Implementation Strategy

### 7.1 Shared Design System

**Master Reference Documentation**
- Exact pixel coordinates for all UI elements
- RGB color values for all themes and states
- Typography specifications with platform font mappings
- Animation timing curves and durations
- Component state diagrams and transitions

**Implementation Guidelines**
- macOS implementation serves as the authoritative reference
- All other platforms must match within 1px tolerance
- Automated screenshot comparison testing
- Design review process for any UI changes
- Shared asset pipeline for consistent rendering

### 7.2 Development Workflow

**Design Consistency Process**
1. All UI changes prototyped and approved on macOS first
2. Changes implemented on all platforms simultaneously
3. Automated visual regression testing
4. Cross-platform design review before release
5. User testing to validate consistent experience

**Quality Assurance**
- Pixel-perfect comparison tools
- Automated UI testing across platforms
- Performance benchmarking for consistency
- User experience validation studies
- Cross-platform beta testing program

### 7.3 Platform-Specific Adaptations (Limited Scope)

**Acceptable Native Adaptations**
- System permission flows and dialogs
- File system access patterns
- Audio API implementations (with identical results)
- Notification systems (with identical content)
- Installation and update mechanisms
- Accessibility features (maintaining visual consistency)

**Prohibited Adaptations**
- UI component appearance changes
- Layout modifications or responsive behavior
- Different interaction patterns
- Platform-specific feature variations
- Different color schemes or theming
- Modified typography or spacing

## Technical Specifications

### 8.1 Supported SSTV Modes (Launch)

| Mode | Resolution | Duration | VIS Code |
|------|------------|----------|----------|
| Scottie S1 | 320×256 | ~110s | 60 |
| Scottie S2 | 320×256 | ~71s | 58 |
| Martin M1 | 320×256 | ~114s | 44 |
| PD120 | 640×496 | ~120s | 93 |
| PD180 | 640×496 | ~180s | 96 |

### 8.2 Audio Requirements

**Input Specifications**
- Sample rates: 44.1kHz, 48kHz (auto-conversion)
- Bit depths: 16-bit, 24-bit
- Channels: Mono preferred, stereo supported (L+R mix)
- Latency: <100ms for real-time processing

**Processing Pipeline**
- Resampling to 11.025kHz for SSTV processing
- Anti-aliasing filters
- DC offset removal
- Automatic gain control (optional)

### 8.3 Performance Targets

**Python Integration Performance**
- Python DSP processing: <10ms per audio buffer
- Native-Python communication: <1ms via shared memory
- Total end-to-end latency: <100ms (including display updates)
- Memory efficiency: <100MB total including Python scientific stack

**Compatibility**
- macOS 12.0+ (SwiftUI 3.0, Core Audio)
- Windows 10 version 1903+ (WinUI 3, WASAPI)
- Linux distributions with GTK4/Qt6 support
- Professional audio interface support across all platforms

## Development Milestones

### 9.1 Phase Timeline

### Phase 1: macOS MVP (Months 1-4)
- [ ] Python DSP engine with NumPy/SciPy integration
- [ ] Swift-Python bridge with shared memory audio pipeline
- [ ] Core application structure and chassis design
- [ ] VFD display implementation with hardware-like characteristics
- [ ] Professional audio pipeline integration
- [ ] Basic SSTV decoding for all launch modes
- [ ] Settings panel with hardware interface preparation
- [ ] Cross-platform Python deployment strategy

### Phase 2: Windows Port (Months 5-7)
- [ ] Python C API integration with WinUI 3
- [ ] Windows shared memory implementation for audio buffers
- [ ] WinUI 3 implementation matching macOS reference
- [ ] Windows audio system integration (WASAPI)
- [ ] Serial port and USB device enumeration
- [ ] Virtual Audio Cable integration
- [ ] Windows Store submission preparation
- [ ] Cross-platform Python consistency validation

### Phase 3: Linux Port (Months 8-10)
- [ ] Python C API integration with GTK4/Qt6
- [ ] POSIX shared memory for audio pipeline
- [ ] GTK4 or Qt6 implementation
- [ ] Linux audio system integration (ALSA/PulseAudio)
- [ ] Linux hardware device management
- [ ] Package management for multiple distributions
- [ ] Cross-platform feature parity validation
- [ ] Community beta testing program

### Phase 4: Hardware Integration (Months 11-12)
- [ ] Python-based TNC integration implementation
- [ ] SDR integration via Virtual Audio Cable
- [ ] Hardware interface status and diagnostics
- [ ] Advanced audio routing capabilities
- [ ] Performance optimization of Python pipeline
- [ ] Final cross-platform hardware testing
- [ ] Professional deployment and distribution

## Quality Assurance for Cross-Platform Consistency

### Testing Strategy
- **Visual Consistency Testing**: Automated pixel-perfect comparison across platforms
- **Behavioral Testing**: Identical interaction patterns and responses
- **Performance Testing**: Consistent audio processing latency and quality
- **User Experience Testing**: Cross-platform usability validation
- **Integration Testing**: Platform-specific features maintaining identical core UX

### Success Metrics for Consistency
- **Visual Accuracy**: 99%+ pixel-perfect match between platforms
- **Behavioral Consistency**: Identical user flows and interactions
- **Performance Parity**: <5% difference in audio processing metrics
- **User Satisfaction**: Platform preference based on system integration, not app UX
- **Feature Completeness**: 100% feature parity across platforms

## Success Metrics

**Technical Metrics**
- Successful decode rate >95% for clean signals
- Audio processing latency <100ms
- App startup time <3 seconds
- Memory usage within platform limits

**User Experience Metrics**
- Time to first successful decode <30 seconds
- User retention after 7 days >70%
- App Store ratings >4.5 stars
- Support ticket volume <5% of downloads

## Risk Mitigation

**Technical Risks**
- Python integration complexity → Early prototyping of shared memory architecture
- Cross-platform Python deployment → Standardized build system with embedded interpreter
- Audio latency issues → Test Python performance on minimum spec devices
- Platform API changes → Monitor developer updates and maintain compatibility layers
- Performance bottlenecks → Profile Python DSP pipeline early and optimize selectively

**Product Risks**
- Feature creep → Strict MVP definition with Python-first DSP implementation
- Platform fragmentation → Native-first UI with shared Python backend
- Competition → Focus on unique aesthetic and superior decode accuracy
- Market size → Build for passionate amateur radio niche with professional quality

## Conclusion

This requirements document provides a roadmap for developing a sophisticated SSTV application that honors the technical depth of amateur radio while delivering a polished, native experience on each platform. The phased approach allows for iterative learning and platform-specific optimization while maintaining a consistent core vision.

The emphasis on native development ensures optimal performance and platform integration, while the shared Python DSP engine provides consistency across all implementations. The digital hi-fi aesthetic differentiates the application in a crowded market while appealing to the sophisticated tastes of amateur radio operators.

Success depends on rigorous attention to both technical excellence and user experience, with particular focus on the audio pipeline performance that forms the foundation of all SSTV operations.