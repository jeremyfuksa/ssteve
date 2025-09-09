# Tauri Architecture Context

## Framework Overview
- **Version**: Tauri v2
- **Backend**: Rust with async/await patterns
- **Frontend**: Vanilla JavaScript (no framework)
- **Communication**: Tauri commands for backend calls

## Key Directories
- **Rust Backend**: `platforms/tauri/src-tauri/src/main.rs`
- **Frontend**: `platforms/tauri/src/`
- **Build Config**: `platforms/tauri/src-tauri/tauri.conf.json`

## Command Pattern
```rust
#[tauri::command]
async fn command_name(param: String) -> Result<ReturnType, String> {
    // Implementation
}
```

## Frontend Integration
```javascript
import { invoke } from '@tauri-apps/api/core';
const result = await invoke('command_name', { param: value });
```

## Audio State Management
- **Mute/Unmute**: Global audio state with passthrough
- **Device Selection**: Audio input device management
- **Real-time Capture**: CPAL-based threaded audio capture

## Build Process
1. `npm run build` - Update frontend dist
2. `npm run tauri dev` - Launch with fresh UI
3. **Critical**: Build before dev to avoid stale frontend cache

## Performance Patterns
- **Non-blocking**: Async commands for long operations
- **File-based**: Audio processing via temporary files
- **Progress Updates**: Event system for status feedback