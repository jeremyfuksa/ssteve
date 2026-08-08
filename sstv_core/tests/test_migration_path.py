"""Migration-path regressions from the 2026-08-07 audit.

The app initializes its schema via create_all and never stamped
alembic_version, so `alembic upgrade head` on any real install died on
"table configurations already exists" -- there was no upgrade path for
databases the app itself created.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from sstv_core.database.models import init_database

MIGRATIONS_DIR = (
    Path(__file__).resolve().parent.parent
    / "src" / "sstv_core" / "database" / "migrations"
)


def _current_head() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    head = ScriptDirectory.from_config(config).get_current_head()
    assert head is not None
    return head


def test_init_database_stamps_alembic_head(tmp_path):
    engine, _ = init_database(db_path=tmp_path / "app.db")
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).fetchall()
    assert rows == [(_current_head(),)]


def test_upgrade_head_is_a_noop_on_app_created_database(tmp_path, monkeypatch):
    """The exact failure the audit reproduced: upgrade after create_all."""
    from alembic import command
    from alembic.config import Config

    db_path = tmp_path / "app.db"
    init_database(db_path=db_path)

    # env.py resolves its own URL (x-arg > SSTEVE_DATABASE_URL > ~/.ssteve
    # default) and ignores sqlalchemy.url -- the env var is the only safe
    # override here.
    monkeypatch.setenv("SSTEVE_DATABASE_URL", f"sqlite:///{db_path}")
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    # Previously: OperationalError, "table configurations already exists".
    command.upgrade(config, "head")
