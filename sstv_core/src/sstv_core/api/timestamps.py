"""Say which clock a timestamp is on, at the API boundary.

The database stores UTC as naive datetimes -- `SSTVImage.timestamp` and the
QSO times are all `datetime.now(timezone.utc).replace(tzinfo=None)`. Served
unlabelled, that is `2026-09-12T02:14:27` on the wire, and a naive ISO
string means *local time* to every client that parses one: JavaScript's
`new Date()`, Python's `datetime.fromisoformat`, Swift's ISO8601 decoder.

The desktop shell showed a picture decoded at 21:14 local as **2:14 AM**
(2026-09-11). The stored value was right; the wire format did not say what
it was.

Amateur radio runs on UTC, so the answer is to mark it rather than convert
it: a client that wants local time can do that conversion correctly once
the instant is unambiguous.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import overload


@overload
def as_utc(moment: datetime) -> datetime: ...


@overload
def as_utc(moment: None) -> None: ...


def as_utc(moment: datetime | None) -> datetime | None:
    """Label a stored (naive, UTC) datetime as UTC. Aware input is untouched.

    Overloaded so a non-null column stays non-null to the type checker: most
    of these are required fields, and only `end_time` is optional.
    """
    if moment is None:
        return None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)
