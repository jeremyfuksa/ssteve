"""
SSTV Engine - Universal Python Core
Cross-platform SSTV decoder/encoder engine using colaclanth/sstv and PySSTV
"""

# KIRO-SUGGESTION: Use lazy imports to avoid ImportError when modules don't exist yet
# This allows the package to be imported even during development when not all modules are implemented
try:
    from .decoder import SSTVDecoder
except ImportError:
    SSTVDecoder = None

try:
    from .encoder import SSTVEncoder
except ImportError:
    SSTVEncoder = None

try:
    from .enhancer import SSTVEnhancer
except ImportError:
    SSTVEnhancer = None

# KIRO-SUGGESTION: Import types with fallback to avoid breaking the package during development
try:
    from .types import SSTVResult, SSTVMode, EnhancementOptions
except ImportError:
    # Provide basic type stubs for development
    SSTVResult = dict
    SSTVMode = str
    EnhancementOptions = dict

__version__ = "1.0.0"

# KIRO-SUGGESTION: Filter out None values from __all__ to only export available modules
# This prevents AttributeError when trying to import non-existent modules
__all__ = [
    name for name, obj in [
        ("SSTVDecoder", SSTVDecoder),
        ("SSTVEncoder", SSTVEncoder), 
        ("SSTVEnhancer", SSTVEnhancer),
        ("SSTVResult", SSTVResult),
        ("SSTVMode", SSTVMode),
        ("EnhancementOptions", EnhancementOptions)
    ] if obj is not None
]