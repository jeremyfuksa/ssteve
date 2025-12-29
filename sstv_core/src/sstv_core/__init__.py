"""SSTeVe SSTV Core Engine.

A headless Python core engine for SSTV (Slow-Scan Television) encoding,
decoding, and real-time signal processing. Exposes REST API and WebSocket
interfaces for UI integration.

Architecture:
- 100% headless, UI-agnostic design
- FastAPI REST endpoints for stateless operations
- WebSocket for real-time updates (scanlines, VIS detection)
- SQLite for metadata storage (images stored as files)
- PTT control via Serial (RTS/DTR) or VOX

See: docs/backend-spec.md for full specification
"""

__version__ = "0.1.0"
__author__ = "SSTeVe Contributors"
