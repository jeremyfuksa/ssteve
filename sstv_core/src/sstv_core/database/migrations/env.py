"""Alembic migration environment configuration.

This configures Alembic to use SSTeVe's database models for migrations.
The database URL defaults to ~/.ssteve/ssteve.db but can be overridden via:
- Environment variable: SSTEVE_DATABASE_URL
- Command line: alembic -x db_path=/custom/path upgrade head
"""

from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import our models so Alembic can detect schema changes
from sstv_core.database.models import Base, get_default_db_path

# Alembic Config object - provides access to .ini file values
config = context.config

# Setup Python logging from the config file
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target_metadata for autogenerate support
target_metadata = Base.metadata


def get_database_url() -> str:
    """Get the database URL, with fallback to default path.

    Priority:
    1. -x db_path=... command line argument
    2. SSTEVE_DATABASE_URL environment variable
    3. Default: ~/.ssteve/ssteve.db
    """
    # Check for command-line override
    cmd_db_path = context.get_x_argument(as_dictionary=True).get("db_path")
    if cmd_db_path:
        return f"sqlite:///{cmd_db_path}"

    # Check for environment variable
    env_url = os.environ.get("SSTEVE_DATABASE_URL")
    if env_url:
        return env_url

    # Default to ~/.ssteve/ssteve.db
    db_path = get_default_db_path()
    return f"sqlite:///{db_path}"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine,
    which means we don't need a DBAPI to be available.

    Calls to context.execute() emit the given string to the script output.
    """
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # Required for SQLite ALTER TABLE operations
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we create an Engine and associate a connection
    with the context.
    """
    # Build configuration with our URL
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # Required for SQLite ALTER TABLE operations
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
