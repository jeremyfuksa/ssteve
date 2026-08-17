"""Smart Reply API endpoints - Auto-populated proof-of-reception templates.

Provides endpoints for Smart Reply feature:
- List available templates
- Generate preview with auto-populated fields
- Transmit Smart Reply composite

Ref: backend-spec.md §6.4 (Smart Reply Technical Implementation)
"""

import logging
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...smart_features.field_populator import (
    FieldPopulationError,
    populate_smart_reply_fields,
    validate_smart_reply_fields,
    )
from ...smart_features.template_engine import TemplateEngine
from ..dsp_manager import dsp_manager
from ..image_lookup import resolve_image_uuid
from ..models import TransmitState
from ..session_manager import concurrent_operation_detail, session_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/smart_reply", tags=["smart_reply"])

def get_db() -> Session:
    """Dependency to get database session.

    This will be overridden by the main app with the actual session factory.
    """
    # Placeholder - will be injected by main app
    raise NotImplementedError("Database session dependency not configured")

# Global template engine instance
_template_engine: TemplateEngine | None = None


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
    format: str | None = None


class TemplateInfo(BaseModel):
    """Template metadata for API response."""

    template_id: str
    name: str
    default_mode: str
    base_image: str
    fields: list[TemplateFieldInfo]


class GenerateSmartReplyRequest(BaseModel):
    """Request to generate Smart Reply preview."""

    image_id: UUID = Field(
        ..., description="Received image to reply to (public UUID)"
    )
    template_id: str = Field(default="qsl_card", description="Template to use")
    field_overrides: dict[str, Any] | None = Field(
        default=None,
        description="Optional manual overrides for specific fields"
    )


class GenerateSmartReplyResponse(BaseModel):
    """Response from Smart Reply generation."""

    preview_id: UUID = Field(..., description="Preview identifier for transmission")
    preview_image_path: str = Field(..., description="Path to preview image")
    template_data: dict[str, Any] = Field(..., description="All field values used")
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
_preview_cache: dict[UUID, dict[str, Any]] = {}


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/templates", response_model=list[TemplateInfo])
async def list_templates(
    template_engine: TemplateEngine = Depends(get_template_engine)
) -> list[TemplateInfo]:
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
    db_image = resolve_image_uuid(db, request.image_id)
    if db_image is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "IMAGE_NOT_FOUND",
                "message": f"I can't find image {request.image_id}.",
                "suggested_action": "GET /images lists what's in the library.",
            },
        )

    try:
        # Populate fields from image metadata
        field_values = populate_smart_reply_fields(
            session=db,
            image_id=db_image.id,
            overrides=request.field_overrides
        )

        # Validate fields
        is_valid, errors = validate_smart_reply_fields(field_values)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "INVALID_FIELD_VALUES",
                    "message": f"Some of those fields didn't check out: {', '.join(errors)}",
                    "suggested_action": "Correct the fields it names and try again.",
                }
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
            detail={
                "error": "FIELD_POPULATION_FAILED",
                "message": f"I couldn't fill in the reply fields: {e!s}",
                "suggested_action": "Supply the missing values in the request and try again.",
            }
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "INVALID_REPLY_REQUEST",
                "message": f"I can't build a reply from that: {e!s}",
                "suggested_action": "Check the template name and field values.",
            }
        ) from e
    except Exception as e:
        logger.error(f"Error generating Smart Reply: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "SMART_REPLY_FAILED",
                "message": f"I couldn't build that Smart Reply: {e!s}",
                "suggested_action": "Nothing was transmitted. Try again, or pick another template.",
            }
        ) from e


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
            detail={
                "error": "PREVIEW_NOT_FOUND",
                "message": f"I don't have a preview with ID {preview_id} anymore.",
                "suggested_action": "Previews are short-lived -- generate a new one.",
            }
        )

    preview_path = preview_data["preview_path"]

    # Verify preview file exists
    if not Path(preview_path).exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "PREVIEW_FILE_MISSING",
                "message": "That preview's image file is gone from disk.",
                "suggested_action": "Generate a new preview.",
            }
        )

    # A real transmit session through the same half-duplex machinery as
    # POST /transmit. Until 2026-08-07 this endpoint fabricated a tx_id and
    # "transmitting" status without touching any hardware; the returned ID
    # 404'd on /transmit/status.
    try:
        session = await session_manager.create_transmit_session(
            metadata={
                "image_path": preview_path,
                "mode": request.mode,
                "smart_reply_preview_id": str(preview_id),
            }
        )
        await dsp_manager.start_transmit(
            session_id=session.session_id,
            image_path=preview_path,
            mode=request.mode,
            device_id=request.device_id,
            vox_enabled=request.ptt_method == "vox",
            serial_port=None,
        )

        logger.info(
            "Started Smart Reply transmission %s for preview %s",
            session.session_id,
            preview_id,
        )
        return TransmitSmartReplyResponse(
            tx_id=session.session_id,
            status="transmitting",
        )

    except ValueError as e:
        await _fail_session_quietly(locals().get("session"))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "INVALID_TRANSMIT_REQUEST",
                "message": f"I can't transmit that preview: {e!s}",
                "suggested_action": "The radio was not keyed. Regenerate the preview and retry.",
            },
        ) from e
    except RuntimeError as e:
        await _fail_session_quietly(locals().get("session"))
        if "already active" in str(e) or "half-duplex" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=concurrent_operation_detail(str(e)),
            ) from e
        raise
    except Exception as e:
        await _fail_session_quietly(locals().get("session"))
        logger.error(f"Error transmitting Smart Reply: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "TRANSMIT_START_FAILED",
                "message": f"I couldn't start that transmission: {e!s}",
                "suggested_action": "The radio was not keyed. Check your PTT and audio settings.",
            }
        ) from e


@router.post("/reload_templates")
async def reload_templates(
    template_engine: TemplateEngine = Depends(get_template_engine)
) -> dict[str, Any]:
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


async def _fail_session_quietly(session: Any) -> None:
    """Release the half-duplex lock on a just-created transmit session.

    Marks the session FAILED and stops any DSP work; never raises.
    """
    if session is None:
        return
    try:
        await session_manager.update_transmit_state(
            session.session_id, TransmitState.FAILED
        )
        await dsp_manager.stop_transmit(session.session_id)
    except Exception:  # pragma: no cover - best-effort cleanup
        logger.warning("Could not clean up failed smart-reply session")
