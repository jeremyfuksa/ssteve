# Agent Guide for SSTeVe Codebase

This file provides build commands, code style guidelines, and conventions for agentic coding agents working on this repository.

## Build & Test Commands

### Python Core Engine (sstv_core/)

```bash
# Activate virtual environment
cd sstv_core
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run all tests
pytest

# Run tests with verbose output
pytest -v

# Run specific test file
pytest tests/api/test_routes_decode.py

# Run single test with name matching
pytest -k "test_list_audio_devices"
pytest -v -k "test_list_audio_devices"  # Verbose for single test

# Run tests in a directory
pytest tests/api/

# Run with specific markers (if defined)
pytest -m "not slow"

# Show available tests
pytest --collect-only

# Run linting (dev dependencies must be installed)
pip install ruff mypy  # If not already in dev
ruff check src/
mypy src/

# Run specific file through linter
ruff check src/sstv_core/decode/vis_detector.py

# Type check specific module
mypy src/sstv_core/api/main.py

# Format code (if black is installed)
black src/

# Install in development mode (editable)
pip install -e .
```

### Desktop Application (ssteve-ui--figma/)

```bash
cd ssteve-ui--figma

# Install dependencies
npm install

# Development mode
npm run dev

# Production build
npm run build

# Run tests
npm run test  # If configured

# Type checking
npx tsc --noEmit
```

## Code Style Guidelines

### Python Code

#### File Headers and Docstrings

```python
"""Module docstring.

Brief description of what this module does and how it fits in SSTeVe.
Mention key dependencies and data flow.
"""

from __future__ import annotations  # Always first import
```

#### Import Order (Groups: stdlib, third-party, local)

```python
# Standard library
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING
from contextlib import asynccontextmanager

# Third-party dependencies
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

# Local imports (from sstv_core)
from sstv_core.api.models import DecodeStartRequest, DecodeStatusResponse
from sstv_core.decode.vis_detector import GoertzelFilter

# TYPE_CHECKING imports (for type hints only)
if TYPE_CHECKING:
    from sqlalchemy.engine import Engine as EngineType
```

#### Type Annotations

```python
# Use type hints for all function parameters and return values
def decode_scanline(self, samples: np.ndarray, line_number: int) -> ScanlineData:
    ...

# Use Optional[T] for nullable types
def get_decode_session(self, session_id: UUID) -> Optional[DecodeSession]:
    ...

# Use Union or | for multiple types
mode: SSTVMode | None = None

# Use TYPE_CHECKING for forward references
if TYPE_CHECKING:
    from sqlalchemy.engine import Engine
```

#### Naming Conventions

- **Classes:** `PascalCase` (e.g., `DecodeSession`, `PTTController`)
- **Functions/Variables:** `snake_case` (e.g., `decode_scanline`, `audio_samples`)
- **Constants:** `UPPER_SNAKE_CASE` (e.g., `DETECTION_THRESHOLD`, `DEFAULT_SAMPLE_RATE`)
- **Private methods:** `_leading_underscore` (e.g., `_detect_frequency`)
- **Protected methods:** `_leading_underscore` (internal use)
- **Enums:** `PascalCase` (e.g., `SSTVMode`, `PTTMethod`)

#### Logging

```python
import logging

logger = logging.getLogger(__name__)

# Use appropriate levels
logger.debug("Detailed diagnostic info")
logger.info("Normal operation message")
logger.warning("Unexpected but recoverable situation")
logger.error("Error occurred: %s", str(e), exc_info=True)
logger.critical("Critical failure")
```

#### Error Handling

```python
# API routes - raise HTTPException with structured errors
from fastapi import HTTPException, status

raise HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail={
        "error": "SESSION_NOT_FOUND",
        "message": f"Can't find decode session {session_id}",
        "suggested_action": "Check session ID and try again",
    },
)

# Custom exceptions for business logic
class PTTError(Exception):
    """Raised when PTT operations fail."""
    pass

try:
    ...
except PTTError as e:
    logger.error("PTT operation failed: %s", e)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={"error": "PTT_OPERATION_FAILED", "message": str(e)},
    ) from e
```

#### Async Code

```python
# Use async/await consistently
async def start_decode(self, request: DecodeStartRequest) -> DecodeStartResponse:
    ...

# Use async context managers
@asynccontextmanager
async def get_db_session():
    async with Session() as session:
        yield session
```

#### Database Models

```python
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Boolean, Integer, String, Float

class SSTVImage(Base):
    """SSTV image metadata.

    Images are stored as files on disk (filepath reference).
    This table stores metadata for search, filtering, and display.

    Note: rx_quality_score is 0.0-1.0 representing signal quality
    """
    __tablename__ = "sstv_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # ... more columns
```

#### API Models (Pydantic)

```python
from pydantic import BaseModel, Field, field_validator

class DecodeStartRequest(BaseModel):
    """Request model for starting decode session."""

    device_id: str = Field(
        ...,
        description="Audio input device ID",
        examples=["0", "1"],
    )
    mode: Optional[SSTVMode] = Field(
        default=None,
        description="SSTV mode (None for auto-detect)",
    )

    @field_validator('callsign', mode='before')
    @classmethod
    def validate_callsign(cls, v: Optional[str]) -> Optional[str]:
        if v and len(v) > 12:
            raise ValueError("Callsign too long (max 12 chars)")
        return v.upper() if v else v
```

#### Tests

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

class TestExample:
    """Test class docstring."""

    @pytest.fixture
    def mock_audio_stream():
        """Create mock audio stream fixture."""
        mock = MagicMock()
        mock.start = Mock()
        mock.stop = Mock()
        return mock

    def test_something_specific(self, mock_audio_stream):
        """Test description explaining what's being verified."""
        # Arrange
        expected = 42

        # Act
        result = mock_audio_stream.calculate()

        # Assert
        assert result == expected, f"Expected {expected}, got {result}"
```

#### Configuration Management

```python
# Singleton pattern for ConfigManager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

class ConfigManager:
    """Thread-safe configuration manager using SQLAlchemy."""

    def __init__(self):
        self._lock = threading.RLock()

    def get_setting(self, session: Session, key: str):
        """Get configuration value."""
        with self._lock:
            # Thread-safe access
            ...
```

#### Signal Processing

```python
# NumPy array conventions
# Use explicit dtype for numeric arrays
samples: np.ndarray = np.zeros(num_samples, dtype=np.float32)

# Document frequency domain operations
# 1500 Hz = 1.5 kHz = 1500.0 (explicit float)
target_freq: float = 1500.0

# Avoid magic numbers - define as constants
SAMPLE_RATE = 48000
BIT_DURATION_MS = 22
BIT_SAMPLES = SAMPLE_RATE * BIT_DURATION_MS // 1000
```

## Important Notes

### Testing in CI

- Audio hardware is mocked in `tests/conftest.py`
- Tests use in-memory SQLite databases
- Run single test with `pytest -k "test_name_pattern"`

### Architecture Separation

- **Never call audio I/O directly from UI** - always use API/WebSocket
- **Business logic stays in Python core** - UI is a thin client
- **API contract** defined in `docs/app-spec.md`

### Code Quality

- **Target Python version:** 3.10+
- **Type checking:** Use mypy (dev dependency)
- **Linting:** Use ruff (dev dependency)
- **Test coverage:** Aim for 60%+ before beta

### Common Pitfalls

1. **Missing imports:** Always test imports after editing
2. **Type mismatches:** Check SQLAlchemy vs Pydantic type annotations
3. **Async blocking:** Never block in async functions
4. **Database sessions:** Always use context managers for sessions
5. **Mocking:** Use `conftest.py` patterns for new test fixtures

### Project Structure

```
sstv_core/
├── src/sstv_core/
│   ├── api/          # FastAPI routes and models
│   ├── audio/         # Audio I/O and PTT control
│   ├── config/        # Configuration management
│   ├── database/      # SQLAlchemy models
│   ├── decode/        # SSTV decoding (VIS, sync, scanlines)
│   ├── encode/        # SSTV encoding (image to audio)
│   ├── filesystem/     # File watcher and importers
│   └── smart_features/ # AI/auto-detection features
├── tests/             # Pytest test suite
│   └── conftest.py    # Test fixtures and mocks
└── requirements.txt    # Python dependencies
```

### Reference Assets

Reference SSTV audio and images are in `sstv_core/tests/reference/`:
- Use these for integration testing
- Validate decode output against reference images
- File names indicate expected mode (e.g., `scottie_s1_bear_je3hht.wav`)
