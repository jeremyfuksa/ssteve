"""FastAPI application for SSTeVe SSTV engine.

Provides REST API and WebSocket endpoints for SSTV decode/transmit operations.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

__version__ = "0.1.0"


# =============================================================================
# Application Lifecycle
# =============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifecycle.

    Startup:
    - Initialize database connection
    - Start session cleanup task

    Shutdown:
    - Clean up active sessions
    - Close database connections
    """
    logger.info("SSTeVe API starting up (version %s)", __version__)

    # Initialize database (if available)
    try:
        from sstv_core.database import init_database, get_or_create_config
        init_database()
        get_or_create_config()
    except ImportError:
        logger.warning("Database module not yet implemented - using in-memory storage")

    # Start background tasks
    from sstv_core.api.session_manager import session_manager
    await session_manager.start_cleanup_task()

    yield

    # Cleanup
    logger.info("SSTeVe API shutting down")
    await session_manager.stop_cleanup_task()


# =============================================================================
# Application Factory
# =============================================================================


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    app = FastAPI(
        title="SSTeVe API",
        description="SSTV (Slow-Scan Television) encode/decode engine",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS middleware - allow localhost origins for development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
            "tauri://localhost",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception handlers
    configure_exception_handlers(app)

    # Register routes
    register_routes(app)

    return app


# =============================================================================
# Exception Handlers
# =============================================================================


def configure_exception_handlers(app: FastAPI) -> None:
    """Configure custom exception handlers."""

    @app.exception_handler(ValueError)
    async def value_error_handler(
        request: Request,
        exc: ValueError,
    ) -> JSONResponse:
        """Handle validation errors."""
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "VALIDATION_ERROR",
                "message": str(exc),
                "recoverable": True,
            },
        )

    @app.exception_handler(FileNotFoundError)
    async def file_not_found_handler(
        request: Request,
        exc: FileNotFoundError,
    ) -> JSONResponse:
        """Handle file not found errors."""
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": "FILE_NOT_FOUND",
                "message": str(exc),
                "recoverable": True,
            },
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """Handle unexpected exceptions."""
        logger.exception("Unexpected error occurred")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "INTERNAL_ERROR",
                "message": "Something went wrong - check the logs for details",
                "recoverable": False,
            },
        )


# =============================================================================
# Route Registration
# =============================================================================


def register_routes(app: FastAPI) -> None:
    """Register all API routes."""

    # Health check
    @app.get("/api/v1/health", tags=["Health"])
    async def health_check() -> dict[str, str]:
        """Health check endpoint.

        Returns:
            Status and version information.
        """
        return {
            "status": "ok",
            "version": __version__,
        }

    # Import and register route modules
    from sstv_core.api.routes import (
        config,
        decode,
        devices,
        images,
        transmit,
        websocket,
    )

    app.include_router(decode.router, prefix="/api/v1", tags=["Decode"])
    app.include_router(transmit.router, prefix="/api/v1", tags=["Transmit"])
    app.include_router(devices.router, prefix="/api/v1", tags=["Devices"])
    app.include_router(config.router, prefix="/api/v1", tags=["Config"])
    app.include_router(images.router, prefix="/api/v1", tags=["Images"])
    app.include_router(websocket.router, prefix="/api/v1", tags=["WebSocket"])


# =============================================================================
# Application Instance
# =============================================================================

app = create_app()


# =============================================================================
# CLI Entry Point
# =============================================================================


def run_server() -> None:
    """Run the API server (CLI entry point).

    Configured in pyproject.toml as 'sstv-server' command.
    """
    import uvicorn

    uvicorn.run(
        "sstv_core.api.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    run_server()
