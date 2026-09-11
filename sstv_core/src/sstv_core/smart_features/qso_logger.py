"""Smart QSO Logging - Auto-populate QSO fields and export to ADIF.

This module handles intelligent QSO logging with auto-population from image metadata
and ADIF export for logbook integration.
"""

from datetime import datetime
from io import StringIO

from sqlalchemy.orm import Session

from ..database.models import QSO, QSOImage, SSTVImage


class RecordTypeError(ValueError):
    """A log entry that would claim more than the picture's provenance allows."""

    def __init__(self, message: str, suggested_action: str) -> None:
        super().__init__(message)
        self.suggested_action = suggested_action


def record_type_for(image: SSTVImage, requested: str | None) -> str:
    """Decide what kind of record a picture can become.

    The provenance on the image wins over the request. A picture heard at
    someone else's receiver is a remote reception whatever the operator
    asks for -- asking for "qso" is refused rather than quietly changed,
    so nobody believes they logged a contact they didn't.

    Unknown provenance (rows from before #69, imports) keeps today's
    behavior: the operator's word, defaulting to a contact.
    """
    if image.source == "sample":
        raise RecordTypeError(
            "That picture came from a sample recording, not the air, so "
            "there's nothing to log.",
            suggested_action="Log a picture you decoded off the air.",
        )
    if image.heard_at == "remote":
        if requested in (None, "remote_reception"):
            return "remote_reception"
        where = image.receiver or "someone else's receiver"
        raise RecordTypeError(
            f"{where} heard that picture, not your station, so I can only "
            "log it as a remote reception.",
            suggested_action=(
                "Log it as remote_reception. If that server really is your "
                "own receiver, add it to spyserver_my_stations -- that "
                "counts for decodes from then on, not this one."
            ),
        )
    return requested or "qso"


def populate_qso_from_image(
    session: Session,
    image_id: int,
    overrides: dict | None = None
) -> dict:
    """Auto-populate QSO fields from image metadata.

    Fallback hierarchy:
    1. User override (manual entry)
    2. Image metadata (from decode)
    3. Placeholder (None/empty)

    Args:
        session: Active database session
        image_id: ID of image to create QSO from
        overrides: Optional user-provided field overrides

    Returns:
        Dictionary of QSO fields ready for database insertion

    Raises:
        ValueError: If image not found or callsign missing

    """
    if overrides is None:
        overrides = {}

    # Fetch image metadata
    image = session.get(SSTVImage, image_id)
    if image is None:
        raise ValueError(f"Image not found: {image_id}")

    # Build QSO fields with fallback hierarchy
    qso_fields = {
        "callsign": overrides.get("callsign") or image.callsign,
        "mode": overrides.get("mode") or image.mode,
        "frequency_hz": overrides.get("frequency_hz") or image.frequency_hz,
        "start_time": overrides.get("start_time") or image.timestamp,
        "end_time": overrides.get("end_time") or None,
        "report": overrides.get("report") or _convert_quality_to_report(image.rx_quality_score),
        "comments": overrides.get("comments") or None,
        "is_sent": overrides.get("is_sent") or False,
    }

    # Validate required fields
    if not qso_fields["callsign"]:
        raise ValueError("Callsign required for QSO logging. Please enter manually.")

    return qso_fields


def _convert_quality_to_report(rx_quality_score: float | None) -> str | None:
    """Convert RX quality score (0.0-1.0) to signal report format.

    Args:
        rx_quality_score: Signal quality score from decoder

    Returns:
        Signal report string (e.g., "59", "55") or None

    """
    if rx_quality_score is None:
        return None

    # Convert 0.0-1.0 quality to 1-9 readability scale
    # Quality > 0.9 = 59 (excellent)
    # Quality 0.7-0.9 = 58 (good)
    # Quality 0.5-0.7 = 57 (fair)
    # Quality 0.3-0.5 = 55 (poor)
    # Quality < 0.3 = 53 (weak)

    if rx_quality_score >= 0.9:
        return "59"
    elif rx_quality_score >= 0.7:
        return "58"
    elif rx_quality_score >= 0.5:
        return "57"
    elif rx_quality_score >= 0.3:
        return "55"
    else:
        return "53"


def create_qso_with_image(
    session: Session,
    image_id: int,
    qso_fields: dict
) -> QSO:
    """Create QSO record and link to image.

    Args:
        session: Active database session
        image_id: ID of image to link
        qso_fields: QSO field values (from populate_qso_from_image)

    Returns:
        Created QSO instance

    """
    # Create QSO record
    qso = QSO(
        callsign=qso_fields["callsign"],
        mode=qso_fields["mode"],
        frequency_hz=qso_fields.get("frequency_hz"),
        start_time=qso_fields["start_time"],
        end_time=qso_fields.get("end_time"),
        report=qso_fields.get("report"),
        comments=qso_fields.get("comments"),
        is_sent=qso_fields.get("is_sent", False),
        record_type=qso_fields.get("record_type", "qso"),
    )
    session.add(qso)
    session.flush()  # Get QSO ID

    # Link QSO to image
    link = QSOImage(qso_id=qso.id, image_id=image_id)
    session.add(link)

    session.commit()
    return qso


def export_qsos_to_adif(
    session: Session,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    callsign_filter: str | None = None
) -> str:
    """Export QSOs to ADIF format.

    Args:
        session: Active database session
        start_date: Optional start date filter
        end_date: Optional end date filter
        callsign_filter: Optional callsign substring filter

    Returns:
        ADIF format string

    """
    # Contacts only. Reception reports follow SWL conventions, not ADIF's,
    # and a remote reception exported here would put a QSO that never
    # happened into LoTW, eQSL or Club Log (PRODUCT.md requirement 12).
    query = session.query(QSO).filter(QSO.record_type == "qso")

    if start_date:
        query = query.filter(QSO.start_time >= start_date)
    if end_date:
        query = query.filter(QSO.start_time <= end_date)
    if callsign_filter:
        query = query.filter(QSO.callsign.ilike(f"%{callsign_filter}%"))

    qsos = query.order_by(QSO.start_time).all()

    # Generate ADIF
    output = StringIO()

    # ADIF header
    output.write("ADIF Export from SSTeVe SSTV Platform\n")
    output.write("<ADIF_VER:5>3.1.4\n")
    output.write("<PROGRAMID:6>SSTeVe\n")
    output.write("<PROGRAMVERSION:5>1.0.0\n")
    output.write("<EOH>\n\n")

    # QSO records
    for qso in qsos:
        output.write(_format_qso_as_adif(qso))
        output.write("<EOR>\n\n")

    return output.getvalue()


def _format_qso_as_adif(qso: QSO) -> str:
    """Format single QSO as ADIF record.

    Args:
        qso: QSO instance

    Returns:
        ADIF record string (without EOR marker)

    Raises:
        ValueError: If the record is not a contact, or any picture on it
            was heard at someone else's receiver. The export query already
            leaves these out; this is the block PRODUCT.md calls absolute,
            so it holds for any future caller that doesn't.

    """
    if qso.record_type != "qso":
        raise ValueError(
            f"Record {qso.id} is a {qso.record_type}, not a contact, and "
            "ADIF is for contacts."
        )
    if any(image.heard_at == "remote" for image in qso.images):
        raise ValueError(
            f"Record {qso.id} has a picture heard at someone else's "
            "receiver, so it can't be exported as a contact."
        )

    fields = []

    # Required fields
    fields.append(_adif_field("CALL", qso.callsign))
    fields.append(_adif_field("QSO_DATE", qso.start_time.strftime("%Y%m%d")))
    fields.append(_adif_field("TIME_ON", qso.start_time.strftime("%H%M%S")))
    fields.append(_adif_field("MODE", "SSTV"))
    fields.append(_adif_field("SUBMODE", qso.mode))

    # Optional fields
    if qso.frequency_hz:
        freq_mhz = qso.frequency_hz / 1e6
        fields.append(_adif_field("FREQ", f"{freq_mhz:.6f}"))

    if qso.end_time:
        fields.append(_adif_field("QSO_DATE_OFF", qso.end_time.strftime("%Y%m%d")))
        fields.append(_adif_field("TIME_OFF", qso.end_time.strftime("%H%M%S")))

    if qso.report:
        fields.append(_adif_field("RST_RCVD", qso.report))

    if qso.comments:
        fields.append(_adif_field("COMMENT", qso.comments))

    # QSL info (images count as QSL)
    if qso.images:
        fields.append(_adif_field("QSL_RCVD", "Y"))
        fields.append(_adif_field("QSL_RCVD_VIA", "SSTV"))

    return " ".join(fields) + " "


def _adif_field(field_name: str, value: str) -> str:
    """Format ADIF field.

    Args:
        field_name: ADIF field name
        value: Field value

    Returns:
        Formatted ADIF field: <FIELD:length>value

    """
    value_str = str(value)
    length = len(value_str)
    return f"<{field_name}:{length}>{value_str}"


def validate_callsign(callsign: str) -> bool:
    """Validate amateur radio callsign format.

    Basic validation: 3-10 characters, alphanumeric with / allowed.

    Args:
        callsign: Callsign string to validate

    Returns:
        True if valid format, False otherwise

    """
    if not callsign or not (3 <= len(callsign) <= 10):
        return False

    # Allow alphanumeric and forward slash
    clean = callsign.replace("/", "").replace("-", "")
    return clean.isalnum()


def suggest_qso_improvements(qso_fields: dict) -> dict[str, str]:
    """Suggest improvements for QSO fields.

    Args:
        qso_fields: QSO field dictionary

    Returns:
        Dictionary of field -> suggestion text

    """
    suggestions = {}

    if not qso_fields.get("frequency_hz"):
        suggestions["frequency_hz"] = "Add frequency for complete log"

    if not qso_fields.get("report"):
        suggestions["report"] = "Add signal report (e.g., 59)"

    if not qso_fields.get("end_time"):
        suggestions["end_time"] = "Add end time for contact duration"

    return suggestions
