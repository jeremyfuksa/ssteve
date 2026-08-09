"""Image gallery endpoints.

Handles:
- GET /images - List images with pagination and filtering
- GET /images/{id} - Get specific image metadata
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from sstv_core.api.image_ids import db_image_id_to_uuid
from sstv_core.api.image_lookup import resolve_image_uuid
from sstv_core.api.main import get_db_session
from sstv_core.api.models import ImageListResponse, ImageMetadata, SSTVMode

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/images", tags=["images"])


def _db_image_to_api(db_image) -> ImageMetadata:
    """Convert database SSTVImage to API ImageMetadata model."""
    from PIL import Image

    # Determine direction
    direction = "rx" if db_image.is_received else "tx"

    # Unknown mode strings stay unknown -- coercing them to MartinM1 (the
    # old behavior) fabricated data.
    try:
        mode = SSTVMode(db_image.mode)
    except ValueError:
        mode = None

    # Dimensions come from the file or not at all.
    width = height = None
    try:
        with Image.open(db_image.filepath) as img:
            width, height = img.size
    except Exception:
        logger.debug("Couldn't read image dimensions from %s", db_image.filepath)

    return ImageMetadata(
        id=db_image_id_to_uuid(db_image.id),
        filepath=db_image.filepath,
        mode=mode,
        direction=direction,
        callsign=db_image.callsign,
        timestamp=db_image.timestamp,
        # rx_snr_db is the dB column; rx_quality_score is a 0-1 number and
        # was previously served here as dB.
        snr_db=db_image.rx_snr_db,
        frequency_hz=db_image.frequency_hz,
        width=width,
        height=height,
        filename=db_image.filename,
        rx_quality_score=db_image.rx_quality_score,
        # Auto-RSV and FSKID: persisted since PRs #38/#41, dropped here
        # until 2026-08-09. Null stays null -- nothing is fabricated for
        # TX images or for decodes that predate these columns.
        rsv_readability=db_image.rsv_readability,
        rsv_signal=db_image.rsv_signal,
        rsv_video=db_image.rsv_video,
        rsv_report=db_image.rsv_report,
        peak_amplitude=db_image.rx_peak_amplitude,
        noise_floor=db_image.rx_noise_floor,
        fskid_detected=db_image.fskid_detected,
        fskid_confidence=db_image.fskid_confidence,
        fskid_checksum_valid=db_image.fskid_checksum_valid,
    )


@router.get("", response_model=ImageListResponse)
async def list_images(
    limit: int = Query(default=20, ge=1, le=100, description="Number of images per page"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    direction: str | None = Query(
        default=None, pattern="^(rx|tx)$", description="Filter by direction"
    ),
    mode: SSTVMode | None = Query(default=None, description="Filter by SSTV mode"),
    callsign: str | None = Query(default=None, description="Filter by callsign"),
    session: Session = Depends(get_db_session),
) -> ImageListResponse:
    """List images with pagination and optional filtering.

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
    """Get metadata for a specific image.

    Returns detailed information about the image including:
    - File path and dimensions
    - SSTV mode used
    - Direction (RX/TX)
    - Signal quality metrics (for RX images)
    - Timestamp and callsign

    Raises:
        404 Not Found: If image doesn't exist

    """
    db_image = resolve_image_uuid(session, image_id)
    if db_image is not None:
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
