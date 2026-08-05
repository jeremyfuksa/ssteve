"""Conversions between database image keys and public API identifiers."""

from __future__ import annotations

from uuid import NAMESPACE_OID, UUID, uuid5


def db_image_id_to_uuid(db_id: int) -> UUID:
    """Return the stable public UUID for an integer database image ID."""
    return uuid5(NAMESPACE_OID, f"sstv_image_{db_id}")
