"""Image auto-save functionality for SSTeVe.

Handles saving decoded SSTV images with metadata to filesystem.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

import numpy as np
from PIL import Image

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ImageSaveError(Exception):
    """Raised when image save operations fail."""

    pass


class ImageSaver:
    """Saves decoded SSTV images with metadata.

    Follows filesystem-native storage principle:
    - Images stored as regular files
    - Database stores metadata only (filepath, mode, timestamp, etc.)
    """

    SUPPORTED_FORMATS: ClassVar[set[str]] = {"png", "jpg", "jpeg", "webp"}
    DEFAULT_FORMAT = "png"

    def __init__(
        self,
        base_directory: str | Path,
        auto_save_enabled: bool = True,
        file_format: str = DEFAULT_FORMAT,
    ) -> None:
        """Initialize image saver.

        Args:
            base_directory: Base directory for image storage
            auto_save_enabled: Whether to automatically save images
            file_format: Image format (png, jpg, webp)

        """
        self._base_dir = Path(base_directory)
        self._auto_save = auto_save_enabled
        self._format = file_format.lower()

        if self._format not in self.SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported format: {file_format}. Use one of {self.SUPPORTED_FORMATS}"
            )

        # Ensure directories exist
        self._received_dir = self._base_dir / "received"
        self._transmitted_dir = self._base_dir / "transmitted"
        self._received_dir.mkdir(parents=True, exist_ok=True)
        self._transmitted_dir.mkdir(parents=True, exist_ok=True)

    @property
    def base_directory(self) -> Path:
        return self._base_dir

    @property
    def auto_save_enabled(self) -> bool:
        return self._auto_save

    def _generate_filename(self, mode: str, is_transmitted: bool = False) -> str:
        """Generate unique filename based on timestamp and mode."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        direction = "tx" if is_transmitted else "rx"
        return f"sstv_{direction}_{mode}_{timestamp}.{self._format}"

    def _validate_path(self, path: Path) -> bool:
        """Validate path is within base directory (prevent traversal)."""
        try:
            resolved = path.resolve()
            return resolved.is_relative_to(self._base_dir.resolve())
        except (ValueError, OSError):
            return False

    def save_image(
        self,
        image_array: np.ndarray,
        mode: str,
        is_transmitted: bool = False,
        custom_filename: str | None = None,
        quality: int = 95,
    ) -> Path:
        """Save image array to filesystem.

        Args:
            image_array: RGB image as numpy array (H, W, 3)
            mode: SSTV mode name (e.g., "ScottieS1")
            is_transmitted: True if transmitted, False if received
            custom_filename: Override auto-generated filename
            quality: JPEG/WebP quality (1-100)

        Returns:
            Path to saved image file

        Raises:
            ImageSaveError: If save fails

        """
        # Determine target directory
        target_dir = self._transmitted_dir if is_transmitted else self._received_dir

        # Generate or use custom filename
        filename = custom_filename or self._generate_filename(mode, is_transmitted)
        filepath = target_dir / filename

        # Validate path
        if not self._validate_path(filepath):
            raise ImageSaveError(f"Invalid path: {filepath}")

        try:
            # Convert numpy array to PIL Image
            if image_array.dtype != np.uint8:
                image_array = (image_array * 255).astype(np.uint8)

            image = Image.fromarray(image_array, mode="RGB")

            # Save with appropriate options
            save_kwargs: dict[str, Any] = {}
            if self._format in ("jpg", "jpeg"):
                save_kwargs["quality"] = quality
                save_kwargs["optimize"] = True
            elif self._format == "webp":
                save_kwargs["quality"] = quality
            elif self._format == "png":
                save_kwargs["optimize"] = True

            image.save(filepath, **save_kwargs)
            logger.info("Saved image to %s", filepath)
            return filepath

        except Exception as e:
            raise ImageSaveError(f"Can't save image to {filepath}: {e}") from e

    def save_with_metadata(
        self,
        session: Session,
        image_array: np.ndarray,
        mode: str,
        is_transmitted: bool = False,
        callsign: str | None = None,
        snr: float | None = None,
        frequency: float | None = None,
        custom_filename: str | None = None,
    ) -> tuple[Path, int]:
        """Save image and create database record.

        Args:
            session: SQLAlchemy session for database operations
            image_array: RGB image as numpy array
            mode: SSTV mode name
            is_transmitted: True if transmitted
            callsign: Detected/associated callsign
            snr: Signal-to-noise ratio
            frequency: Operating frequency
            custom_filename: Override filename

        Returns:
            Tuple of (filepath, database_id)

        """
        from sstv_core.database.models import SSTVImage

        # Save file first
        filepath = self.save_image(
            image_array,
            mode,
            is_transmitted,
            custom_filename,
        )

        # Create database record
        db_image = SSTVImage(
            filepath=str(filepath),
            mode=mode,
            is_transmitted=is_transmitted,
            callsign=callsign,
            snr=snr,
            frequency=frequency,
            width=image_array.shape[1],
            height=image_array.shape[0],
        )

        session.add(db_image)
        session.commit()

        logger.info("Created database record for image: id=%d", db_image.id)
        return filepath, db_image.id

    def list_images(
        self,
        is_transmitted: bool | None = None,
        limit: int = 100,
    ) -> list[Path]:
        """List saved images.

        Args:
            is_transmitted: Filter by direction (None for both)
            limit: Maximum number of images to return

        Returns:
            List of image file paths, newest first

        """
        if is_transmitted is None:
            dirs = [self._received_dir, self._transmitted_dir]
        elif is_transmitted:
            dirs = [self._transmitted_dir]
        else:
            dirs = [self._received_dir]

        images: list[Path] = []
        for d in dirs:
            for ext in self.SUPPORTED_FORMATS:
                images.extend(d.glob(f"*.{ext}"))

        # Sort by modification time, newest first
        images.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return images[:limit]

    def delete_image(self, filepath: str | Path) -> bool:
        """Delete an image file.

        Args:
            filepath: Path to image to delete

        Returns:
            True if deleted, False if not found

        """
        path = Path(filepath)

        if not self._validate_path(path):
            logger.warning("Attempted to delete file outside base directory: %s", filepath)
            return False

        try:
            if path.exists():
                path.unlink()
                logger.info("Deleted image: %s", filepath)
                return True
            return False
        except Exception as e:
            logger.error("Error deleting image %s: %s", filepath, e)
            return False
