"""
SSTV Decoder - Universal Python decoder using colaclanth/sstv
"""

import os
import sys
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional, Callable, List
from collections import namedtuple

from .types import SSTVResult, SSTVDecodeRequest, EnhancementOptions

# Terminal size patch for headless environments
def patch_terminal_functions():
    """Patch terminal-related functions globally before any imports"""
    import shutil
    import os
    
    terminal_size = namedtuple('terminal_size', ['columns', 'lines'])
    
    def mock_get_terminal_size(fallback=(80, 24)):
        return terminal_size(80, 24)
    
    shutil.get_terminal_size = mock_get_terminal_size
    os.get_terminal_size = mock_get_terminal_size
    
    for module_name, module in sys.modules.items():
        if hasattr(module, 'get_terminal_size'):
            setattr(module, 'get_terminal_size', mock_get_terminal_size)

class SSTVDecoder:
    """Universal SSTV decoder using colaclanth/sstv library"""
    
    def __init__(self, debug: bool = False):
        self.debug = debug
        self.progress_callback: Optional[Callable[[int], None]] = None
        self.mode_callback: Optional[Callable[[str], None]] = None
        
        # Apply terminal patches before any SSTV imports
        patch_terminal_functions()
    
    def set_progress_callback(self, callback: Callable[[int], None]):
        """Set progress reporting callback"""
        self.progress_callback = callback
    
    def set_mode_callback(self, callback: Callable[[str], None]):
        """Set mode detection callback"""
        self.mode_callback = callback
    
    def check_dependencies(self) -> bool:
        """Check if required Python libraries are available"""
        try:
            import sstv
            return True
        except ImportError:
            return False
    
    def get_supported_modes(self) -> List[str]:
        """Get list of supported SSTV modes"""
        return [
            "Martin M1", "Martin M2",
            "Scottie S1", "Scottie S2", "Scottie DX",
            "Robot 36", "Robot 72",
            "PD 50", "PD 90", "PD 120", "PD 160", "PD 180", "PD 240", "PD 290"
        ]
    
    def decode(self, request: SSTVDecodeRequest) -> SSTVResult:
        """
        Decode SSTV audio file to image
        
        Args:
            request: SSTVDecodeRequest with decode parameters
            
        Returns:
            SSTVResult with decode results
        """
        start_time = time.time()
        
        # Validate input file
        if not os.path.exists(request.audio_path):
            return SSTVResult(
                success=False,
                message=f"Audio file not found: {request.audio_path}",
                input_path=request.audio_path,
                output_path=request.output_path
            )
        
        try:
            # Import SSTV library with patches applied
            from sstv.decode import SSTVDecoder as ColacSSTVDecoder
            
            if self.debug:
                print(f"🔧 Decoding: {request.audio_path} -> {request.output_path}")
            
            # Create output directory if needed
            os.makedirs(os.path.dirname(request.output_path), exist_ok=True)
            
            # Decode SSTV
            decoder = ColacSSTVDecoder(request.audio_path)
            
            # Suppress stderr during decoding to hide progress messages
            old_stderr = sys.stderr
            if not self.debug:
                sys.stderr = open(os.devnull, 'w')
            
            try:
                image = decoder.decode()
            finally:
                if not self.debug:
                    sys.stderr.close()
                    sys.stderr = old_stderr
            
            if not image:
                return SSTVResult(
                    success=False,
                    message="No SSTV signal detected in audio file",
                    input_path=request.audio_path,
                    output_path=request.output_path,
                    duration_ms=(time.time() - start_time) * 1000
                )
            
            # Save decoded image
            image.save(request.output_path)
            
            # Get file stats
            file_size = os.path.getsize(request.output_path)
            duration_ms = (time.time() - start_time) * 1000
            
            # Try to detect mode (basic implementation)
            mode = self._detect_mode(request.audio_path)
            
            result = SSTVResult(
                success=True,
                message=f"Successfully decoded {mode} SSTV image",
                mode=mode,
                input_path=request.audio_path,
                output_path=request.output_path,
                file_size=file_size,
                duration_ms=duration_ms
            )
            
            # Apply enhancement if requested
            if request.enhance:
                from .enhancer import SSTVEnhancer
                enhancer = SSTVEnhancer(debug=self.debug)
                enhance_result = enhancer.enhance_image(
                    request.output_path,
                    request.output_path,
                    request.enhance
                )
                
                if enhance_result.success:
                    result.enhanced = True
                    result.enhancements = request.enhance
                    result.file_size = enhance_result.file_size
                    result.message += " (enhanced)"
                else:
                    result.message += " (enhancement failed)"
                    result.metadata = {"enhance_error": enhance_result.message}
            
            if self.debug:
                print(f"✅ Decode successful: {result.message}")
            
            return result
            
        except ImportError as e:
            return SSTVResult(
                success=False,
                message=f"SSTV library not available: {str(e)}",
                error="Missing colaclanth/sstv library. Install with: pip install sstv",
                input_path=request.audio_path,
                output_path=request.output_path,
                duration_ms=(time.time() - start_time) * 1000
            )
        except Exception as e:
            return SSTVResult(
                success=False,
                message=f"SSTV decoding failed: {str(e)}",
                error=str(e),
                input_path=request.audio_path,
                output_path=request.output_path,
                duration_ms=(time.time() - start_time) * 1000
            )
    
    def _detect_mode(self, audio_path: str) -> str:
        """
        Basic SSTV mode detection
        In a full implementation, this would analyze the VIS code
        """
        # For now, return a default mode
        # TODO: Implement proper VIS code detection
        return "Scottie S1"
    
    def decode_from_json(self, json_request: str) -> str:
        """
        Decode from JSON request string, return JSON result
        Useful for cross-platform IPC
        """
        import json
        
        try:
            request_data = json.loads(json_request)
            
            # Convert to SSTVDecodeRequest
            enhance = None
            if "enhance" in request_data:
                enhance = EnhancementOptions.from_dict(request_data["enhance"])
            
            request = SSTVDecodeRequest(
                audio_path=request_data["audioPath"],
                output_path=request_data["outputPath"],
                skip_seconds=request_data.get("skipSeconds", 0.0),
                enhance=enhance
            )
            
            result = self.decode(request)
            return result.to_json()
            
        except Exception as e:
            error_result = SSTVResult(
                success=False,
                message=f"JSON decode request failed: {str(e)}",
                error=str(e)
            )
            return error_result.to_json()