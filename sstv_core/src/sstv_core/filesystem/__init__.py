"""Filesystem integration for SSTeVe.

Provides:
- File system watcher for auto-import of external images
- Image metadata parsing and import
- MMSSTV library compatibility
- Directory scanning and batch import
"""

from sstv_core.filesystem.watcher import ImageLibraryWatcher
from sstv_core.filesystem.importer import ImageImporter, parse_image_metadata
from sstv_core.filesystem.mmsstv_importer import MMSStvImporter

__all__ = [
    "ImageLibraryWatcher",
    "ImageImporter",
    "parse_image_metadata",
    "MMSStvImporter",
]
