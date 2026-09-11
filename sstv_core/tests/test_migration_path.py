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


def _columns(engine, table: str) -> set[str]:
    from sqlalchemy import inspect

    return {c["name"] for c in inspect(engine).get_columns(table)}


def test_existing_install_gains_new_columns_on_open(tmp_path):
    """An install from before a migration must be upgraded when it opens.

    create_all never adds a column to a table that exists, and the stamp
    only writes a version where none exists -- so before #69 an old
    database kept its old tables forever and failed the first query that
    selected a new column. Reproduced here by downgrading a fresh database
    to the revision every pre-provenance install is stamped at.
    """
    from alembic import command
    from alembic.config import Config

    from sstv_core.database.models import QSO

    db_path = tmp_path / "old.db"
    engine, _ = init_database(db_path=db_path)
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "2026011601")
        connection.execute(
            text(
                "INSERT INTO qsos (start_time, mode, callsign, is_sent) "
                "VALUES ('2026-08-01 12:00:00', 'ScottieS1', 'KG5JJ', 0)"
            )
        )
    assert "record_type" not in _columns(engine, "qsos")
    engine.dispose()

    engine, session_factory = init_database(db_path=db_path)

    assert {"source", "receiver", "heard_at"} <= _columns(engine, "sstv_images")
    assert "record_type" in _columns(engine, "qsos")
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert version == _current_head()
    with session_factory() as session:
        # A contact logged before record types existed stays a contact.
        assert [q.record_type for q in session.query(QSO).all()] == ["qso"]
