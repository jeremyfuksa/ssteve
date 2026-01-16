"""MMSSTV library import functionality.

Provides batch import of SSTV images from MMSSTV-compatible directory structures.
Handles recursive scanning, progress tracking, and batch database transactions.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Callable, List, Dict, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class MMSStvImporter:
    """Batch importer for MMSSTV-compatible image libraries.

    MMSSTV typically stores images in a flat or nested directory structure
    with filenames like: YYYYMMDD_HHMMSS_MODE_CALLSIGN.jpg

    This importer:
    - Recursively scans directories
    - Filters for image files (jpg, png, bmp)
    - Batch imports with progress tracking
    - Transaction batching (commit every 100 images)
    - Error logging without aborting entire import

    Usage:
        from sstv_core.filesystem import MMSStvImporter
        from sstv_core.database.models import init_database

        engine, session_factory = init_database()

        with session_factory() as session:
            importer = MMSStvImporter(session)

            result = importer.import_directory(
                directory="/path/to/mmsstv/library",
                progress_callback=lambda cur, tot: print(f"{cur}/{tot}")
            )

            print(f"Imported: {result['imported']}")
            print(f"Skipped: {result['skipped']}")
            print(f"Errors: {len(result['errors'])}")
    """

    # Image file extensions to import
    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}

    # Batch size for database transactions
    BATCH_SIZE = 100

    def __init__(self, session: Session):
        """Initialize the MMSSTV importer.

        Args:
            session: Active SQLAlchemy session for database operations
        """
        self._session = session

    def import_directory(
        self,
        directory: str | Path,
        recursive: bool = True,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, Any]:
        """Import all images from a directory.

        Scans directory for SSTV images and imports them to the database
        with metadata extraction. Commits in batches for efficiency.

        Args:
            directory: Path to directory containing SSTV images
            recursive: If True, scan subdirectories (default True)
            progress_callback: Optional function(current, total) called during import

        Returns:
            Dictionary with import results:
                - imported: Number of successfully imported images
                - skipped: Number of already-existing images
                - errors: List of error messages
                - total: Total files scanned

        Raises:
            FileNotFoundError: If directory doesn't exist
            NotADirectoryError: If path is not a directory
        """
        directory = Path(directory)

        if not directory.exists():
            raise FileNotFoundError(f"Directory does not exist: {directory}")

        if not directory.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {directory}")

        logger.info("Starting MMSSTV import from: %s (recursive=%s)", directory, recursive)

        # Find all image files
        image_files = self._scan_directory(directory, recursive)
        total_files = len(image_files)

        logger.info("Found %d image files to import", total_files)

        # Import files with batch transactions
        result = self._import_files(
            files=image_files,
            progress_callback=progress_callback,
        )

        logger.info(
            "MMSSTV import complete: %d imported, %d skipped, %d errors (total %d files)",
            result["imported"],
            result["skipped"],
            len(result["errors"]),
            total_files,
        )

        return result

    def _scan_directory(
        self,
        directory: Path,
        recursive: bool,
    ) -> List[Path]:
        """Scan directory for image files.

        Args:
            directory: Directory to scan
            recursive: If True, scan subdirectories

        Returns:
            List of image file paths, sorted by filename
        """
        image_files: List[Path] = []

        for ext in self.IMAGE_EXTENSIONS:
            if recursive:
                # Recursive scan (e.g., **/*.jpg)
                image_files.extend(directory.rglob(f"*{ext}"))
                # Also match uppercase extensions
                image_files.extend(directory.rglob(f"*{ext.upper()}"))
            else:
                # Non-recursive scan (e.g., *.jpg)
                image_files.extend(directory.glob(f"*{ext}"))
                image_files.extend(directory.glob(f"*{ext.upper()}"))

        # Remove duplicates (in case of case-insensitive filesystems)
        image_files = list(set(image_files))

        # Sort by filename for deterministic import order
        image_files.sort(key=lambda p: p.name)

        return image_files

    def _import_files(
        self,
        files: List[Path],
        progress_callback: Optional[Callable[[int, int], None]],
    ) -> Dict[str, Any]:
        """Import a list of image files to the database.

        Imports in batches, committing every BATCH_SIZE images for efficiency.
        Errors are logged but don't abort the import.

        Args:
            files: List of image file paths
            progress_callback: Optional progress callback(current, total)

        Returns:
            Dictionary with import statistics
        """
        from sstv_core.filesystem.importer import ImageImporter

        importer = ImageImporter(self._session)

        imported_count = 0
        skipped_count = 0
        errors: List[str] = []

        total_files = len(files)
        batch_start_idx = 0

        for i, filepath in enumerate(files, start=1):
            # Progress callback
            if progress_callback:
                try:
                    progress_callback(i, total_files)
                except Exception as e:
                    logger.warning("Progress callback failed: %s", e)

            # Import image
            try:
                # Check if already exists (fast query before parsing)
                from sstv_core.database.models import SSTVImage

                filepath_str = str(filepath.resolve())
                existing = self._session.query(SSTVImage).filter_by(filepath=filepath_str).first()

                if existing:
                    skipped_count += 1
                    logger.debug("Skipping existing image: %s (id=%d)", filepath.name, existing.id)
                else:
                    # Import new image
                    result = importer.import_image(filepath)
                    if result:
                        imported_count += 1
                        logger.debug("Imported: %s (id=%d)", filepath.name, result.id)
                    else:
                        skipped_count += 1
                        logger.debug("Skipped (import failed): %s", filepath.name)

            except Exception as e:
                error_msg = f"{filepath}: {e}"
                errors.append(error_msg)
                logger.error("Error importing %s: %s", filepath, e, exc_info=True)

            # Batch commit every BATCH_SIZE images
            if i - batch_start_idx >= self.BATCH_SIZE:
                try:
                    self._session.commit()
                    logger.debug("Committed batch at file %d/%d", i, total_files)
                    batch_start_idx = i
                except Exception as e:
                    self._session.rollback()
                    error_msg = f"Batch commit failed at file {i}: {e}"
                    errors.append(error_msg)
                    logger.error("Batch commit failed at file %d: %s", i, e, exc_info=True)

        # Final commit for remaining files
        if imported_count > 0 or skipped_count > 0:
            try:
                self._session.commit()
                logger.debug("Final commit after importing %d files", total_files)
            except Exception as e:
                self._session.rollback()
                error_msg = f"Final commit failed: {e}"
                errors.append(error_msg)
                logger.error("Final commit failed: %s", e, exc_info=True)

        return {
            "imported": imported_count,
            "skipped": skipped_count,
            "errors": errors,
            "total": total_files,
        }

    def validate_directory(self, directory: str | Path) -> Dict[str, Any]:
        """Validate a directory for MMSSTV import.

        Checks if directory exists and contains importable images.
        Does NOT import anything, just scans and reports.

        Args:
            directory: Path to directory

        Returns:
            Dictionary with validation results:
                - valid: bool (True if directory can be imported)
                - exists: bool (Directory exists)
                - is_directory: bool (Path is a directory)
                - image_count: int (Number of importable images found)
                - error: str or None (Error message if validation failed)
        """
        directory = Path(directory)

        result: Dict[str, Any] = {
            "valid": False,
            "exists": directory.exists(),
            "is_directory": directory.is_dir() if directory.exists() else False,
            "image_count": 0,
            "error": None,
        }

        # Check existence
        if not result["exists"]:
            result["error"] = f"Directory does not exist: {directory}"
            return result

        # Check if directory
        if not result["is_directory"]:
            result["error"] = f"Path is not a directory: {directory}"
            return result

        # Scan for images
        try:
            image_files = self._scan_directory(directory, recursive=True)
            result["image_count"] = len(image_files)

            if result["image_count"] == 0:
                result["error"] = "No importable images found in directory"
            else:
                result["valid"] = True

        except Exception as e:
            result["error"] = f"Failed to scan directory: {e}"
            logger.error("Failed to validate directory %s: %s", directory, e, exc_info=True)

        return result

    def get_import_preview(
        self,
        directory: str | Path,
        max_samples: int = 10,
    ) -> Dict[str, Any]:
        """Get a preview of what would be imported from a directory.

        Scans directory and returns sample filenames with parsed metadata.
        Does NOT import anything.

        Args:
            directory: Path to directory
            max_samples: Maximum number of sample files to return (default 10)

        Returns:
            Dictionary with preview data:
                - total_files: int (Total importable images)
                - samples: List of dicts with parsed metadata
                - validation: Validation result from validate_directory()
        """
        directory = Path(directory)

        # Validate directory first
        validation = self.validate_directory(directory)

        if not validation["valid"]:
            return {
                "total_files": 0,
                "samples": [],
                "validation": validation,
            }

        # Scan directory
        image_files = self._scan_directory(directory, recursive=True)
        total_files = len(image_files)

        # Get sample files (evenly distributed)
        sample_indices = []
        if total_files <= max_samples:
            sample_indices = list(range(total_files))
        else:
            step = total_files / max_samples
            sample_indices = [int(i * step) for i in range(max_samples)]

        # Parse metadata for samples
        from sstv_core.filesystem.importer import parse_image_metadata

        samples = []
        for idx in sample_indices:
            filepath = image_files[idx]
            try:
                metadata = parse_image_metadata(filepath)
                samples.append({
                    "filename": filepath.name,
                    "path": str(filepath),
                    "metadata": metadata,
                })
            except Exception as e:
                logger.warning("Failed to parse sample file %s: %s", filepath, e)

        return {
            "total_files": total_files,
            "samples": samples,
            "validation": validation,
        }
