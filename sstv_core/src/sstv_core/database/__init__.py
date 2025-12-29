"""SQLAlchemy models and database operations.

This module provides:
- ORM models for SSTV images, QSOs, and configuration
- Database connection utilities
- Session management helpers

Usage:
    from sstv_core.database import (
        init_database,
        SSTVImage,
        QSO,
        Configuration,
        get_or_create_config,
    )

    engine, SessionFactory = init_database()
    with SessionFactory() as session:
        config = get_or_create_config(session)
        images = session.query(SSTVImage).all()
"""

from sstv_core.database.models import (
    Base,
    Configuration,
    QSO,
    QSOImage,
    SSTVImage,
    create_db_engine,
    create_session_factory,
    get_database_url,
    get_default_db_path,
    get_or_create_config,
    init_database,
)

__all__ = [
    # Base class
    "Base",
    # Models
    "SSTVImage",
    "QSO",
    "QSOImage",
    "Configuration",
    # Utilities
    "get_default_db_path",
    "get_database_url",
    "create_db_engine",
    "create_session_factory",
    "init_database",
    "get_or_create_config",
]
