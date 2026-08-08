"""Field Auto-Population for Smart Reply templates.

This module implements the fallback hierarchy for populating Smart Reply fields:
1. User override (manual entry in preview dialog)
2. Image metadata (callsign, frequency, SNR from decode)
3. Placeholder text ("N/A", "Unknown")

(A configuration tier existed on paper but read columns that were never
created; removed 2026-08-07.)
"""

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ..database.models import SSTVImage


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

    # Build field values with fallback hierarchy
    fields = {
        # Critical field: Their callsign (must be present)
        "callsign_received": overrides.get("callsign_received")
                            or image.callsign
                            or None,  # Will raise error below if None

        # Your callsign. There is no station-callsign column in
        # configuration (the old code read `config.station_callsign`, which
        # never existed, so this was always the placeholder); callers must
        # pass it as an override until such a setting exists.
        "callsign_operator": overrides.get("callsign_operator") or "YOUR_CALL",

        # Frequency: override wins, then the image's own metadata. (The old
        # expression ended in a low-precedence conditional on a config
        # column that never existed, which evaluated the WHOLE chain --
        # including the explicit override -- to None every time.)
        "frequency_mhz": (
            overrides.get("frequency_mhz")
            or (image.frequency_hz / 1e6 if image.frequency_hz else None)
        ),

        # Timestamp (always from image)
        "timestamp_utc": image.timestamp,

        # SNR in dB, from the column that actually holds dB. The old code
        # read rx_quality_score -- a 0-1 quality number -- and templates
        # rendered it as "SNR: 0dB".
        "snr_db": overrides.get("snr_db")
                 or getattr(image, "rx_snr_db", None)
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
        # There is no station-callsign setting yet; pointing users at
        # Settings was a dead end.
        suggestions["callsign_operator"] = (
            "Pass callsign_operator when generating the reply -- "
            "I don't have a station callsign setting yet"
        )

    if fields.get("frequency_mhz") is None or fields.get("frequency_mhz") == "N/A":
        suggestions["frequency_mhz"] = (
            "Add frequency to the image metadata, or pass frequency_mhz directly"
        )

    if fields.get("snr_db") == "N/A":
        suggestions["snr_db"] = "Signal quality not available (decode metadata missing)"

    return suggestions
