"""Field Auto-Population for Smart Reply templates.

This module implements the fallback hierarchy for populating Smart Reply fields:
1. User override (manual entry in preview dialog)
2. Image metadata (callsign, frequency, SNR from decode)
3. Configuration defaults (operator callsign from settings)
4. Placeholder text ("N/A", "Unknown")
"""

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ..database.models import SSTVImage, get_or_create_config


class FieldPopulationError(Exception):
    """Raised when critical field is missing and cannot be populated."""

    pass


def populate_smart_reply_fields(
    session: Session,
    image_id: int,
    overrides: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Auto-populate template fields from image metadata with fallback hierarchy.

    Args:
        session: Active database session
        image_id: ID of received image to reply to
        overrides: Optional user-provided overrides for specific fields

    Returns:
        Dictionary of field_id -> value for all template fields

    Raises:
        FieldPopulationError: If callsign_received cannot be determined
        ValueError: If image not found

    """
    if overrides is None:
        overrides = {}

    # Fetch image metadata
    image = session.get(SSTVImage, image_id)
    if image is None:
        raise ValueError(f"Image not found: {image_id}")

    # Fetch configuration
    config = get_or_create_config(session)

    # Build field values with fallback hierarchy
    fields = {
        # Critical field: Their callsign (must be present)
        "callsign_received": overrides.get("callsign_received")
                            or image.callsign
                            or None,  # Will raise error below if None

        # Your callsign (fallback to config or placeholder)
        "callsign_operator": overrides.get("callsign_operator")
                            or getattr(config, "station_callsign", None)
                            or "YOUR_CALL",

        # Frequency (from image metadata or config default)
        "frequency_mhz": (
            overrides.get("frequency_mhz")
            or (image.frequency_hz / 1e6 if image.frequency_hz else None)
            or getattr(config, "default_frequency_hz", 0.0) / 1e6
            if hasattr(config, "default_frequency_hz")
            else None
        ),

        # Timestamp (always from image)
        "timestamp_utc": image.timestamp,

        # SNR/Signal quality (from decode metadata)
        "snr_db": overrides.get("snr_db")
                 or image.rx_quality_score
                 or "N/A",

        # Mode (always from image)
        "mode": image.mode,

        # Operator name (if available)
        "operator_name": overrides.get("operator_name")
                        or image.operator_name
                        or None,
    }

    # Critical validation: callsign_received must be present
    if not fields["callsign_received"] or fields["callsign_received"] == "UNKNOWN":
        raise FieldPopulationError(
            "Callsign required for Smart Reply. Please enter the callsign manually."
        )

    # Format values for display
    formatted_fields = _format_field_values(fields)

    return formatted_fields


def _format_field_values(fields: dict[str, Any]) -> dict[str, Any]:
    """Format field values for display in template.

    Args:
        fields: Raw field values

    Returns:
        Dictionary with formatted values

    """
    formatted: dict[str, Any] = {}

    for key, value in fields.items():
        if value is None:
            formatted[key] = "N/A"
        elif key == "frequency_mhz" and isinstance(value, (int, float)):
            # Format frequency with 3 decimal places
            formatted[key] = value
        elif key == "timestamp_utc" and isinstance(value, datetime):
            # Keep datetime object for format string handling
            formatted[key] = value
        elif key == "snr_db" and isinstance(value, (int, float)):
            # Format SNR as integer dB value
            formatted[key] = int(value) if value != "N/A" else "N/A"
        else:
            formatted[key] = value

    return formatted


def validate_smart_reply_fields(fields: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate that all required fields are present and valid.

    Args:
        fields: Dictionary of field_id -> value

    Returns:
        Tuple of (is_valid, list_of_errors)

    """
    errors = []

    # Required fields
    required_fields = ["callsign_received", "callsign_operator", "mode"]

    for field_id in required_fields:
        value = fields.get(field_id)
        if not value or value in ("N/A", "UNKNOWN", "YOUR_CALL"):
            errors.append(f"Required field missing or invalid: {field_id}")

    # Validate callsign format (basic validation)
    for callsign_field in ["callsign_received", "callsign_operator"]:
        callsign = fields.get(callsign_field)
        if callsign and callsign not in ("N/A", "UNKNOWN", "YOUR_CALL"):
            # Basic callsign validation: 3-10 alphanumeric characters
            if not (
                3 <= len(callsign) <= 10
                and callsign.replace("/", "").replace("-", "").isalnum()
            ):
                errors.append(f"Invalid callsign format: {callsign}")

    is_valid = len(errors) == 0
    return is_valid, errors


def suggest_field_improvements(fields: dict[str, Any]) -> dict[str, str]:
    """Suggest improvements for field values that are present but suboptimal.

    Args:
        fields: Dictionary of field_id -> value

    Returns:
        Dictionary of field_id -> suggestion_text

    """
    suggestions = {}

    # Check for placeholder values
    if fields.get("callsign_operator") == "YOUR_CALL":
        suggestions["callsign_operator"] = "Configure your callsign in Settings for auto-population"

    if fields.get("frequency_mhz") is None or fields.get("frequency_mhz") == "N/A":
        suggestions["frequency_mhz"] = (
            "Add frequency to image metadata or configure default frequency"
        )

    if fields.get("snr_db") == "N/A":
        suggestions["snr_db"] = "Signal quality not available (decode metadata missing)"

    return suggestions
