"""Image auto-save functionality for SSTeVe.

Handles saving decoded SSTV images with metadata to filesystem.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
from PIL import Image

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

    # (save_with_metadata was deleted 2026-08-07: it constructed SSTVImage
    # with column names that have never existed -- is_transmitted, snr,
    # frequency, width, height -- so it crashed on first use, and nothing
    # called it. The API decode path creates gallery records via
    # dsp_manager._create_image_record, which uses the real columns.)

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
