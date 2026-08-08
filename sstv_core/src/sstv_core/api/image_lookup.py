"""Resolve public image UUIDs back to database rows.

Public image IDs are one-way uuid5 hashes of the integer primary key
(image_ids.py). Reversing one means scanning the ID space; this helper
scans only the id column and is the single place to optimize if a UUID
column ever lands in the schema.

Before 2026-08-07 there was no bridge at all: /images spoke UUIDs while
/qso and /smart_reply demanded raw integer keys no endpoint ever returned,
so a client literally could not log a QSO for an image it just decoded.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from sstv_core.api.image_ids import db_image_id_to_uuid
from sstv_core.database.models import SSTVImage


def resolve_image_uuid(session: Session, image_id: UUID) -> SSTVImage | None:
    """Return the SSTVImage whose public UUID is `image_id`, or None."""
    for (db_id,) in session.query(SSTVImage.id).all():
        if db_image_id_to_uuid(db_id) == image_id:
            return session.get(SSTVImage, db_id)
    return None
