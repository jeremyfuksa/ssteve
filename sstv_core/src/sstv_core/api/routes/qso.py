"""QSO Logging API endpoints - Smart QSO logging with ADIF export.

Provides endpoints for QSO logging feature:
- Create QSO with auto-populated fields
- List QSOs with filtering
- Export QSOs to ADIF format

Ref: backend-spec.md §6.3 (Smart QSO Logging)
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...database.models import QSO
from ...smart_features.qso_logger import (
    create_qso_with_image,
    export_qsos_to_adif,
    populate_qso_from_image,
    suggest_qso_improvements,
    validate_callsign,
    )

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/qso", tags=["qso"])

def get_db() -> Session:
    """Dependency to get database session.

    This will be overridden by the main app with the actual session factory.
    """
    # Placeholder - will be injected by main app
    raise NotImplementedError("Database session dependency not configured")


# =============================================================================
# Request/Response Models
# =============================================================================


class LogQSORequest(BaseModel):
    """Request to log a QSO."""

    image_id: int = Field(..., description="Image ID to create QSO from")
    callsign: Optional[str] = Field(None, description="Override callsign")
    mode: Optional[str] = Field(None, description="Override mode")
    frequency_hz: Optional[float] = Field(None, description="Override frequency")
    start_time: Optional[datetime] = Field(None, description="Override start time")
    end_time: Optional[datetime] = Field(None, description="Override end time")
    report: Optional[str] = Field(None, description="Override signal report")
    comments: Optional[str] = Field(None, description="Additional comments")
    is_sent: Optional[bool] = Field(False, description="True if we initiated contact")


class QSOResponse(BaseModel):
    """QSO record response."""

    id: int
    callsign: str
    mode: str
    frequency_hz: Optional[float]
    start_time: datetime
    end_time: Optional[datetime]
    report: Optional[str]
    comments: Optional[str]
    is_sent: bool
    image_ids: List[int] = Field(default_factory=list)


class QSOListResponse(BaseModel):
    """Paginated QSO list response."""

    qsos: List[QSOResponse]
    total: int
    limit: int
    offset: int


class ExportADIFRequest(BaseModel):
    """Request to export QSOs to ADIF."""

    start_date: Optional[datetime] = Field(None, description="Start date filter")
    end_date: Optional[datetime] = Field(None, description="End date filter")
    callsign_filter: Optional[str] = Field(None, description="Callsign substring filter")


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/log", response_model=QSOResponse, status_code=status.HTTP_201_CREATED)
async def log_qso(
    request: LogQSORequest,
    db: Session = Depends(get_db),
) -> QSOResponse:
    """Log a QSO with auto-populated fields from image metadata.

    Auto-populates fields from image metadata using fallback hierarchy:
    1. User override (from request)
    2. Image metadata (from decode)
    3. None/empty

    Args:
        request: QSO logging request with image_id and optional overrides
        db: Database session

    Returns:
        Created QSO record

    Raises:
        HTTPException: If image not found or callsign missing/invalid
    """
    try:
        # Build overrides from request
        overrides = {}
        if request.callsign:
            overrides["callsign"] = request.callsign
        if request.mode:
            overrides["mode"] = request.mode
        if request.frequency_hz:
            overrides["frequency_hz"] = request.frequency_hz
        if request.start_time:
            overrides["start_time"] = request.start_time
        if request.end_time:
            overrides["end_time"] = request.end_time
        if request.report:
            overrides["report"] = request.report
        if request.comments:
            overrides["comments"] = request.comments
        if request.is_sent is not None:
            overrides["is_sent"] = request.is_sent

        # Populate QSO fields
        qso_fields = populate_qso_from_image(
            session=db,
            image_id=request.image_id,
            overrides=overrides
        )

        # Validate callsign
        if not validate_callsign(qso_fields["callsign"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid callsign format: {qso_fields['callsign']}"
            )

        # Create QSO and link to image
        qso = create_qso_with_image(
            session=db,
            image_id=request.image_id,
            qso_fields=qso_fields
        )

        logger.info(f"Created QSO {qso.id} for {qso.callsign}")

        # Convert to response
        return QSOResponse(
            id=qso.id,
            callsign=qso.callsign,
            mode=qso.mode,
            frequency_hz=qso.frequency_hz,
            start_time=qso.start_time,
            end_time=qso.end_time,
            report=qso.report,
            comments=qso.comments,
            is_sent=qso.is_sent,
            image_ids=[request.image_id],
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error logging QSO: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to log QSO: {str(e)}"
        )


@router.get("/list", response_model=QSOListResponse)
async def list_qsos(
    limit: int = 50,
    offset: int = 0,
    callsign_filter: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
) -> QSOListResponse:
    """List QSOs with filtering and pagination.

    Args:
        limit: Maximum number of QSOs to return
        offset: Offset for pagination
        callsign_filter: Optional callsign substring filter
        start_date: Optional start date filter
        end_date: Optional end date filter
        db: Database session

    Returns:
        Paginated list of QSOs
    """
    # Build query
    query = db.query(QSO)

    if callsign_filter:
        query = query.filter(QSO.callsign.ilike(f"%{callsign_filter}%"))
    if start_date:
        query = query.filter(QSO.start_time >= start_date)
    if end_date:
        query = query.filter(QSO.start_time <= end_date)

    # Get total count
    total = query.count()

    # Apply pagination
    qsos = query.order_by(QSO.start_time.desc()).limit(limit).offset(offset).all()

    # Convert to response
    qso_list = [
        QSOResponse(
            id=qso.id,
            callsign=qso.callsign,
            mode=qso.mode,
            frequency_hz=qso.frequency_hz,
            start_time=qso.start_time,
            end_time=qso.end_time,
            report=qso.report,
            comments=qso.comments,
            is_sent=qso.is_sent,
            image_ids=[img.id for img in qso.images] if qso.images else [],
        )
        for qso in qsos
    ]

    return QSOListResponse(
        qsos=qso_list,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/export", response_class=PlainTextResponse)
async def export_adif(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    callsign_filter: Optional[str] = None,
    db: Session = Depends(get_db),
) -> Response:
    """Export QSOs to ADIF format.

    ADIF (Amateur Data Interchange Format) is the standard format for
    amateur radio logbook data exchange.

    Args:
        start_date: Optional start date filter
        end_date: Optional end date filter
        callsign_filter: Optional callsign substring filter
        db: Database session

    Returns:
        ADIF format file as plain text
    """
    try:
        adif_content = export_qsos_to_adif(
            session=db,
            start_date=start_date,
            end_date=end_date,
            callsign_filter=callsign_filter,
        )

        # Generate filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"ssteve_qsos_{timestamp}.adi"

        return Response(
            content=adif_content,
            media_type="text/plain",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except Exception as e:
        logger.error(f"Error exporting ADIF: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export ADIF: {str(e)}"
        )


@router.get("/{qso_id}", response_model=QSOResponse)
async def get_qso(
    qso_id: int,
    db: Session = Depends(get_db),
) -> QSOResponse:
    """Get single QSO by ID.

    Args:
        qso_id: QSO ID
        db: Database session

    Returns:
        QSO record

    Raises:
        HTTPException: If QSO not found
    """
    qso = db.get(QSO, qso_id)
    if qso is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"QSO not found: {qso_id}"
        )

    return QSOResponse(
        id=qso.id,
        callsign=qso.callsign,
        mode=qso.mode,
        frequency_hz=qso.frequency_hz,
        start_time=qso.start_time,
        end_time=qso.end_time,
        report=qso.report,
        comments=qso.comments,
        is_sent=qso.is_sent,
        image_ids=[img.id for img in qso.images] if qso.images else [],
    )


@router.delete("/{qso_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_qso(
    qso_id: int,
    db: Session = Depends(get_db),
) -> None:
    """Delete QSO by ID.

    Args:
        qso_id: QSO ID
        db: Database session

    Raises:
        HTTPException: If QSO not found
    """
    qso = db.get(QSO, qso_id)
    if qso is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"QSO not found: {qso_id}"
        )

    db.delete(qso)
    db.commit()

    logger.info(f"Deleted QSO {qso_id}")
