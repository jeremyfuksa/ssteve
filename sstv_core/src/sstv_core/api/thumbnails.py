"""Thumbnails, and deciding which files are safe to serve (#54).

Storage stays filesystem-native: pictures are files on disk and the
database holds metadata. This is about serving bytes that already exist,
never about putting them in a row.

Two jobs live here rather than in the route, because both are pure
functions over paths and both are worth testing without a web client.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

#: Longest edge of a generated thumbnail, in pixels. Big enough for the
#: gallery grid and the history strip on a 1280x720 field laptop
#: (frontend-spec 20.11), small enough that a hundred of them load without
#: thought.
THUMBNAIL_MAX_PX = 512

#: Suffix inserted before the extension. Beside the original rather than in
#: a parallel tree, so a thumbnail travels with its picture when an
#: operator moves or backs up a directory -- the filesystem-native
#: storage rule applies to derived files too.
THUMBNAIL_SUFFIX = ".thumb"


def thumbnail_path_for(source: Path) -> Path:
    """Where the thumbnail for ``source`` lives."""
    return source.with_suffix(THUMBNAIL_SUFFIX + source.suffix)


def generate_thumbnail(source: Path | str) -> Path | None:
    """Write a thumbnail beside ``source`` and return its path.

    Returns None instead of raising. A thumbnail is a convenience, and a
    decode that produced a real picture must not be reported as failed
    because a derived file could not be written -- the missing thumbnail
    is visible in the gallery, which is the right place for it to show up.

    Never upscales. Blowing a Robot 36 up to the cap would invent detail
    the transmission never carried.
    """
    from PIL import Image

    source = Path(source)
    target = thumbnail_path_for(source)
    try:
        with Image.open(source) as img:
            img.load()
            if max(img.size) > THUMBNAIL_MAX_PX:
                # thumbnail() preserves the aspect ratio in place, which
                # matters: SSTV modes are not square, and a stretched
                # thumbnail misrepresents the picture in the one view an
                # operator scans quickly.
                img.thumbnail((THUMBNAIL_MAX_PX, THUMBNAIL_MAX_PX))
            img.save(target)
    except Exception as exc:
        logger.warning("Couldn't make a thumbnail for %s: %s", source, exc)
        return None
    return target


def is_servable(candidate: Path | str, roots: list[Path]) -> bool:
    """Whether ``candidate`` sits inside one of ``roots``.

    An image row's filepath decides which bytes a request returns, so
    anything that lets a caller steer it outside the library turns an
    image endpoint into a general file-read primitive. Paths are resolved
    before comparison: without that, `..` walks out and a symlink planted
    inside the library points anywhere.
    """
    try:
        resolved = Path(candidate).resolve()
    except OSError:
        return False
    for root in roots:
        try:
            resolved.relative_to(Path(root).resolve())
        except (ValueError, OSError):
            continue
        return True
    return False
