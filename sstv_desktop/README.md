# SSTeVe Desktop

Tauri/React desktop application shell for SSTeVe.

## Status

This directory is a placeholder for the desktop application build configuration.
The actual UI components are currently in `/ssteve-ui--figma/`.

## Architecture

The desktop app is a thin shell that:
1. Bundles the SSTeVe Core Engine (Python)
2. Spawns the core as a subprocess on startup
3. Communicates via REST API and WebSocket
4. Provides native OS integration (notifications, tray icons, file dialogs)

See `/docs/backend-spec.md` Section 1.3 for the desktop UI stack specification.

## Build Requirements

- Node.js 18+
- Rust (for Tauri)
- Python 3.10+ (bundled with app)

## Development

Setup instructions will be added when the desktop build pipeline is configured.
