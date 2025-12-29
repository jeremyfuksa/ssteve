# SSTeVe Core Engine

Headless Python backend for SSTV encoding, decoding, and real-time signal processing.

## Quick Start

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest
```

## System Dependencies

The audio I/O library (`sounddevice`) requires PortAudio system libraries:

**Debian/Ubuntu/Raspberry Pi:**
```bash
sudo apt-get install libportaudio2 portaudio19-dev
```

**macOS:**
```bash
brew install portaudio
```

**Windows:**
PortAudio is bundled with the sounddevice wheel - no extra steps needed.

## Project Structure

```
sstv_core/
  src/
    sstv_core/
      api/           # FastAPI REST and WebSocket endpoints
      database/      # SQLAlchemy models and migrations
      engine/        # SSTV DSP - encoding, decoding, PTT
  tests/             # pytest test suite
  requirements.txt   # Pip-installable dependencies
  pyproject.toml     # Modern Python packaging config
```

## Architecture

This is a **100% headless** engine with no UI dependencies:

- **REST API:** Stateless operations (device enumeration, config, image retrieval)
- **WebSocket:** Real-time updates (scanline progress, VIS detection, TX status)
- **SQLite:** Metadata storage only (images stored as files on disk)
- **PTT:** Serial (RTS/DTR via pyserial) or VOX (silence preamble)

See `/docs/backend-spec.md` for the full specification.

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| sounddevice | >=0.4.6 | Audio I/O |
| numpy | >=1.24 | Signal processing |
| scipy | >=1.10 | Filters, FFT |
| Pillow | >=10.0 | Image processing |
| sqlalchemy | >=2.0 | Database ORM |
| alembic | >=1.12 | Migrations |
| fastapi | >=0.104 | REST API |
| uvicorn | >=0.24 | ASGI server |
| websockets | >=12.0 | Live updates |
| pydantic | >=2.0 | Validation |
| pyserial | >=3.5 | PTT control |
| watchdog | >=3.0 | File monitoring |
