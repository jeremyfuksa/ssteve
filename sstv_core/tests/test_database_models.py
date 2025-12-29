"""Unit tests for database models and schema.

These tests verify:
- Table creation with correct columns and types
- Index existence and naming (per backend-spec.md Section 2.1)
- Foreign key relationships (QSO <-> Image via qso_images)
- Configuration singleton constraint enforcement
- Model relationships and cascading deletes
"""

from __future__ import annotations

import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Generator

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sstv_core.database import (
    Base,
    Configuration,
    QSO,
    QSOImage,
    SSTVImage,
    create_db_engine,
    create_session_factory,
    get_or_create_config,
    init_database,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_db_path() -> Generator[Path, None, None]:
    """Create a temporary database file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def db_session(temp_db_path: Path) -> Generator[Session, None, None]:
    """Create a database session with all tables initialized."""
    engine, session_factory = init_database(temp_db_path)
    session = session_factory()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def db_engine(temp_db_path: Path):
    """Create a database engine for schema inspection."""
    engine = create_db_engine(temp_db_path)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


# =============================================================================
# Table Creation Tests
# =============================================================================


class TestTableCreation:
    """Test that all tables are created with correct structure."""

    def test_all_tables_exist(self, db_engine) -> None:
        """Verify all required tables are created."""
        inspector = inspect(db_engine)
        table_names = set(inspector.get_table_names())

        required_tables = {"sstv_images", "qsos", "qso_images", "configurations"}
        assert required_tables.issubset(
            table_names
        ), f"Missing tables: {required_tables - table_names}"

    def test_sstv_images_columns(self, db_engine) -> None:
        """Verify sstv_images table has all required columns."""
        inspector = inspect(db_engine)
        columns = {col["name"] for col in inspector.get_columns("sstv_images")}

        required_columns = {
            "id",
            "filename",
            "filepath",
            "timestamp",
            "mode",
            "callsign",
            "operator_name",
            "frequency_hz",
            "rx_quality_score",
            "comments",
            "is_received",
            "raw_audio_filepath",
            "ai_caption",
        }
        assert required_columns.issubset(
            columns
        ), f"Missing columns in sstv_images: {required_columns - columns}"

    def test_qsos_columns(self, db_engine) -> None:
        """Verify qsos table has all required columns."""
        inspector = inspect(db_engine)
        columns = {col["name"] for col in inspector.get_columns("qsos")}

        required_columns = {
            "id",
            "start_time",
            "end_time",
            "mode",
            "callsign",
            "frequency_hz",
            "report",
            "comments",
            "is_sent",
        }
        assert required_columns.issubset(
            columns
        ), f"Missing columns in qsos: {required_columns - columns}"

    def test_qso_images_columns(self, db_engine) -> None:
        """Verify qso_images join table has correct columns."""
        inspector = inspect(db_engine)
        columns = {col["name"] for col in inspector.get_columns("qso_images")}

        assert columns == {"qso_id", "image_id"}, f"Unexpected columns in qso_images: {columns}"

    def test_configurations_columns(self, db_engine) -> None:
        """Verify configurations table has all required columns."""
        inspector = inspect(db_engine)
        columns = {col["name"] for col in inspector.get_columns("configurations")}

        required_columns = {
            "id",
            "audio_input_device_id",
            "audio_output_device_id",
            "default_tx_mode",
            "image_save_directory",
            "enable_auto_save",
            "ptt_method",
            "ptt_serial_port",
            "ptt_serial_baud",
            "ptt_serial_signal",
            "ptt_pre_delay_ms",
            "ptt_post_delay_ms",
            "vox_preamble_ms",
            "enable_stereo_guidance",
            "pilot_tone_hz",
            "enable_ai_captions",
            "enable_verbose_cli",
            "theme",
            "advanced_settings_json",
        }
        assert required_columns.issubset(
            columns
        ), f"Missing columns in configurations: {required_columns - columns}"


# =============================================================================
# Index Tests
# =============================================================================


class TestIndexes:
    """Test that all required indexes exist per backend-spec.md Section 2.1."""

    def test_idx_images_timestamp_exists(self, db_engine) -> None:
        """Verify idx_images_timestamp index exists on sstv_images."""
        inspector = inspect(db_engine)
        indexes = {idx["name"] for idx in inspector.get_indexes("sstv_images")}
        assert "idx_images_timestamp" in indexes, "Missing idx_images_timestamp index"

    def test_idx_images_mode_exists(self, db_engine) -> None:
        """Verify idx_images_mode index exists on sstv_images."""
        inspector = inspect(db_engine)
        indexes = {idx["name"] for idx in inspector.get_indexes("sstv_images")}
        assert "idx_images_mode" in indexes, "Missing idx_images_mode index"

    def test_idx_images_callsign_exists(self, db_engine) -> None:
        """Verify idx_images_callsign index exists on sstv_images."""
        inspector = inspect(db_engine)
        indexes = {idx["name"] for idx in inspector.get_indexes("sstv_images")}
        assert "idx_images_callsign" in indexes, "Missing idx_images_callsign index"

    def test_idx_qsos_start_exists(self, db_engine) -> None:
        """Verify idx_qsos_start index exists on qsos."""
        inspector = inspect(db_engine)
        indexes = {idx["name"] for idx in inspector.get_indexes("qsos")}
        assert "idx_qsos_start" in indexes, "Missing idx_qsos_start index"

    def test_index_columns_correct(self, db_engine) -> None:
        """Verify indexes are on correct columns."""
        inspector = inspect(db_engine)

        # Check sstv_images indexes
        img_indexes = {idx["name"]: idx["column_names"] for idx in inspector.get_indexes("sstv_images")}
        assert img_indexes.get("idx_images_timestamp") == ["timestamp"]
        assert img_indexes.get("idx_images_mode") == ["mode"]
        assert img_indexes.get("idx_images_callsign") == ["callsign"]

        # Check qsos index
        qso_indexes = {idx["name"]: idx["column_names"] for idx in inspector.get_indexes("qsos")}
        assert qso_indexes.get("idx_qsos_start") == ["start_time"]


# =============================================================================
# Constraint Tests
# =============================================================================


class TestConstraints:
    """Test database constraints (unique, foreign key, check)."""

    def test_filepath_unique_constraint(self, db_session: Session) -> None:
        """Verify filepath uniqueness is enforced on sstv_images."""
        image1 = SSTVImage(
            filename="test.png",
            filepath="/path/to/image.png",
            mode="ScottieS1",
        )
        db_session.add(image1)
        db_session.commit()

        # Attempt to insert duplicate filepath
        image2 = SSTVImage(
            filename="test2.png",
            filepath="/path/to/image.png",  # Same filepath
            mode="MartinM1",
        )
        db_session.add(image2)
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_configuration_singleton_constraint(self, db_session: Session) -> None:
        """Verify only one configuration row can exist (id=1)."""
        # Create first config (should work)
        config1 = Configuration(id=1)
        db_session.add(config1)
        db_session.commit()

        # Attempt to create second config with different id
        config2 = Configuration(id=2)
        db_session.add(config2)
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_configuration_singleton_via_helper(self, db_session: Session) -> None:
        """Verify get_or_create_config enforces singleton pattern."""
        # First call creates
        config1 = get_or_create_config(db_session)
        assert config1.id == 1

        # Second call returns same instance
        config2 = get_or_create_config(db_session)
        assert config2.id == 1
        assert config1 is config2

    def test_qso_images_foreign_key_cascade(self, db_session: Session) -> None:
        """Verify cascade delete on qso_images join table."""
        # Create image and QSO
        image = SSTVImage(
            filename="test.png",
            filepath="/path/to/image.png",
            mode="ScottieS1",
        )
        qso = QSO(
            callsign="W1AW",
            mode="ScottieS1",
        )
        qso.images.append(image)
        db_session.add_all([image, qso])
        db_session.commit()

        image_id = image.id
        qso_id = qso.id

        # Verify join record exists
        join_record = db_session.query(QSOImage).filter_by(
            qso_id=qso_id, image_id=image_id
        ).first()
        assert join_record is not None

        # Delete QSO - should cascade to qso_images
        db_session.delete(qso)
        db_session.commit()

        # Verify join record is deleted
        join_record = db_session.query(QSOImage).filter_by(
            qso_id=qso_id, image_id=image_id
        ).first()
        assert join_record is None

        # But image should still exist
        remaining_image = db_session.get(SSTVImage, image_id)
        assert remaining_image is not None


# =============================================================================
# Relationship Tests
# =============================================================================


class TestRelationships:
    """Test ORM relationships between models."""

    def test_qso_to_images_relationship(self, db_session: Session) -> None:
        """Verify QSO -> Images many-to-many relationship."""
        image1 = SSTVImage(filename="a.png", filepath="/a.png", mode="ScottieS1")
        image2 = SSTVImage(filename="b.png", filepath="/b.png", mode="ScottieS1")
        qso = QSO(callsign="W1AW", mode="ScottieS1")

        qso.images.extend([image1, image2])
        db_session.add(qso)
        db_session.commit()

        # Reload and verify
        loaded_qso = db_session.get(QSO, qso.id)
        assert len(loaded_qso.images) == 2
        assert {img.filepath for img in loaded_qso.images} == {"/a.png", "/b.png"}

    def test_image_to_qsos_relationship(self, db_session: Session) -> None:
        """Verify Image -> QSOs back-reference."""
        image = SSTVImage(filename="shared.png", filepath="/shared.png", mode="ScottieS1")
        qso1 = QSO(callsign="W1AW", mode="ScottieS1")
        qso2 = QSO(callsign="K2XYZ", mode="ScottieS1")

        # Same image in multiple QSOs
        qso1.images.append(image)
        qso2.images.append(image)
        db_session.add_all([qso1, qso2])
        db_session.commit()

        # Verify from image side
        loaded_image = db_session.get(SSTVImage, image.id)
        assert len(loaded_image.qsos) == 2
        assert {qso.callsign for qso in loaded_image.qsos} == {"W1AW", "K2XYZ"}


# =============================================================================
# Default Value Tests
# =============================================================================


class TestDefaultValues:
    """Test that default values are correctly applied."""

    def test_sstv_image_defaults(self, db_session: Session) -> None:
        """Verify SSTVImage default values."""
        image = SSTVImage(
            filename="test.png",
            filepath="/test.png",
            mode="ScottieS1",
        )
        db_session.add(image)
        db_session.commit()

        assert image.is_received is True  # Default
        assert image.timestamp is not None  # Auto-set

    def test_qso_defaults(self, db_session: Session) -> None:
        """Verify QSO default values."""
        qso = QSO(callsign="W1AW", mode="ScottieS1")
        db_session.add(qso)
        db_session.commit()

        assert qso.is_sent is False  # Default
        assert qso.start_time is not None  # Auto-set

    def test_configuration_defaults(self, db_session: Session) -> None:
        """Verify Configuration default values match spec."""
        config = get_or_create_config(db_session)

        assert config.default_tx_mode == "ScottieS1"
        assert config.enable_auto_save is True
        assert config.ptt_method == "vox"
        assert config.ptt_serial_baud == 9600
        assert config.ptt_serial_signal == "RTS"
        assert config.ptt_pre_delay_ms == 500
        assert config.ptt_post_delay_ms == 200
        assert config.vox_preamble_ms == 500
        assert config.enable_stereo_guidance is False
        assert config.pilot_tone_hz == 1200
        assert config.enable_ai_captions is False
        assert config.enable_verbose_cli is False
        assert config.theme == "darkroom"


# =============================================================================
# Model Method Tests
# =============================================================================


class TestModelMethods:
    """Test model helper methods (to_dict, __repr__)."""

    def test_sstv_image_to_dict(self, db_session: Session) -> None:
        """Verify SSTVImage.to_dict() returns expected fields."""
        image = SSTVImage(
            filename="test.png",
            filepath="/path/to/test.png",
            mode="ScottieS1",
            callsign="W1AW",
            frequency_hz=14230000.0,
            rx_quality_score=0.85,
        )
        db_session.add(image)
        db_session.commit()

        data = image.to_dict()
        assert data["id"] == image.id
        assert data["filename"] == "test.png"
        assert data["filepath"] == "/path/to/test.png"
        assert data["mode"] == "ScottieS1"
        assert data["callsign"] == "W1AW"
        assert data["frequency_hz"] == 14230000.0
        assert data["rx_quality_score"] == 0.85
        assert data["is_received"] is True
        assert "timestamp" in data

    def test_qso_to_dict(self, db_session: Session) -> None:
        """Verify QSO.to_dict() returns expected fields including image_ids."""
        image = SSTVImage(filename="a.png", filepath="/a.png", mode="ScottieS1")
        qso = QSO(
            callsign="W1AW",
            mode="ScottieS1",
            frequency_hz=14230000.0,
            report="59",
        )
        qso.images.append(image)
        db_session.add(qso)
        db_session.commit()

        data = qso.to_dict()
        assert data["id"] == qso.id
        assert data["callsign"] == "W1AW"
        assert data["mode"] == "ScottieS1"
        assert data["frequency_hz"] == 14230000.0
        assert data["report"] == "59"
        assert data["is_sent"] is False
        assert image.id in data["image_ids"]

    def test_configuration_to_dict(self, db_session: Session) -> None:
        """Verify Configuration.to_dict() returns expected fields."""
        config = get_or_create_config(db_session)
        data = config.to_dict()

        assert "audio_input_device_id" in data
        assert "default_tx_mode" in data
        assert data["default_tx_mode"] == "ScottieS1"
        assert "ptt_method" in data
        assert "theme" in data
        assert "advanced_settings_json" in data

    def test_model_repr_strings(self, db_session: Session) -> None:
        """Verify __repr__ methods return informative strings."""
        image = SSTVImage(
            filename="test.png",
            filepath="/test.png",
            mode="ScottieS1",
            callsign="W1AW",
            is_received=True,  # Explicit to test repr
        )
        qso = QSO(callsign="K2XYZ", mode="MartinM1")
        config = Configuration(id=1)

        assert "SSTVImage" in repr(image)
        assert "RX" in repr(image)  # is_received=True
        assert "ScottieS1" in repr(image)

        # Test TX case
        tx_image = SSTVImage(
            filename="tx.png",
            filepath="/tx.png",
            mode="MartinM1",
            is_received=False,
        )
        assert "TX" in repr(tx_image)

        assert "QSO" in repr(qso)
        assert "K2XYZ" in repr(qso)

        assert "Configuration" in repr(config)


# =============================================================================
# Database Utility Tests
# =============================================================================


class TestDatabaseUtilities:
    """Test database connection and session utilities."""

    def test_init_database_creates_tables(self, temp_db_path: Path) -> None:
        """Verify init_database creates all tables."""
        engine, session_factory = init_database(temp_db_path)

        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert "sstv_images" in tables
        assert "qsos" in tables
        assert "qso_images" in tables
        assert "configurations" in tables

        engine.dispose()

    def test_foreign_keys_enabled(self, temp_db_path: Path) -> None:
        """Verify SQLite foreign key enforcement is enabled."""
        engine, _ = init_database(temp_db_path)

        with engine.connect() as conn:
            result = conn.execute(text("PRAGMA foreign_keys"))
            fk_enabled = result.scalar()
            assert fk_enabled == 1, "Foreign keys should be enabled"

        engine.dispose()

    def test_session_factory_creates_sessions(self, temp_db_path: Path) -> None:
        """Verify session factory creates working sessions."""
        engine, session_factory = init_database(temp_db_path)

        session = session_factory()
        assert session is not None

        # Test basic operation
        image = SSTVImage(filename="test.png", filepath="/test.png", mode="ScottieS1")
        session.add(image)
        session.commit()
        assert image.id is not None

        session.close()
        engine.dispose()


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_nullable_fields_accept_null(self, db_session: Session) -> None:
        """Verify nullable fields can be NULL."""
        image = SSTVImage(
            filename="minimal.png",
            filepath="/minimal.png",
            mode="Robot36",
            # All nullable fields omitted
        )
        db_session.add(image)
        db_session.commit()

        loaded = db_session.get(SSTVImage, image.id)
        assert loaded.callsign is None
        assert loaded.operator_name is None
        assert loaded.frequency_hz is None
        assert loaded.rx_quality_score is None
        assert loaded.comments is None
        assert loaded.raw_audio_filepath is None
        assert loaded.ai_caption is None

    def test_long_filepath_supported(self, db_session: Session) -> None:
        """Verify long filepaths (up to 1024 chars) are supported."""
        long_path = "/" + "a" * 1000 + ".png"
        image = SSTVImage(
            filename="long.png",
            filepath=long_path,
            mode="ScottieS1",
        )
        db_session.add(image)
        db_session.commit()

        loaded = db_session.get(SSTVImage, image.id)
        assert loaded.filepath == long_path

    def test_advanced_settings_json_storage(self, db_session: Session) -> None:
        """Verify JSON data can be stored in advanced_settings_json."""
        config = get_or_create_config(db_session)
        config.advanced_settings_json = '{"decoder": {"afc_enabled": true}}'
        db_session.commit()

        # Reload and verify
        db_session.expire(config)
        loaded = db_session.get(Configuration, 1)
        assert loaded.advanced_settings_json == '{"decoder": {"afc_enabled": true}}'
