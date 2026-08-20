"""Scanline pixels for the progressive decode canvas (#55).

PRODUCT.md #6 asks that scanlines render as they arrive with no buffering
delay. `ScanlineUpdateEvent` carried numbers only, so a client could show
a finished picture and nothing else -- the product's centrepiece
interaction reduced to a progress bar.

**Why plain integers rather than base64.** Measured at each mode's real
line pacing:

    Robot 36    28.7 KB/s json    8.5 KB/s base64
    Martin M2   19.1              5.6
    PD180       22.7              6.7
    Scottie S1  10.0              3.0

The worst case is affordable either way, so bandwidth does not decide it.
What does is the requirement itself: base64 saves 20 KB/s and puts a
decode step between a line arriving and the canvas painting it. An
integer array drops straight into a Uint8ClampedArray for putImageData.
"""

from __future__ import annotations

import numpy as np

#: Most rows one event will carry. A decode produces lines faster than a
#: slow consumer drains them, and without a cap one event could carry a
#: whole frame -- a megabyte arriving at once is the buffering delay this
#: feature exists to avoid. Twenty rows is about 60 KB at 320 px, and more
#: than any mode produces between events at normal pacing.
MAX_LINES_PER_EVENT = 20


def rows_to_rgb_payload(rows: np.ndarray) -> list[list[int]]:
    """Flatten decoded rows into JSON-safe RGB triples.

    Each row becomes ``[r, g, b, r, g, b, ...]``, so a client gets the
    width from ``len(row) // 3`` and needs to know nothing about the mode
    before its first paint.

    When more rows arrive than the cap allows, the **newest** are kept.
    Dropping the oldest keeps the canvas current; keeping them would
    paint stale lines and then jump.
    """
    if rows is None or len(rows) == 0:
        return []
    if len(rows) > MAX_LINES_PER_EVENT:
        rows = rows[-MAX_LINES_PER_EVENT:]
    # tolist() converts out of numpy scalars in one step -- json.dumps
    # raises on np.uint8, and that failure would only appear once a
    # client was attached.
    return [np.asarray(row, dtype=np.uint8).reshape(-1).tolist() for row in rows]
