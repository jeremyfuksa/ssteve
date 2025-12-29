"""
Image gallery endpoints.

Handles:
- GET /images - List images with pagination and filtering
- GET /images/{id} - Get specific image metadata
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from sstv_core.api.models import ImageMetadata, ImageListResponse, SSTVMode


router = APIRouter(prefix="/images", tags=["images"])


# Mock image storage (will be replaced with database queries)
_images: List[ImageMetadata] = []


@router.get("", response_model=ImageListResponse)
async def list_images(
    limit: int = Query(default=20, ge=1, le=100, description="Number of images per page"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    direction: Optional[str] = Query(default=None, pattern="^(rx|tx)$", description="Filter by direction"),
    mode: Optional[SSTVMode] = Query(default=None, description="Filter by SSTV mode"),
    callsign: Optional[str] = Query(default=None, description="Filter by callsign"),
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
    # Apply filters
    filtered = _images

    if direction:
        filtered = [img for img in filtered if img.direction == direction]

    if mode:
        filtered = [img for img in filtered if img.mode == mode]

    if callsign:
        callsign_upper = callsign.upper()
        filtered = [
            img for img in filtered
            if img.callsign and img.callsign.upper() == callsign_upper
        ]

    # Sort by timestamp descending (newest first)
    filtered.sort(key=lambda x: x.timestamp, reverse=True)

    # Apply pagination
    total = len(filtered)
    paginated = filtered[offset:offset + limit]

    return ImageListResponse(
        images=paginated,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{image_id}", response_model=ImageMetadata)
async def get_image(image_id: UUID) -> ImageMetadata:
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
    for img in _images:
        if img.id == image_id:
            return img

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error": "IMAGE_NOT_FOUND",
            "message": f"Can't find image {image_id}",
            "suggested_action": "Check the image ID or browse the gallery",
        },
    )
