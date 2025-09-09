# SSTV Station - macOS Implementation

## Overview

Native macOS implementation of SSTV Station using SwiftUI and the shared Python SSTV engine. This implementation serves as the reference platform for the cross-platform design system.

## Architecture

### Technology Stack
- **Framework**: SwiftUI + AVFoundation
- **Python Integration**: Python.h embedded interpreter
- **Audio**: Core Audio (AVAudioEngine)
- **Target**: macOS 13.0+
- **Build System**: Xcode 15.0+

### Project Structure
```
SSTVStation/
├── SSTVStation.xcodeproj/     # Xcode project
├── SSTVStation/
│   ├── SSTVStationApp.swift   # App entry point
│   ├── ContentView.swift      # Main UI layout (720x480pt)
│   ├── Core/
│   │   ├── AudioManager.swift      # Core Audio integration
│   │   ├── SSTVProcessor.swift     # Main processing logic
│   │   └── PythonBridge.swift      # Python engine interface
│   ├── UI/                    # UI Components (to be added)
│   ├── Assets.xcassets        # App assets
│   ├── Info.plist            # App configuration
│   └── SSTVStation.entitlements # Sandbox permissions
└── README.md
```

## Design System Implementation

### Fixed Window Dimensions
- **Size**: 720x480 points (exact specification)
- **Layout**: 65% display area (468pt) + 35% controls (234pt)
- **Resizing**: Disabled to maintain consistent "rack unit" appearance
- **Background**: Brushed aluminum gradient texture

### UI Components

#### 1. VFD Display (Main Display Area)
- **Location**: Left column, primary display
- **States**: Spectrum analyzer, Progressive image rendering, Gallery, Settings
- **Styling**: VFD-style with scan lines, glowing text, authentic CRT persistence
- **Colors**: Configurable (Cyan/Amber/Green)

#### 2. Function Button Bank
- **Layout**: Four buttons - RECEIVE | TRANSMIT | GALLERY | SETTINGS
- **Styling**: Chunky buttons with LED indicators
- **States**: Active (pressed + bright LED), Inactive (raised + dim LED)
- **Animation**: Smooth state transitions

#### 3. Audio Level Meter
- **Type**: Segmented LED-style VU meter
- **Colors**: Green → Amber → Red progression
- **Ballistics**: Proper attack/decay timing
- **Real-time**: 60fps updates from audio input

#### 4. Mode Selector
- **Type**: Rotary knob with snap-to-position
- **Modes**: AUTO, Scottie S1/S2, Martin M1/M2, Robot 36
- **Manual Override**: Always available for traditional operators
- **Interaction**: Click-drag rotation with haptic feedback

## Audio System Integration

### Core Audio Pipeline
```swift
AVAudioEngine → AVAudioInputNode → Format Conversion → 
Shared Memory Buffer → Python DSP Engine → Results
```

### Audio Processing
- **Sample Rate**: 22.050 kHz (SSTV standard)
- **Channels**: Mono (stereo mixed to mono)
- **Buffer Size**: 1024 samples
- **Latency Target**: <100ms end-to-end
- **Professional Audio**: Full support for USB/Thunderbolt interfaces

### Device Support
- Built-in microphone
- USB audio interfaces (Focusrite, PreSonus, etc.)
- Virtual Audio Cables (Soundflower, BlackHole)
- Bluetooth audio devices
- Professional ham radio interfaces

## Python Bridge Integration

### Shared Memory Architecture
- **Buffer Size**: 1MB circular buffer (mmap)
- **Communication**: MessagePack serialization
- **Process Management**: Embedded Python interpreter (persistent)
- **Error Recovery**: Watchdog monitoring with automatic restart

### Python Engine Interface
```swift
// Audio processing
func processAudioStream(_ audioData: Data) async throws -> SSTVProcessingResult

// File-based processing  
func decodeAudioFile(_ filePath: String) async throws -> SSTVProcessingResult
func encodeImage(_ imagePath: String, mode: String) async throws -> SSTVProcessingResult

// Configuration
func getSupportedModes() async throws -> [String]
```

### Result Types
- **Spectrum Data**: Real-time FFT for visualization
- **VIS Detection**: Automatic mode detection from signal
- **Line Data**: Progressive image rendering updates
- **Complete Image**: Final decoded image data
- **Error States**: Processing failures with recovery guidance

## Cultural Bridge Implementation

### Traditional Operator Support
- **Direct Control**: Manual mode selection always overrides auto-detection
- **Amateur Radio Terminology**: "QRV", "QRT", "PSE K" in status messages
- **Hardware-like Operation**: Physical-feeling controls, immediate response
- **Reliable Behavior**: Predictable operation patterns

### Modern Operator Features
- **Rich Data Display**: Technical metrics available on demand
- **Integration Ready**: API endpoints for external tool integration
- **Advanced Automation**: Optional sophisticated processing modes
- **Performance Metrics**: SNR, decoder confidence, signal analysis

### Adaptive UI Complexity
- **Base Layer**: Clean, simple operation (traditional users)
- **Detail Layer**: Technical overlays available (modern users)
- **Expert Layer**: Advanced controls for power users

## Development Workflow

### Building the Project
```bash
# Open in Xcode
open platforms/macos/SSTVStation/SSTVStation.xcodeproj

# Or build from command line
xcodebuild -project SSTVStation.xcodeproj -scheme SSTVStation -configuration Debug

# For release builds
xcodebuild -project SSTVStation.xcodeproj -scheme SSTVStation -configuration Release archive
```

### Python Engine Integration
The app automatically links to the shared Python SSTV engine:
```
../../core/python/sstv_engine/  → Embedded in app bundle
```

### Testing
```bash
# Run from Xcode for development
# Audio input testing requires physical microphone access

# Automated testing
xcodebuild test -project SSTVStation.xcodeproj -scheme SSTVStation
```

## System Requirements

### macOS Version Support
- **Minimum**: macOS 13.0 (Ventura)
- **Recommended**: macOS 14.0+ (Sonoma+)
- **Architecture**: Apple Silicon + Intel universal binary

### Hardware Requirements
- **RAM**: 4GB minimum, 8GB recommended
- **Storage**: 100MB for app + Python dependencies
- **Audio**: Any Core Audio compatible device
- **CPU**: Dual-core minimum for real-time processing

### Permissions Required
- **Microphone Access**: Required for audio input
- **File System Access**: User-selected files (sandbox-compliant)
- **Network Access**: Optional for future features (spotting, logging)

## Installation & Distribution

### Development Installation
1. Clone repository
2. Open Xcode project
3. Build and run (automatically handles Python dependencies)

### Production Distribution
- **App Store**: Sandboxed build with embedded Python
- **Direct Download**: Signed and notarized .dmg
- **Homebrew**: Formula for command-line users

### Code Signing
```bash
# Development
codesign --deep --force --verify --verbose --sign "Developer ID" SSTVStation.app

# Distribution  
codesign --deep --force --verify --verbose --sign "Developer ID Application" SSTVStation.app
xcrun notarytool submit SSTVStation.dmg --keychain-profile "notary"
```

## Performance Optimization

### Audio Processing
- **Core Audio Optimization**: Minimal latency audio pipeline
- **Python Integration**: Shared memory avoids copy overhead
- **FFT Processing**: Accelerate framework for spectrum analysis
- **Memory Management**: Circular buffers prevent allocation overhead

### UI Rendering
- **Metal Acceleration**: GPU-accelerated VFD display rendering
- **SwiftUI Optimization**: Efficient state management and updates
- **Animation Performance**: 60fps target with battery efficiency

### Python Performance
- **NumPy Optimization**: Vectorized operations for DSP
- **Memory Efficiency**: Pre-allocated buffers for audio processing
- **Process Management**: Persistent interpreter eliminates startup costs

## Future Enhancements

### Phase 1 Additions (Near-term)
- **TNC Integration**: Serial port communication for packet radio
- **SDR Integration**: Direct integration with SDR software
- **Image Enhancement**: Real-time processing with PIL/OpenCV
- **Gallery Management**: Local image database and organization

### Phase 2 Extensions (Medium-term)
- **Network SDR**: KiwiSDR and WebSDR integration
- **Contest Integration**: Automatic logging and spotting
- **Advanced DSP**: Noise reduction and signal enhancement
- **Plugin Architecture**: Extension points for custom processing

### Phase 3 Advanced (Long-term)
- **Machine Learning**: AI-powered signal detection and enhancement
- **Multi-Protocol**: Support for other digital modes
- **Cloud Integration**: Synchronized settings and images
- **Professional Features**: Rack mount hardware integration

## Known Limitations

### Current Implementation
- **Basic Python Bridge**: Minimal error handling and recovery
- **Simple UI Components**: Placeholder implementations
- **Limited Audio Processing**: Basic spectrum analysis only
- **No Hardware Integration**: TNC/SDR support not yet implemented

### Platform Limitations
- **Sandbox Restrictions**: Limited file system and hardware access
- **Audio Latency**: Core Audio limitations on some hardware
- **Python Dependencies**: Complex deployment for scientific stack
- **Memory Usage**: Python interpreter overhead

## Contributing

### Code Style
- **Swift**: Follow Apple's Swift style guide
- **SwiftUI**: Prefer declarative patterns, minimal state
- **Python Integration**: Error handling for all Python calls
- **Performance**: Profile before optimizing, measure improvements

### Testing Requirements
- **Unit Tests**: All core functionality
- **Integration Tests**: Python bridge operation
- **UI Tests**: Critical user workflows
- **Performance Tests**: Audio latency and throughput
- **Device Tests**: Multiple audio interfaces

### Review Process
- **Design Consistency**: Must match cross-platform specifications
- **Cultural Bridge**: Validate with both traditional and modern users
- **Performance**: Audio processing within latency requirements
- **Accessibility**: VoiceOver and keyboard navigation support

This implementation provides the foundation for a premium SSTV application that honors amateur radio traditions while embracing modern software capabilities.