"""
SSTV Encoder - Universal Python encoder using PySSTV
"""

import os
import subprocess
import time
from typing import List
from .types import SSTVResult, SSTVEncodeRequest

class SSTVEncoder:
    """Universal SSTV encoder using PySSTV library"""
    
    # Available modes that support full round-trip (encode + decode)
    AVAILABLE_MODES = [
        'MartinM1', 'MartinM2',
        'ScottieS1', 'ScottieS2', 'ScottieDX',
        'Robot36'
    ]
    
    def __init__(self, debug: bool = False):
        self.debug = debug
    
    def check_dependencies(self) -> bool:
        """Check if required Python libraries are available"""
        try:
            import pysstv
            return True
        except ImportError:
            return False
    
    def get_supported_modes(self) -> List[str]:
        """Get list of supported encoding modes"""
        return self.AVAILABLE_MODES.copy()
    
    def encode(self, request: SSTVEncodeRequest) -> SSTVResult:
        """
        Encode image to SSTV audio file
        
        Args:
            request: SSTVEncodeRequest with encode parameters
            
        Returns:
            SSTVResult with encode results
        """
        start_time = time.time()
        
        # Validate input file
        if not os.path.exists(request.image_path):
            return SSTVResult(
                success=False,
                message=f"Image file not found: {request.image_path}",
                input_path=request.image_path,
                output_path=request.output_path
            )
        
        # Validate mode
        if request.mode not in self.AVAILABLE_MODES:
            return SSTVResult(
                success=False,
                message=f"Unsupported mode: {request.mode}. Available: {', '.join(self.AVAILABLE_MODES)}",
                input_path=request.image_path,
                output_path=request.output_path
            )
        
        try:
            # Create output directory if needed
            os.makedirs(os.path.dirname(request.output_path), exist_ok=True)
            
            # Build PySSTV command
            cmd = [
                'python3', '-m', 'pysstv',
                '--mode', request.mode,
                '--rate', str(request.sample_rate),
                '--bits', str(request.bits_per_sample)
            ]
            
            if request.vox:
                cmd.append('--vox')
            
            if request.fskid:
                cmd.extend(['--fskid', request.fskid])
            
            if request.resize:
                cmd.append('--resize')
                cmd.extend(['--resample', 'lanczos'])
            
            # Add input and output paths
            cmd.extend([request.image_path, request.output_path])
            
            if self.debug:
                print(f"🔧 Encoding: {' '.join(cmd)}")
            
            # Execute PySSTV
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else "Unknown encoding error"
                return SSTVResult(
                    success=False,
                    message=f"PySSTV encoding failed: {error_msg}",
                    error=error_msg,
                    input_path=request.image_path,
                    output_path=request.output_path,
                    duration_ms=(time.time() - start_time) * 1000
                )
            
            # Check if output file was created
            if not os.path.exists(request.output_path):
                return SSTVResult(
                    success=False,
                    message="Output WAV file was not created",
                    input_path=request.image_path,
                    output_path=request.output_path,
                    duration_ms=(time.time() - start_time) * 1000
                )
            
            # Get file statistics
            file_size = os.path.getsize(request.output_path)
            duration_ms = (time.time() - start_time) * 1000
            
            # Estimate audio duration (rough calculation)
            # WAV file size ≈ sample_rate * bits/8 * channels * duration_seconds
            estimated_duration = file_size / (request.sample_rate * (request.bits_per_sample / 8) * 1)
            
            result = SSTVResult(
                success=True,
                message=f"Successfully encoded {request.mode} SSTV audio",
                mode=request.mode,
                input_path=request.image_path,
                output_path=request.output_path,
                file_size=file_size,
                duration_ms=duration_ms,
                metadata={
                    "sampleRate": request.sample_rate,
                    "bitsPerSample": request.bits_per_sample,
                    "estimatedDuration": round(estimated_duration, 1),
                    "vox": request.vox,
                    "fskid": request.fskid
                }
            )
            
            if self.debug:
                print(f"✅ Encode successful: {result.message}")
            
            return result
            
        except subprocess.TimeoutExpired:
            return SSTVResult(
                success=False,
                message="Encoding timed out (>5 minutes)",
                error="Timeout",
                input_path=request.image_path,
                output_path=request.output_path,
                duration_ms=(time.time() - start_time) * 1000
            )
        except Exception as e:
            return SSTVResult(
                success=False,
                message=f"SSTV encoding failed: {str(e)}",
                error=str(e),
                input_path=request.image_path,
                output_path=request.output_path,
                duration_ms=(time.time() - start_time) * 1000
            )
    
    def encode_from_json(self, json_request: str) -> str:
        """
        Encode from JSON request string, return JSON result
        Useful for cross-platform IPC
        """
        import json
        
        try:
            request_data = json.loads(json_request)
            
            request = SSTVEncodeRequest(
                image_path=request_data["imagePath"],
                output_path=request_data["outputPath"],
                mode=request_data.get("mode", "ScottieS1"),
                sample_rate=request_data.get("sampleRate", 22050),
                bits_per_sample=request_data.get("bitsPerSample", 16),
                vox=request_data.get("vox", False),
                fskid=request_data.get("fskid"),
                resize=request_data.get("resize", True)
            )
            
            result = self.encode(request)
            return result.to_json()
            
        except Exception as e:
            error_result = SSTVResult(
                success=False,
                message=f"JSON encode request failed: {str(e)}",
                error=str(e)
            )
            return error_result.to_json()