"""
Configuration endpoints.

Handles:
- GET /config - Get current configuration
- POST /config - Replace entire configuration
- PATCH /config - Update specific configuration fields
"""

from typing import Dict, Any

from fastapi import APIRouter, HTTPException, status

from sstv_core.api.models import Configuration


router = APIRouter(prefix="/config", tags=["config"])


# In-memory config storage for now (will be replaced with database)
_config = Configuration()


@router.get("", response_model=Configuration)
async def get_config() -> Configuration:
    """
    Get the current system configuration.

    Returns all configuration settings including:
    - Audio device selections
    - PTT method and settings
    - Default SSTV mode
    - Image library path
    - Operating mode (standard/night vision/sunlight)
    - Auto-detection settings (mode, AFC, squelch)
    """
    return _config


@router.post("", response_model=Configuration)
async def update_config(config: Configuration) -> Configuration:
    """
    Replace the entire configuration.

    Updates all configuration settings at once. Any fields not provided
    will be reset to their defaults.

    Raises:
        400 Bad Request: If configuration is invalid (e.g., serial PTT without port)
    """
    global _config
    _config = config
    # TODO: Persist to database
    return _config


@router.patch("", response_model=Configuration)
async def patch_config(updates: Dict[str, Any]) -> Configuration:
    """
    Update specific configuration fields.

    Only the provided fields will be updated; others remain unchanged.
    This is useful for changing individual settings without replacing
    the entire configuration.

    Example:
        PATCH /config
        {"ptt_method": "serial_rts", "ptt_serial_port": "/dev/ttyUSB0"}

    Raises:
        400 Bad Request: If update would create invalid configuration
    """
    global _config

    # Create updated config by merging
    current_dict = _config.model_dump()
    current_dict.update(updates)

    try:
        _config = Configuration(**current_dict)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "VALIDATION_ERROR",
                "message": f"Can't apply config update: {str(e)}",
                "suggested_action": "Check the field values and try again",
            },
        )

    # TODO: Persist to database
    return _config
