"""SQLAlchemy ORM models for SSTeVe database.

Schema follows backend-spec.md Section 2.1/2.2:
- sstv_images: Received/transmitted SSTV images (metadata only, files on disk)
- qsos: QSO contact log entries
- qso_images: Many-to-many join table (QSO <-> Image)
- configurations: Singleton settings table (id=1 constraint enforced)

All timestamps use UTC. Image data stored as files, not blobs.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

if TYPE_CHECKING:
    pass


# =============================================================================
# Base Class
# =============================================================================


logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


# =============================================================================
# Association Table (QSO <-> Image many-to-many)
# =============================================================================


class QSOImage(Base):
    """Join table linking QSOs to SSTV images.

    A QSO can have multiple images (sent/received during contact).
    An image can be associated with multiple QSOs (e.g., reused template).
    """

    __tablename__ = "qso_images"

    qso_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("qsos.id", ondelete="CASCADE"),
        primary_key=True,
    )
    image_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sstv_images.id", ondelete="CASCADE"),
        primary_key=True,
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<QSOImage(qso_id={self.qso_id}, image_id={self.image_id})>"


# =============================================================================
# SSTV Images Table
# =============================================================================


class SSTVImage(Base):
    """SSTV image metadata.

    Images are stored as files on disk (filepath reference).
    This table stores metadata for search, filtering, and display.

    Note: rx_quality_score is 0.0-1.0 representing signal quality
          (higher = better signal, cleaner image).
    """

    __tablename__ = "sstv_images"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # File references (filepath is unique - no duplicate files)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    filepath: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)

    # Temporal
    timestamp: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    # SSTV mode (e.g., "ScottieS1", "MartinM1", "Robot36")
    mode: Mapped[str] = mapped_column(String(50), nullable=False)

    # Operator info (from decoded image or user input)
    callsign: Mapped[str | None] = mapped_column(String(20), nullable=True)
    operator_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # RF parameters
    frequency_hz: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Signal quality (0.0-1.0, higher = better)
    rx_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # User notes/comments
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Direction: True = received, False = transmitted
    is_received: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Optional raw audio recording reference
    raw_audio_filepath: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # AI-generated alt-text for accessibility
    ai_caption: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Composition data for re-editing/retransmission (TRANSMIT_SPEC.md Phase 1)
    # Stores JSON: {background: {...}, zones: [{zone, text, font, size, color, alignment}, ...]}
    composition_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # FSKID (Automatic Callsign Detection) - FSKID_SPECIFICATION.md
    fskid_detected: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        comment="Whether FSKID callsign data was detected"
    )
    fskid_confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="FSKID decoder confidence (0.0-1.0)"
    )
    fskid_checksum_valid: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        comment="FSKID checksum validation result"
    )

    # Signal Measurements (for RSV calculation) - AUTO_RSV_SPECIFICATION.md
    rx_snr_db: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Signal-to-noise ratio in dB"
    )
    rx_peak_amplitude: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Peak signal level (0.0-1.0)"
    )
    rx_noise_floor: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Background noise level (0.0-1.0)"
    )

    # RSV Signal Report (Readability, Signal, Video) - AUTO_RSV_SPECIFICATION.md
    rsv_readability: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="RSV Readability (1-5)"
    )
    rsv_signal: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="RSV Signal strength (1-9, S-meter)"
    )
    rsv_video: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="RSV Video quality (1-5)"
    )
    rsv_report: Mapped[str | None] = mapped_column(
        String(3),
        nullable=True,
        comment="Formatted RSV (e.g., '595')"
    )

    # Detailed Decode Metrics (JSON for analysis)
    decode_metrics_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Full DecodeMetrics as JSON"
    )

    # Relationships
    qsos: Mapped[list[QSO]] = relationship(
        "QSO",
        secondary="qso_images",
        back_populates="images",
    )

    # Indexes per backend-spec.md Section 2.1
    __table_args__ = (
        Index("idx_images_timestamp", "timestamp"),
        Index("idx_images_mode", "mode"),
        Index("idx_images_callsign", "callsign"),
        Index("idx_images_rsv_signal", "rsv_signal"),
        Index("idx_images_snr", "rx_snr_db"),
        Index("idx_images_fskid_detected", "fskid_detected"),
    )

    def __repr__(self) -> str:
        """Return string representation."""
        direction = "RX" if self.is_received else "TX"
        return f"<SSTVImage({direction} id={self.id}, mode={self.mode}, callsign={self.callsign})>"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "filename": self.filename,
            "filepath": self.filepath,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "mode": self.mode,
            "callsign": self.callsign,
            "operator_name": self.operator_name,
            "frequency_hz": self.frequency_hz,
            "rx_quality_score": self.rx_quality_score,
            "comments": self.comments,
            "is_received": self.is_received,
            "raw_audio_filepath": self.raw_audio_filepath,
            "ai_caption": self.ai_caption,
            # FSKID data
            "fskid_detected": self.fskid_detected,
            "fskid_confidence": self.fskid_confidence,
            "fskid_checksum_valid": self.fskid_checksum_valid,
            # Signal measurements
            "rx_snr_db": self.rx_snr_db,
            "rx_peak_amplitude": self.rx_peak_amplitude,
            "rx_noise_floor": self.rx_noise_floor,
            # RSV signal report
            "rsv_readability": self.rsv_readability,
            "rsv_signal": self.rsv_signal,
            "rsv_video": self.rsv_video,
            "rsv_report": self.rsv_report,
        }


# =============================================================================
# QSO Log Table
# =============================================================================


class QSO(Base):
    """QSO (contact) log entry.

    Tracks amateur radio contacts with associated SSTV images.
    Start/end times mark the contact duration.
    """

    __tablename__ = "qsos"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Temporal
    start_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Contact info
    mode: Mapped[str] = mapped_column(String(50), nullable=False)
    callsign: Mapped[str] = mapped_column(String(20), nullable=False)

    # RF parameters
    frequency_hz: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Signal reports (e.g., "59", "55", RST format)
    report: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # User notes
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Direction: True = we initiated, False = they initiated
    is_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationships
    images: Mapped[list[SSTVImage]] = relationship(
        "SSTVImage",
        secondary="qso_images",
        back_populates="qsos",
    )

    # Index per backend-spec.md Section 2.1
    __table_args__ = (
        Index("idx_qsos_start", "start_time"),
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<QSO(id={self.id}, callsign={self.callsign}, mode={self.mode})>"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "mode": self.mode,
            "callsign": self.callsign,
            "frequency_hz": self.frequency_hz,
            "report": self.report,
            "comments": self.comments,
            "is_sent": self.is_sent,
            "image_ids": [img.id for img in self.images] if self.images else [],
        }


# =============================================================================
# Configuration Table (Singleton Pattern)
# =============================================================================


class Configuration(Base):
    """Application configuration (singleton pattern).

    Only one row exists (id=1), enforced via CHECK constraint.
    Stores all user-configurable settings including audio, PTT,
    accessibility options, and advanced settings as JSON.

    Uses JSON field for extensibility - advanced_settings_json can hold
    decoder/encoder/UI/audio/experimental settings without schema changes.
    """

    __tablename__ = "configurations"

    # Singleton enforcement: id must always be 1
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        default=1,
    )

    # --- Audio Settings ---
    audio_input_device_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    audio_output_device_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_tx_mode: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="ScottieS1",
    )

    # --- Storage Settings ---
    image_save_directory: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        default=lambda: str(Path.home() / ".ssteve" / "images"),
    )
    mmsstv_import_directory: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    enable_auto_save: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # --- PTT Control ---
    ptt_method: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="vox",
    )  # 'none', 'serial', 'vox'
    ptt_serial_port: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ptt_serial_baud: Mapped[int] = mapped_column(Integer, nullable=False, default=9600)
    ptt_serial_signal: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="RTS",
    )  # 'RTS' or 'DTR'
    ptt_pre_delay_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    ptt_post_delay_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
    vox_preamble_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=500)

    # --- Accessibility ---
    enable_stereo_guidance: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pilot_tone_hz: Mapped[int] = mapped_column(Integer, nullable=False, default=1200)
    enable_ai_captions: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enable_verbose_cli: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- Theme ---
    theme: Mapped[str] = mapped_column(String(50), nullable=False, default="darkroom")

    # --- UI State (stored as binary for geometry/state) ---
    window_geometry: Mapped[bytes | None] = mapped_column(nullable=True)
    window_state: Mapped[bytes | None] = mapped_column(nullable=True)
    last_input_device: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_output_device: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # --- Advanced Settings (JSON for extensibility) ---
    # Schema documented in backend-spec.md Section 2.1
    advanced_settings_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Singleton constraint
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton_constraint"),
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<Configuration(theme={self.theme}, ptt={self.ptt_method})>"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "audio_input_device_id": self.audio_input_device_id,
            "audio_output_device_id": self.audio_output_device_id,
            "default_tx_mode": self.default_tx_mode,
            "image_save_directory": self.image_save_directory,
            "mmsstv_import_directory": self.mmsstv_import_directory,
            "enable_auto_save": self.enable_auto_save,
            "ptt_method": self.ptt_method,
            "ptt_serial_port": self.ptt_serial_port,
            "ptt_serial_baud": self.ptt_serial_baud,
            "ptt_serial_signal": self.ptt_serial_signal,
            "ptt_pre_delay_ms": self.ptt_pre_delay_ms,
            "ptt_post_delay_ms": self.ptt_post_delay_ms,
            "vox_preamble_ms": self.vox_preamble_ms,
            "enable_stereo_guidance": self.enable_stereo_guidance,
            "pilot_tone_hz": self.pilot_tone_hz,
            "enable_ai_captions": self.enable_ai_captions,
            "enable_verbose_cli": self.enable_verbose_cli,
            "theme": self.theme,
            "last_input_device": self.last_input_device,
            "last_output_device": self.last_output_device,
            "advanced_settings_json": self.advanced_settings_json,
        }


# =============================================================================
# Explicit Index Definitions
# =============================================================================

# These are defined inline via index=True on columns, but we can also
# define composite or additional indexes here if needed.
# The spec requires these indexes:
#   - idx_images_timestamp (on sstv_images.timestamp DESC)
#   - idx_images_mode (on sstv_images.mode)
#   - idx_images_callsign (on sstv_images.callsign)
#   - idx_qsos_start (on qsos.start_time DESC)
#
# SQLAlchemy's index=True creates standard ASC indexes. For explicit
# DESC ordering, we define them in __table_args__ or use Index() objects.

# Note: SQLite handles DESC indexes via query optimization, so index=True
# on the column is sufficient. The naming is for documentation purposes.


# =============================================================================
# Database Connection Utilities
# =============================================================================


def get_default_db_path() -> Path:
    """Get the default database file path.

    Returns ~/.ssteve/ssteve.db, creating the directory if needed.
    """
    db_dir = Path.home() / ".ssteve"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "ssteve.db"


def get_database_url(db_path: Path | str | None = None) -> str:
    """Get SQLAlchemy database URL.

    Args:
        db_path: Optional path to database file. Defaults to ~/.ssteve/ssteve.db

    Returns:
        SQLAlchemy connection URL (sqlite:///path/to/db)

    """
    if db_path is None:
        db_path = get_default_db_path()
    elif isinstance(db_path, str):
        db_path = Path(db_path)

    return f"sqlite:///{db_path}"


def create_db_engine(
    db_path: Path | str | None = None,
    echo: bool = False,
) -> Engine:
    """Create a SQLAlchemy engine for the database.

    Args:
        db_path: Optional path to database file. Defaults to ~/.ssteve/ssteve.db
        echo: If True, log all SQL statements (for debugging)

    Returns:
        SQLAlchemy Engine instance

    """
    url = get_database_url(db_path)
    engine = create_engine(url, echo=echo)

    # Enable foreign key enforcement for SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection: Any, connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory bound to the given engine.

    Args:
        engine: SQLAlchemy Engine instance

    Returns:
        Session factory (call it to create new sessions)

    """
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_database(
    db_path: Path | str | None = None,
    echo: bool = False,
) -> tuple[Engine, sessionmaker[Session]]:
    """Initialize the database, creating all tables if they don't exist.

    This is a convenience function for development/testing.
    For production, use Alembic migrations.

    Args:
        db_path: Optional path to database file. Defaults to ~/.ssteve/ssteve.db
        echo: If True, log all SQL statements

    Returns:
        Tuple of (engine, session_factory)

    """
    engine = create_db_engine(db_path, echo=echo)
    Base.metadata.create_all(engine)
    _stamp_alembic_head(engine)

    session_factory = create_session_factory(engine)
    return engine, session_factory


def _stamp_alembic_head(engine: Engine) -> None:
    """Record the current Alembic head on a create_all database.

    The app initializes its schema with create_all, which never wrote
    alembic_version -- so `alembic upgrade head` on any real install died
    on "table configurations already exists". Stamping makes upgrades a
    no-op on a fresh schema and a real migration path later.
    """
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from sqlalchemy import text

        migrations = Path(__file__).resolve().parent / "migrations"
        config = Config()
        config.set_main_option("script_location", str(migrations))
        head = ScriptDirectory.from_config(config).get_current_head()
        if head is None:
            return

        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS alembic_version "
                    "(version_num VARCHAR(32) NOT NULL, "
                    "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
                )
            )
            existing = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).fetchall()
            if not existing:
                connection.execute(
                    text("INSERT INTO alembic_version (version_num) VALUES (:v)"),
                    {"v": head},
                )
                logger.info("Stamped alembic_version at head %s", head)
    except Exception as e:  # pragma: no cover - alembic missing or unreadable
        logger.warning("Could not stamp alembic version: %s", e)


def get_or_create_config(session: Session) -> Configuration:
    """Get the singleton Configuration, creating it if it doesn't exist.

    Args:
        session: Active SQLAlchemy session

    Returns:
        The Configuration instance (always id=1)

    """
    config = session.get(Configuration, 1)
    if config is None:
        config = Configuration(id=1)
        session.add(config)
        session.commit()
    return config
