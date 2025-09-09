#!/usr/bin/env python3
"""
SSTV Wrapper - Handles audio format conversion and terminal output
Moved from scripts/sstv_wrapper.py to core engine
"""
import sys
import os
import subprocess
import tempfile
from collections import namedtuple
from pathlib import Path

# Patch before importing anything else
def patch_terminal_functions():
    """Patch terminal-related functions globally before any imports"""
    import shutil
    import os
    
    # Create a mock terminal_size object
    terminal_size = namedtuple('terminal_size', ['columns', 'lines'])
    
    # Replace get_terminal_size everywhere it might be imported
    def mock_get_terminal_size(fallback=(80, 24)):
        return terminal_size(80, 24)
    
    # Patch all possible imports
    shutil.get_terminal_size = mock_get_terminal_size
    os.get_terminal_size = mock_get_terminal_size
    
    # Also patch it in sys modules in case it's already imported
    for module_name, module in sys.modules.items():
        if hasattr(module, 'get_terminal_size'):
            setattr(module, 'get_terminal_size', mock_get_terminal_size)

def main():
    """Run SSTV with audio conversion and terminal patches"""
    if len(sys.argv) < 2:
        print("Usage: python3 sstv_wrapper.py [sstv arguments...]")
        sys.exit(1)
    
    # Apply patches BEFORE any imports
    patch_terminal_functions()
    
    # WAV-only support - no conversion needed
    try:
        from sstv.__main__ import main as sstv_main
        # Replace sys.argv to pass arguments to SSTV
        sys.argv = ['sstv'] + sys.argv[1:]
        sstv_main()
    except Exception as e:
        print(f"SSTV execution failed: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()