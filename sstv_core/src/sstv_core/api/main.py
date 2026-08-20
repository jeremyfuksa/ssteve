"""FastAPI application for SSTeVe SSTV engine.

Provides REST API and WebSocket endpoints for SSTV decode/transmit operations.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from sstv_core.api.app_channel import app_channel
from sstv_core.api.dsp_manager import dsp_manager
from sstv_core.api.session_manager import session_manager
from sstv_core.api.websocket_manager import websocket_manager

logger = logging.getLogger(__name__)

__version__ = "0.1.0"

_db_engine: Engine | None = None
_db_session_factory: sessionmaker[Session] | None = None
_file_library_watcher = None


# =============================================================================
# Application Lifecycle
# =============================================================================


def _ensure_database_initialized() -> None:
    global _db_engine, _db_session_factory

    if _db_session_factory is not None:
        return

    try:
        from sstv_core.database import init_database
    except ImportError:
        logger.warning("Database module not yet implemented - using in-memory storage")
        return

    db_path = os.environ.get("SSTVE_DB_PATH")
    logger.debug("Initializing database with path %s", db_path)
    engine, session_factory = init_database(db_path=db_path)
    _db_engine = engine
    _db_session_factory = session_factory
    logger.debug("Database initialized %s", session_factory)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifecycle.

    Startup:
    - Initialize database connection
    - Start session cleanup task

    Shutdown:
    - Stop the file library watcher
    - Stop active transmit/decode operations (unkeys the radio)
    - Clean up active sessions
    - Close database connections
    """
    logger.info("SSTeVe API starting up (version %s)", __version__)
    global _db_engine, _db_session_factory
    _ensure_database_initialized()
    try:
        from sstv_core.database import get_or_create_config
    except ImportError:
        logger.warning("Database module not yet implemented - using in-memory storage")
    else:
        if _db_session_factory is not None:
            with _db_session_factory() as session:
                get_or_create_config(session)

    # Pass session factory to DSP manager for database integration
    if _db_session_factory is not None:
        dsp_manager._db_session_factory = _db_session_factory
        logger.info("Database session factory connected to DSP manager")

    # Start background tasks
    await session_manager.start_cleanup_task()

    # Start file library watcher if database and watch path configured
    global _file_library_watcher
    if _db_session_factory is not None:
        # Env var overrides; otherwise use the configured library directory.
        watch_path = os.environ.get("SSTVE_IMAGE_LIBRARY_PATH")
        if not watch_path:
            from sstv_core.config.manager import ConfigManager

            with _db_session_factory() as session:
                watch_path = ConfigManager(session).get("image_save_directory") or None
        if watch_path:
            try:
                # Create watch path if it doesn't exist
                from pathlib import Path

                from sstv_core.filesystem.watcher import ImageLibraryWatcher
                watch_dir = Path(watch_path).expanduser()
                watch_dir.mkdir(parents=True, exist_ok=True)

                _file_library_watcher = ImageLibraryWatcher(
                    watch_path=watch_dir,
                    session_factory=_db_session_factory,
                    websocket_manager=websocket_manager,
                    debounce_delay=0.5,
                )
                _file_library_watcher.start()
                logger.info("Started file library watcher: %s", watch_dir)
            except Exception as e:
                logger.error("Failed to start file library watcher: %s", e, exc_info=True)
        else:
            logger.info(
                "File library watcher not started (no SSTVE_IMAGE_LIBRARY_PATH env var "
                "and image_save_directory is not configured)"
            )

    yield

    # Cleanup
    logger.info("SSTeVe API shutting down")
    if _file_library_watcher:
        _file_library_watcher.stop()
        logger.info("Stopped file library watcher")
    # Before the engine is disposed: stopping a session can write a final
    # record, and an orphaned transmit task can leave the radio keyed.
    await dsp_manager.shutdown()
    # The app channel's device poll and any monitored input stream are
    # background tasks holding real hardware; stop them too.
    await app_channel.shutdown()
    await session_manager.stop_cleanup_task()
    if _db_engine is not None:
        _db_engine.dispose()
        _db_engine = None
        _db_session_factory = None


def get_db_session() -> Iterator[Session]:
    """Dependency for providing a database session."""
    _ensure_database_initialized()
    if _db_session_factory is None:
        raise RuntimeError("Database not initialized")
    session = _db_session_factory()
    try:
        yield session
    finally:
        session.close()


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

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        """Redirect the bare root URL to the interactive API docs."""
        return RedirectResponse(url="/docs")

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
        import_routes,
        propagation,
        qso,
        smart_reply,
        transmit,
        websocket,
    )

    # Depends() captures its callable when each route is defined. Override the
    # placeholder callables rather than rebinding their module attributes.
    app.dependency_overrides[import_routes.get_db] = get_db_session
    app.dependency_overrides[smart_reply.get_db] = get_db_session
    app.dependency_overrides[qso.get_db] = get_db_session

    app.include_router(decode.router, prefix="/api/v1", tags=["Decode"])
    app.include_router(transmit.router, prefix="/api/v1", tags=["Transmit"])
    app.include_router(devices.router, prefix="/api/v1", tags=["Devices"])
    app.include_router(config.router, prefix="/api/v1", tags=["Config"])
    app.include_router(images.router, prefix="/api/v1", tags=["Images"])
    app.include_router(websocket.router, prefix="/api/v1", tags=["WebSocket"])
    app.include_router(import_routes.router, prefix="/api/v1", tags=["Import"])
    app.include_router(smart_reply.router, prefix="/api/v1", tags=["Smart Reply"])
    app.include_router(propagation.router, prefix="/api/v1", tags=["Propagation"])
    app.include_router(qso.router, prefix="/api/v1", tags=["QSO Logging"])

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
        # Not a dev server: auto-reload in the production console entry
        # restarted mid-transmission on any file change.
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    run_server()
