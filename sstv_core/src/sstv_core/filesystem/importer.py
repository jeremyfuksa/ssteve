"""Image import functions for SSTeVe filesystem integration.

Provides:
- Filename metadata parsing (YYYYMMDD_HHMMSS_MODE_CALLSIGN.jpg)
- EXIF data extraction
- Database record creation and updates
- Graceful handling of missing/malformed metadata
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image
from PIL.ExifTags import TAGS

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from sstv_core.database.models import SSTVImage

logger = logging.getLogger(__name__)


# Known SSTV modes for validation
KNOWN_SSTV_MODES = {
    "ScottieS1", "ScottieS2", "ScottieDX",
    "MartinM1", "MartinM2",
    "Robot36", "Robot72",
    "PD90", "PD120", "PD160", "PD180", "PD240",
    "WraaseSC2-180",
}


def parse_image_metadata(filepath: Path) -> dict[str, Any]:
    """Parse metadata from image filename and EXIF data.

    Filename format: YYYYMMDD_HHMMSS_MODE_CALLSIGN.jpg
    Example: 20260115_143022_ScottieS1_K0ABC.jpg

    Falls back to EXIF data if filename doesn't match expected format.
    Returns gracefully degraded metadata if both fail.

    Args:
        filepath: Path to image file

    Returns:
        Dictionary with extracted metadata:
            - timestamp: datetime (from filename or EXIF, or file mtime)
            - mode: str (SSTV mode, or "Unknown")
            - callsign: str or None
            - operator_name: str or None (from EXIF Artist tag)
            - comments: str or None (from EXIF ImageDescription)
            - is_received: bool (True by default, False if in "transmitted" dir)

    """
    metadata: dict[str, Any] = {
        "timestamp": None,
        "mode": "Unknown",
        "callsign": None,
        "operator_name": None,
        "comments": None,
        "is_received": True,  # Default assumption
    }

    # Check if file is in "transmitted" subdirectory
    if "transmitted" in [p.lower() for p in filepath.parts]:
        metadata["is_received"] = False

    # Try parsing filename
    filename_meta = _parse_filename(filepath.stem)
    if filename_meta:
        metadata.update(filename_meta)
        logger.debug("Parsed metadata from filename: %s", filename_meta)

    # Extract EXIF data (may override filename metadata)
    exif_meta = _extract_exif_metadata(filepath)
    if exif_meta:
        # EXIF takes precedence for certain fields
        if exif_meta.get("timestamp"):
            metadata["timestamp"] = exif_meta["timestamp"]
        if exif_meta.get("operator_name"):
            metadata["operator_name"] = exif_meta["operator_name"]
        if exif_meta.get("comments"):
            metadata["comments"] = exif_meta["comments"]

        logger.debug("Extracted EXIF metadata: %s", exif_meta)

    # Fallback to file modification time if no timestamp found
    if metadata["timestamp"] is None:
        try:
            mtime = filepath.stat().st_mtime
            metadata["timestamp"] = datetime.fromtimestamp(mtime)
            logger.debug("Using file mtime as timestamp: %s", metadata["timestamp"])
        except OSError as e:
            logger.warning("Failed to get file mtime for %s: %s", filepath, e)
            metadata["timestamp"] = datetime.utcnow()

    return metadata


def _parse_filename(filename_stem: str) -> dict[str, Any] | None:
    """Parse SSTV metadata from filename.

    Expected format: YYYYMMDD_HHMMSS_MODE_CALLSIGN
    Parts are optional except date/time.

    Args:
        filename_stem: Filename without extension

    Returns:
        Dict with parsed fields, or None if format doesn't match

    """
    # Pattern: YYYYMMDD_HHMMSS_MODE_CALLSIGN
    # MODE and CALLSIGN are optional
    pattern = r'^(\d{8})_(\d{6})(?:_([A-Za-z0-9]+))?(?:_([A-Z0-9/]+))?$'
    match = re.match(pattern, filename_stem)

    if match:
        date_str, time_str, mode, callsign = match.groups()
    else:
        # SSTeVe's own decode output: sstv_rx_MODE_YYYYMMDD_HHMMSS
        # (ImageSaver._generate_filename). Until 2026-08-07 the importer
        # didn't recognize the app's own files, so they imported with
        # mode="Unknown" and an mtime timestamp.
        own = re.match(
            r'^sstv_(?:rx|tx)_([A-Za-z0-9]+)_(\d{8})_(\d{6})$', filename_stem
        )
        if not own:
            logger.debug("Filename doesn't match expected pattern: %s", filename_stem)
            return None
        mode, date_str, time_str = own.groups()
        callsign = None

    metadata: dict[str, Any] = {}

    # Parse timestamp
    try:
        datetime_str = f"{date_str}_{time_str}"
        timestamp = datetime.strptime(datetime_str, "%Y%m%d_%H%M%S")
        metadata["timestamp"] = timestamp
    except ValueError as e:
        logger.warning("Failed to parse timestamp from filename: %s", e)
        return None

    # Parse mode (validate against known modes)
    if mode:
        if mode in KNOWN_SSTV_MODES:
            metadata["mode"] = mode
        else:
            # Try case-insensitive match
            mode_lower = mode.lower()
            for known_mode in KNOWN_SSTV_MODES:
                if known_mode.lower() == mode_lower:
                    metadata["mode"] = known_mode
                    break
            else:
                logger.warning("Unknown SSTV mode in filename: %s", mode)
                metadata["mode"] = mode  # Keep it anyway

    # Parse callsign
    if callsign:
        # Validate callsign format (basic validation)
        if re.match(r'^[A-Z0-9/]{3,12}$', callsign, re.IGNORECASE):
            metadata["callsign"] = callsign.upper()
        else:
            logger.warning("Invalid callsign format in filename: %s", callsign)

    return metadata


def _extract_exif_metadata(filepath: Path) -> dict[str, Any] | None:
    """Extract metadata from image EXIF data.

    Args:
        filepath: Path to image file

    Returns:
        Dict with EXIF metadata, or None if extraction fails

    """
    try:
        with Image.open(filepath) as img:
            exif_data = img.getexif()

            if not exif_data:
                return None

            metadata: dict[str, Any] = {}

            # Extract relevant EXIF tags
            for tag_id, value in exif_data.items():
                tag_name = TAGS.get(tag_id, tag_id)

                # DateTime (original or digitized)
                if tag_name in ("DateTime", "DateTimeOriginal", "DateTimeDigitized"):
                    try:
                        # EXIF datetime format: "YYYY:MM:DD HH:MM:SS"
                        timestamp = datetime.strptime(str(value), "%Y:%m:%d %H:%M:%S")
                        metadata["timestamp"] = timestamp
                    except ValueError:
                        logger.debug("Failed to parse EXIF datetime: %s", value)

                # Artist (operator name)
                elif tag_name == "Artist":
                    metadata["operator_name"] = str(value)

                # ImageDescription (comments)
                elif tag_name == "ImageDescription":
                    metadata["comments"] = str(value)

                # UserComment (additional comments)
                elif tag_name == "UserComment":
                    if "comments" not in metadata:
                        metadata["comments"] = str(value)

            return metadata if metadata else None

    except Exception as e:
        logger.warning("Failed to extract EXIF data from %s: %s", filepath, e)
        return None


class ImageImporter:
    """Handles importing and managing SSTV images in the database.

    Provides methods for:
    - Importing new images with metadata extraction
    - Updating existing image metadata
    - Removing deleted images from database
    - Moving/renaming images with database sync
    """

    def __init__(self, session: Session):
        """Initialize the importer.

        Args:
            session: Active SQLAlchemy session for database operations

        """
        self._session = session

    def import_image(self, filepath: Path) -> SSTVImage | None:
        """Import a new image to the database.

        Extracts metadata from filename and EXIF data, creates database record.
        Skips import if image already exists in database.

        Args:
            filepath: Path to image file

        Returns:
            Created SSTVImage instance, or None if import failed/skipped

        """
        from sstv_core.database.models import SSTVImage

        # Check if file exists
        if not filepath.exists():
            logger.warning("Cannot import non-existent file: %s", filepath)
            return None

        # Check if already imported
        filepath_str = str(filepath.resolve())
        existing = self._session.query(SSTVImage).filter_by(filepath=filepath_str).first()
        if existing:
            logger.debug("Image already in database: %s (id=%d)", filepath, existing.id)
            return existing

        # Extract metadata
        try:
            metadata = parse_image_metadata(filepath)
        except Exception as e:
            logger.error("Failed to parse metadata for %s: %s", filepath, e, exc_info=True)
            return None

        # Create database record
        try:
            image = SSTVImage(
                filename=filepath.name,
                filepath=filepath_str,
                timestamp=metadata["timestamp"],
                mode=metadata["mode"],
                callsign=metadata.get("callsign"),
                operator_name=metadata.get("operator_name"),
                comments=metadata.get("comments"),
                is_received=metadata["is_received"],
            )

            self._session.add(image)
            self._session.commit()

            logger.info("Imported image to database: %s (id=%d)", filepath.name, image.id)
            return image

        except Exception as e:
            self._session.rollback()
            logger.error("Failed to create database record for %s: %s", filepath, e, exc_info=True)
            return None

    def update_image_metadata(self, filepath: Path) -> SSTVImage | None:
        """Update metadata for an existing image.

        Re-extracts metadata from file and updates database record.

        Args:
            filepath: Path to image file

        Returns:
            Updated SSTVImage instance, or None if update failed

        """
        from sstv_core.database.models import SSTVImage

        # Find existing record
        filepath_str = str(filepath.resolve())
        image = self._session.query(SSTVImage).filter_by(filepath=filepath_str).first()

        if not image:
            logger.warning("Cannot update non-existent image: %s", filepath)
            return None

        # Re-extract metadata
        try:
            metadata = parse_image_metadata(filepath)
        except Exception as e:
            logger.error("Failed to parse metadata for %s: %s", filepath, e, exc_info=True)
            return None

        # Update record
        try:
            image.timestamp = metadata["timestamp"]
            image.mode = metadata["mode"]
            image.callsign = metadata.get("callsign")
            image.operator_name = metadata.get("operator_name")
            image.comments = metadata.get("comments")
            image.is_received = metadata["is_received"]

            self._session.commit()

            logger.info("Updated image metadata: %s (id=%d)", filepath.name, image.id)
            return image

        except Exception as e:
            self._session.rollback()
            logger.error("Failed to update database record for %s: %s", filepath, e, exc_info=True)
            return None

    def remove_image(self, filepath: Path) -> bool:
        """Remove an image from the database.

        Args:
            filepath: Path to deleted image file

        Returns:
            True if image was removed, False if not found or error occurred

        """
        from sstv_core.database.models import SSTVImage

        # Find existing record
        filepath_str = str(filepath.resolve())
        image = self._session.query(SSTVImage).filter_by(filepath=filepath_str).first()

        if not image:
            logger.debug("Image not in database, nothing to remove: %s", filepath)
            return False

        # Delete record
        try:
            image_id = image.id
            self._session.delete(image)
            self._session.commit()

            logger.info("Removed image from database: %s (id=%d)", filepath, image_id)
            return True

        except Exception as e:
            self._session.rollback()
            logger.error("Failed to remove database record for %s: %s", filepath, e, exc_info=True)
            return False

    def move_image(self, src_path: Path, dest_path: Path) -> SSTVImage | None:
        """Update database record when an image is moved/renamed.

        Args:
            src_path: Original file path
            dest_path: New file path

        Returns:
            Updated SSTVImage instance, or None if update failed

        """
        from sstv_core.database.models import SSTVImage

        # Find existing record by old path
        src_str = str(src_path.resolve())
        image = self._session.query(SSTVImage).filter_by(filepath=src_str).first()

        if not image:
            logger.warning("Cannot move non-existent image: %s", src_path)
            # Try importing as new image instead
            return self.import_image(dest_path)

        # Update filepath and filename
        try:
            dest_str = str(dest_path.resolve())
            image.filepath = dest_str
            image.filename = dest_path.name

            # Re-extract metadata from new path (filename may have changed)
            metadata = parse_image_metadata(dest_path)
            image.timestamp = metadata["timestamp"]
            image.mode = metadata["mode"]
            image.callsign = metadata.get("callsign")
            image.operator_name = metadata.get("operator_name")
            image.comments = metadata.get("comments")
            image.is_received = metadata["is_received"]

            self._session.commit()

            logger.info(
                "Moved image in database: %s -> %s (id=%d)",
                src_path.name,
                dest_path.name,
                image.id,
            )
            return image

        except Exception as e:
            self._session.rollback()
            logger.error("Failed to move image %s -> %s: %s", src_path, dest_path, e, exc_info=True)
            return None

    def import_directory(
        self,
        directory: Path,
        recursive: bool = True,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> tuple[int, int, list[str]]:
        """Import all images from a directory.

        Args:
            directory: Directory to scan for images
            recursive: If True, scan subdirectories
            progress_callback: Optional callback(current, total) called during import

        Returns:
            Tuple of (imported_count, skipped_count, error_list)

        """
        if not directory.exists():
            raise FileNotFoundError(f"Directory does not exist: {directory}")

        if not directory.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {directory}")

        # Find all image files
        image_files: list[Path] = []
        for ext in [".jpg", ".jpeg", ".png", ".bmp"]:
            if recursive:
                image_files.extend(directory.rglob(f"*{ext}"))
                image_files.extend(directory.rglob(f"*{ext.upper()}"))
            else:
                image_files.extend(directory.glob(f"*{ext}"))
                image_files.extend(directory.glob(f"*{ext.upper()}"))

        total_files = len(image_files)
        imported_count = 0
        skipped_count = 0
        errors = []

        logger.info("Found %d image files in %s", total_files, directory)

        # Import each file
        for i, filepath in enumerate(image_files, 1):
            if progress_callback:
                progress_callback(i, total_files)

            try:
                result = self.import_image(filepath)
                if result:
                    if result.id:  # Newly created
                        imported_count += 1
                    else:  # Already existed
                        skipped_count += 1
                else:
                    skipped_count += 1

            except Exception as e:
                error_msg = f"{filepath}: {e}"
                errors.append(error_msg)
                logger.error("Error importing %s: %s", filepath, e, exc_info=True)

        logger.info(
            "Directory import complete: %d imported, %d skipped, %d errors",
            imported_count,
            skipped_count,
            len(errors)
        )

        return imported_count, skipped_count, errors
