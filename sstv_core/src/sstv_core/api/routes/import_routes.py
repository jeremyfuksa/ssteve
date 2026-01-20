"""
Import endpoints for SSTeVe API.

Handles MMSSTV library import, directory validation, and import previews.
"""

import logging
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session

from sstv_core.api.models import (
    MMSStvImportRequest,
    MMSStvImportResponse,
    DirectoryValidationRequest,
    DirectoryValidationResponse,
    ImportPreviewResponse,
)
from sstv_core.filesystem import MMSStvImporter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/import", tags=["import"])


def get_db() -> Session:
    """Dependency to get database session.

    This will be overridden by the main app with the actual session factory.
    """
    # Placeholder - will be injected by main app
    raise NotImplementedError("Database session dependency not configured")


@router.post(
    "/mmsstv",
    response_model=MMSStvImportResponse,
    status_code=status.HTTP_200_OK,
    summary="Import MMSSTV library",
    description="""
Import SSTV images from an MMSSTV-compatible directory.

Scans the directory for image files (jpg, png, bmp) and imports them
to the database with automatic metadata extraction from filenames and EXIF.

Filenames should follow the format: YYYYMMDD_HHMMSS_MODE_CALLSIGN.jpg

The import is performed in batches (100 images per transaction) for efficiency.
Errors are logged but don't abort the entire import.

**Note:** Images already in the database (by filepath) will be skipped.
    """,
)
async def import_mmsstv_library(
    request: MMSStvImportRequest,
    session: Session = Depends(get_db),
) -> MMSStvImportResponse:
    """Import images from MMSSTV library directory.

    Args:
        request: Import request with directory path and options
        session: Database session (injected)

    Returns:
        Import result with statistics

    Raises:
        HTTPException 400: Invalid directory path
        HTTPException 404: Directory not found
        HTTPException 500: Import operation failed
    """
    directory = Path(request.directory_path)

    # Validate directory exists
    if not directory.exists():
        logger.warning("Import failed: directory not found: %s", directory)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Directory not found: {directory}",
        )

    # Validate is directory
    if not directory.is_dir():
        logger.warning("Import failed: path is not a directory: %s", directory)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Path is not a directory: {directory}",
        )

    logger.info(
        "Starting MMSSTV import: directory=%s, recursive=%s",
        directory,
        request.recursive,
    )

    try:
        # Create importer
        importer = MMSStvImporter(session)

        # Perform import
        result = importer.import_directory(
            directory=directory,
            recursive=request.recursive,
        )

        logger.info(
            "MMSSTV import completed: imported=%d, skipped=%d, errors=%d",
            result["imported"],
            result["skipped"],
            len(result["errors"]),
        )

        return MMSStvImportResponse(
            imported=result["imported"],
            skipped=result["skipped"],
            errors=result["errors"],
            total=result["total"],
        )

    except Exception as e:
        logger.error("MMSSTV import failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Import operation failed: {str(e)}",
        )


@router.post(
    "/validate",
    response_model=DirectoryValidationResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate directory for import",
    description="""
Validate that a directory exists and contains importable images.

This endpoint does NOT import anything - it just checks if the directory
is valid and reports how many images would be imported.

Use this before calling /import/mmsstv to verify the path.
    """,
)
async def validate_directory(
    request: DirectoryValidationRequest,
    session: Session = Depends(get_db),
) -> DirectoryValidationResponse:
    """Validate a directory for MMSSTV import.

    Args:
        request: Validation request with directory path
        session: Database session (injected)

    Returns:
        Validation result with image count and status

    Raises:
        HTTPException 500: Validation operation failed
    """
    directory = Path(request.directory_path)

    logger.debug("Validating directory for import: %s", directory)

    try:
        importer = MMSStvImporter(session)
        validation = importer.validate_directory(directory)

        logger.debug(
            "Directory validation: valid=%s, image_count=%d",
            validation["valid"],
            validation["image_count"],
        )

        return DirectoryValidationResponse(
            valid=validation["valid"],
            exists=validation["exists"],
            is_directory=validation["is_directory"],
            image_count=validation["image_count"],
            error=validation["error"],
        )

    except Exception as e:
        logger.error("Directory validation failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Validation operation failed: {str(e)}",
        )


@router.post(
    "/preview",
    response_model=ImportPreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Preview import from directory",
    description="""
Get a preview of what would be imported from a directory.

Returns validation status, total file count, and sample files with
parsed metadata. Does NOT import anything.

Sample files are evenly distributed across the directory to give a
representative preview of the import.
    """,
)
async def preview_import(
    request: DirectoryValidationRequest,
    session: Session = Depends(get_db),
) -> ImportPreviewResponse:
    """Get preview of MMSSTV import.

    Args:
        request: Preview request with directory path
        session: Database session (injected)

    Returns:
        Preview with sample files and validation

    Raises:
        HTTPException 500: Preview operation failed
    """
    directory = Path(request.directory_path)

    logger.debug("Getting import preview for: %s", directory)

    try:
        importer = MMSStvImporter(session)
        preview = importer.get_import_preview(directory, max_samples=10)

        logger.debug(
            "Import preview: total_files=%d, samples=%d",
            preview["total_files"],
            len(preview["samples"]),
        )

        return ImportPreviewResponse(
            total_files=preview["total_files"],
            samples=preview["samples"],
            validation=DirectoryValidationResponse(**preview["validation"]),
        )

    except Exception as e:
        logger.error("Import preview failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Preview operation failed: {str(e)}",
        )
