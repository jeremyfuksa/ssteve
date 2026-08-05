"""
Image gallery endpoints.

Handles:
- GET /images - List images with pagination and filtering
- GET /images/{id} - Get specific image metadata
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from sstv_core.api.main import get_db_session
from sstv_core.api.image_ids import db_image_id_to_uuid

from sstv_core.api.models import ImageMetadata, ImageListResponse, SSTVMode


router = APIRouter(prefix="/images", tags=["images"])


def _db_image_to_api(db_image) -> ImageMetadata:
    """Convert database SSTVImage to API ImageMetadata model."""
    from PIL import Image

    # Determine direction
    direction = "rx" if db_image.is_received else "tx"

    # Parse mode enum
    try:
        mode = SSTVMode(db_image.mode)
    except ValueError:
        mode = SSTVMode.MARTIN_M1  # Default fallback

    # Get image dimensions from file
    width = 320
    height = 256
    try:
        with Image.open(db_image.filepath) as img:
            width, height = img.size
    except Exception:
        pass  # Use defaults if can't read file

    return ImageMetadata(
        id=db_image_id_to_uuid(db_image.id),
        filepath=db_image.filepath,
        mode=mode,
        direction=direction,
        callsign=db_image.callsign,
        timestamp=db_image.timestamp,
        snr_db=db_image.rx_quality_score,
        frequency_offset_hz=db_image.frequency_hz,
        width=width,
        height=height,
    )


@router.get("", response_model=ImageListResponse)
async def list_images(
    limit: int = Query(default=20, ge=1, le=100, description="Number of images per page"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    direction: Optional[str] = Query(default=None, pattern="^(rx|tx)$", description="Filter by direction"),
    mode: Optional[SSTVMode] = Query(default=None, description="Filter by SSTV mode"),
    callsign: Optional[str] = Query(default=None, description="Filter by callsign"),
    session: Session = Depends(get_db_session),
) -> ImageListResponse:
    """
    List images with pagination and optional filtering.

    Supports filtering by:
    - Direction: "rx" (received) or "tx" (transmitted)
    - Mode: SSTV mode (e.g., "MartinM1", "ScottieS1")
    - Callsign: Operator callsign

    Images are returned in reverse chronological order (newest first).

    Query Parameters:
        limit: Number of images per page (1-100, default: 20)
        offset: Pagination offset (default: 0)
        direction: Filter by "rx" or "tx"
        mode: Filter by SSTV mode
        callsign: Filter by operator callsign
    """
    from sstv_core.database.models import SSTVImage
    
    # Build query
    query = session.query(SSTVImage)

    # Apply filters
    if direction:
        is_received = (direction == "rx")
        query = query.filter(SSTVImage.is_received == is_received)

    if mode:
        query = query.filter(SSTVImage.mode == mode.value)

    if callsign:
        # Case-insensitive callsign match
        query = query.filter(SSTVImage.callsign.ilike(f"%{callsign}%"))

    # Get total count before pagination
    total = query.count()

    # Sort by timestamp descending (newest first) and paginate
    images_db = (
        query.order_by(desc(SSTVImage.timestamp))
        .offset(offset)
        .limit(limit)
        .all()
    )

    # Convert to API models
    images_api = [_db_image_to_api(img) for img in images_db]

    return ImageListResponse(
        images=images_api,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{image_id}", response_model=ImageMetadata)
async def get_image(
    image_id: UUID,
    session: Session = Depends(get_db_session),
) -> ImageMetadata:
    """
    Get metadata for a specific image.

    Returns detailed information about the image including:
    - File path and dimensions
    - SSTV mode used
    - Direction (RX/TX)
    - Signal quality metrics (for RX images)
    - Timestamp and callsign

    Raises:
        404 Not Found: If image doesn't exist
    """
    from sstv_core.database.models import SSTVImage
    
    # Since UUIDs are deterministic (uuid5), we need to find matching database entry
    # TODO: Add UUID column to database for efficient lookups
    all_images = session.query(SSTVImage).all()
    
    for db_image in all_images:
        if db_image_id_to_uuid(db_image.id) == image_id:
            return _db_image_to_api(db_image)
    
    # Not found
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error": "IMAGE_NOT_FOUND",
            "message": f"Can't find image {image_id}",
            "suggested_action": "Check the image ID or browse the gallery",
        },
    )
