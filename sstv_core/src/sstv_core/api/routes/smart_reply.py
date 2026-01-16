"""Smart Reply API endpoints - Auto-populated proof-of-reception templates.

Provides endpoints for Smart Reply feature:
- List available templates
- Generate preview with auto-populated fields
- Transmit Smart Reply composite

Ref: backend-spec.md §6.4 (Smart Reply Technical Implementation)
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...database.models import get_or_create_config
from ...smart_features.field_populator import (
    FieldPopulationError,
    populate_smart_reply_fields,
    validate_smart_reply_fields,
)
from ...smart_features.template_engine import TemplateEngine, TemplateMetadata
from ..models import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/smart_reply", tags=["smart_reply"])

# Global template engine instance
_template_engine: Optional[TemplateEngine] = None


def get_template_engine() -> TemplateEngine:
    """Get or create template engine instance."""
    global _template_engine
    if _template_engine is None:
        _template_engine = TemplateEngine()
    return _template_engine


# =============================================================================
# Request/Response Models
# =============================================================================


class TemplateFieldInfo(BaseModel):
    """Template field metadata."""

    id: str
    label: str
    x: int
    y: int
    font_size: int
    color: str
    font_family: str = "Arial"
    alignment: str = "left"
    format: Optional[str] = None


class TemplateInfo(BaseModel):
    """Template metadata for API response."""

    template_id: str
    name: str
    default_mode: str
    base_image: str
    fields: List[TemplateFieldInfo]


class GenerateSmartReplyRequest(BaseModel):
    """Request to generate Smart Reply preview."""

    image_id: int = Field(..., description="Received image to reply to")
    template_id: str = Field(default="qsl_card", description="Template to use")
    field_overrides: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional manual overrides for specific fields"
    )


class GenerateSmartReplyResponse(BaseModel):
    """Response from Smart Reply generation."""

    preview_id: UUID = Field(..., description="Preview identifier for transmission")
    preview_image_path: str = Field(..., description="Path to preview image")
    template_data: Dict[str, Any] = Field(..., description="All field values used")
    estimated_tx_duration: int = Field(..., description="Estimated transmit duration in seconds")


class TransmitSmartReplyRequest(BaseModel):
    """Request to transmit Smart Reply."""

    mode: str = Field(..., description="SSTV mode (ScottieS1, MartinM1, Robot36)")
    device_id: str = Field(..., description="Audio output device ID")
    ptt_method: str = Field(..., description="PTT method (none, serial, vox)")


class TransmitSmartReplyResponse(BaseModel):
    """Response from Smart Reply transmission."""

    tx_id: UUID = Field(..., description="Transmit session ID")
    status: str = Field(..., description="Transmission status")


# In-memory preview storage (temporary files + metadata)
_preview_cache: Dict[UUID, Dict[str, Any]] = {}


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/templates", response_model=List[TemplateInfo])
async def list_templates(
    template_engine: TemplateEngine = Depends(get_template_engine)
) -> List[TemplateInfo]:
    """List all available Smart Reply templates.

    Returns bundled templates and user-created templates from ~/.ssteve/templates/

    Returns:
        List of template metadata
    """
    templates = template_engine.list_templates()

    # Convert to response model
    template_list = []
    for template in templates:
        template_info = TemplateInfo(
            template_id=template.template_id,
            name=template.name,
            default_mode=template.default_mode,
            base_image=template.base_image,
            fields=[
                TemplateFieldInfo(
                    id=field.id,
                    label=field.label,
                    x=field.x,
                    y=field.y,
                    font_size=field.font_size,
                    color=field.color,
                    font_family=field.font_family,
                    alignment=field.alignment,
                    format=field.format,
                )
                for field in template.fields
            ],
        )
        template_list.append(template_info)

    return template_list


@router.post("/generate", response_model=GenerateSmartReplyResponse)
async def generate_smart_reply(
    request: GenerateSmartReplyRequest,
    db: Session = Depends(get_db),
    template_engine: TemplateEngine = Depends(get_template_engine),
) -> GenerateSmartReplyResponse:
    """Generate Smart Reply preview with auto-populated fields.

    Auto-populates template fields from image metadata using fallback hierarchy:
    1. User override (manual entry)
    2. Image metadata (callsign, frequency, SNR from decode)
    3. Configuration defaults (operator callsign)
    4. Placeholder text ("N/A", "Unknown")

    Args:
        request: Generation request with image_id, template_id, and optional overrides
        db: Database session
        template_engine: Template engine instance

    Returns:
        Preview information with path and populated fields

    Raises:
        HTTPException: If image not found, template missing, or callsign required
    """
    try:
        # Populate fields from image metadata
        field_values = populate_smart_reply_fields(
            session=db,
            image_id=request.image_id,
            overrides=request.field_overrides
        )

        # Validate fields
        is_valid, errors = validate_smart_reply_fields(field_values)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid field values: {', '.join(errors)}"
            )

        # Render template
        preview_path = template_engine.render_template(
            template_id=request.template_id,
            field_values=field_values
        )

        # Estimate transmit duration based on mode
        mode = field_values.get("mode", "ScottieS1")
        estimated_duration = _estimate_tx_duration(mode)

        # Store preview in cache
        preview_id = uuid4()
        _preview_cache[preview_id] = {
            "preview_path": preview_path,
            "template_id": request.template_id,
            "field_values": field_values,
            "mode": mode,
        }

        logger.info(f"Generated Smart Reply preview {preview_id} for image {request.image_id}")

        return GenerateSmartReplyResponse(
            preview_id=preview_id,
            preview_image_path=preview_path,
            template_data=field_values,
            estimated_tx_duration=estimated_duration,
        )

    except FieldPopulationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error generating Smart Reply: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate Smart Reply: {str(e)}"
        )


@router.post("/transmit/{preview_id}", response_model=TransmitSmartReplyResponse)
async def transmit_smart_reply(
    preview_id: UUID,
    request: TransmitSmartReplyRequest,
    db: Session = Depends(get_db),
) -> TransmitSmartReplyResponse:
    """Transmit Smart Reply preview image.

    Args:
        preview_id: Preview ID from generate endpoint
        request: Transmission parameters (mode, device, PTT)
        db: Database session

    Returns:
        Transmission session information

    Raises:
        HTTPException: If preview not found or transmission fails
    """
    # Get preview from cache
    preview_data = _preview_cache.get(preview_id)
    if preview_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preview not found: {preview_id}. Please generate a new preview."
        )

    preview_path = preview_data["preview_path"]

    # Verify preview file exists
    if not Path(preview_path).exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Preview image file not found. Please generate a new preview."
        )

    try:
        # TODO: Integrate with actual transmit endpoint
        # For now, return a mock response
        tx_id = uuid4()

        logger.info(f"Starting Smart Reply transmission {tx_id} for preview {preview_id}")

        # Clean up preview from cache after starting transmission
        # (actual file cleanup should happen after TX completes)
        # _preview_cache.pop(preview_id, None)

        return TransmitSmartReplyResponse(
            tx_id=tx_id,
            status="transmitting"
        )

    except Exception as e:
        logger.error(f"Error transmitting Smart Reply: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start transmission: {str(e)}"
        )


@router.post("/reload_templates")
async def reload_templates(
    template_engine: TemplateEngine = Depends(get_template_engine)
) -> Dict[str, Any]:
    """Hot-reload templates from disk.

    Useful for adding new templates without restarting the server.

    Returns:
        Status with count of loaded templates
    """
    template_engine.reload_templates()
    templates = template_engine.list_templates()

    return {
        "status": "reloaded",
        "count": len(templates),
        "templates": [t.name for t in templates],
    }


# =============================================================================
# Helper Functions
# =============================================================================


def _estimate_tx_duration(mode: str) -> int:
    """Estimate transmit duration in seconds for a given mode.

    Args:
        mode: SSTV mode name

    Returns:
        Estimated duration in seconds
    """
    # Approximate durations for common modes (320x256 image)
    mode_durations = {
        "ScottieS1": 110,  # ~1:50
        "ScottieS2": 71,   # ~1:11
        "MartinM1": 114,   # ~1:54
        "MartinM2": 58,    # ~0:58
        "Robot36": 36,     # ~0:36
        "Robot72": 72,     # ~1:12
    }

    return mode_durations.get(mode, 120)  # Default 2 minutes
