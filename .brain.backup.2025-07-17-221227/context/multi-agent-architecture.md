# Multi-Agent Architecture - SSTV Project

## 🏗️ Architecture Overview

### Core Concept
**Universal Python Core + Platform-Specific Implementations**
- **Agent 1**: Python/SSTV expert maintains core engine (`core/python/`)
- **Agent 2**: Swift/iOS developer handles Apple platforms (`platforms/swift/`)
- **Agent 3**: .NET/C++ developer handles Windows (`platforms/windows/`)
- **Agent 4**: Linux/Qt developer handles Linux desktop (`platforms/linux/`)
- **Agent 5**: Web developer handles browser/Electron (`platforms/web/`)
- **Current**: Tauri implementation (`platforms/tauri/`) - Phase 4B complete

## 🔧 Integration Architecture

### Core Python Engine (`core/python/sstv_engine/`)
- **Universal SSTV decoder/encoder**: colaclanth/sstv and PySSTV integration
- **Cross-platform image enhancement**: PIL/Pillow processing pipeline
- **JSON-based IPC protocol**: Communication with platform layers
- **CLI interface**: Direct command-line usage and integration reference

### Platform Integration Methods

#### 1. Process Spawning (Recommended)
```bash
python core/python/sstv_engine/cli.py decode input.wav output.png --json
```

#### 2. Symlinked Core Directory
```bash
platforms/swift/core -> ../../core
platforms/tauri/core -> ../../core
platforms/windows/core -> ../../core
```

#### 3. JSON IPC Protocol
```json
{
  "method": "decode",
  "params": {
    "audioPath": "/path/to/audio.wav",
    "outputPath": "/path/to/output.png",
    "enhance": {"contrast": 1.3, "brightness": 1.1}
  }
}
```

## 🚀 Development Benefits

### Parallel Development
- **No Conflicts**: Each platform has isolated codebase
- **Specialized Expertise**: Platform-specific optimization
- **Shared Quality**: Core engine ensures consistent SSTV results
- **Clean Separation**: Platform UI/UX independent of core logic

### Code Reuse Strategy
- **Single Core Engine**: All platforms use same Python SSTV implementation
- **Multiple UIs**: Platform-optimized user interfaces
- **Consistent Results**: Reference-quality SSTV across all platforms
- **Easy Platform Addition**: New platforms don't affect existing ones

## 📁 Current Implementation Status

### ✅ Completed Platforms
- **Tauri (Agent Current)**: `platforms/tauri/` - Phase 4B complete with real-time functionality
- **Swift (Agent 2)**: `platforms/swift/` - Basic framework and core integration
- **Web (Agent 5)**: `platforms/web/` - Initial implementation skeleton

### 📋 Platform Skeletons
- **Windows (Agent 3)**: `platforms/windows/` - Directory structure created
- **Linux (Agent 4)**: `platforms/linux/` - Directory structure created

### 🔄 Reorganization Complete
- **Legacy Cleanup**: Removed obsolete directories (`scripts/`, `lib/`, `examples/`, etc.)
- **Core Migration**: All valuable code preserved and migrated to new structure
- **Symlink Setup**: Platform symlinks to core established
- **Multi-Agent Ready**: Architecture prepared for parallel development

## 🧪 Testing Strategy

### Core Engine Tests
```bash
cd core/python
python -m pytest tests/
python -m sstv_engine.cli decode --help
```

### Platform Integration Tests
- **Tauri**: `npm run tauri dev` - Test full UI integration
- **Swift**: `swift test` - Test core communication
- **Web**: `npm test` - Test JavaScript integration

### Reference Validation
- **MMSSTV Gold Standard**: Core engine must match reference images
- **Cross-platform Consistency**: All platforms produce identical results
- **Real-time Performance**: Audio processing without timing degradation

## 📦 Deployment Strategy

### Core Engine Distribution
- **Bundled Python**: Include Python dependencies with each platform
- **Virtual Environments**: Isolated dependency management
- **Universal CLI**: Command-line interface included in all distributions

### Platform-Specific Packaging
- **Tauri**: Cross-platform desktop app (current focus)
- **Swift**: Mac App Store / DMG distribution
- **Windows**: MSI installer / Microsoft Store
- **Linux**: AppImage / Flatpak / Snap packages
- **Web**: Electron cross-platform or pure web app

## 🔄 Communication Protocol

### Request Format
```json
{
  "id": "unique-request-id",
  "method": "decode|encode|enhance|getSupportedModes|checkDependencies",
  "params": {
    // Method-specific parameters
  }
}
```

### Response Format
```json
{
  "id": "unique-request-id",
  "result": {
    "success": true|false,
    "message": "Human-readable message",
    // Method-specific result data
  }
}
```

## 🎯 Development Workflow

### Core Engine Changes (Agent 1)
1. Modify `core/python/sstv_engine/`
2. Update IPC protocol if needed
3. Test with CLI: `python -m sstv_engine.cli`
4. All platforms automatically inherit updates via symlinks

### Platform-Specific Changes (Agents 2-5)
1. Work in respective `platforms/*/` directory
2. Use symlinked `core/` for testing
3. Platform changes isolated from others
4. Independent UI, integration, and packaging development

### Integration Testing
- **Core Agent**: Tests CLI with various inputs and edge cases
- **Platform Agents**: Test UI integration with core functionality
- **Cross-platform**: Verify consistent results across all implementations

## 🏆 Architecture Advantages

1. **Parallel Development**: Multiple agents work simultaneously without conflicts
2. **Code Reuse**: Single core engine, multiple optimized UIs
3. **Platform Optimization**: Each platform leverages native capabilities
4. **Maintainability**: Core logic changes propagate to all platforms automatically
5. **Scalability**: Easy to add new platforms or modify existing ones
6. **Quality Assurance**: Shared core ensures consistent SSTV quality universally