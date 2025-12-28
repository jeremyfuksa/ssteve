"""
SSTV Image Enhancer - Universal Python image enhancement using PIL
"""

import os
import time
import numpy as np
from typing import Dict, Any
from PIL import Image, ImageEnhance, ImageOps

from .types import SSTVResult, EnhancementOptions

class SSTVEnhancer:
    """Universal SSTV image enhancer using PIL/Pillow"""
    
    # Predefined enhancement presets
    PRESETS = {
        'conservative': EnhancementOptions(
            contrast=1.1,
            brightness=1.02,
            saturation=1.05,
            auto_level=False,
            gamma=1.0,
            sharpen=False,
            white_balance=True
        ),
        'moderate': EnhancementOptions(
            contrast=1.25,
            brightness=1.05,
            saturation=1.1,
            auto_level=True,
            gamma=1.0,
            sharpen=False,
            white_balance=True
        ),
        'aggressive': EnhancementOptions(
            contrast=1.4,
            brightness=1.1,
            saturation=1.2,
            auto_level=True,
            gamma=0.9,
            sharpen=True,
            white_balance=True
        ),
        'white_balance_only': EnhancementOptions(
            contrast=1.0,
            brightness=1.0,
            saturation=1.0,
            auto_level=False,
            gamma=1.0,
            sharpen=False,
            white_balance=True
        ),
        'auto_level_only': EnhancementOptions(
            contrast=1.0,
            brightness=1.0,
            saturation=1.0,
            auto_level=True,
            gamma=1.0,
            sharpen=False,
            white_balance=False
        )
    }
    
    def __init__(self, debug: bool = False):
        self.debug = debug
    
    def check_dependencies(self) -> bool:
        """Check if required Python libraries are available"""
        try:
            from PIL import Image
            import numpy as np
            return True
        except ImportError:
            return False
    
    def get_presets(self) -> Dict[str, EnhancementOptions]:
        """Get available enhancement presets"""
        return self.PRESETS.copy()
    
    def enhance_image(self, input_path: str, output_path: str, options: EnhancementOptions) -> SSTVResult:
        """
        Enhance an image with the specified options
        
        Args:
            input_path: Path to input image
            output_path: Path for enhanced output image
            options: Enhancement options
            
        Returns:
            SSTVResult with enhancement results
        """
        start_time = time.time()
        
        # Validate input file
        if not os.path.exists(input_path):
            return SSTVResult(
                success=False,
                message=f"Input image not found: {input_path}",
                input_path=input_path,
                output_path=output_path
            )
        
        try:
            # Load image
            with Image.open(input_path) as img:
                # Convert to RGB if necessary
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Apply enhancements in order
                enhanced_img = img.copy()
                
                if self.debug:
                    print(f"🎨 Enhancing image: {input_path}")
                    print(f"   Options: {options}")
                
                # 1. Auto-level adjustment (histogram stretching)
                if options.auto_level:
                    enhanced_img = ImageOps.autocontrast(enhanced_img)
                    if self.debug:
                        print("   ✓ Applied auto-level")
                
                # 2. Brightness adjustment
                if options.brightness != 1.0:
                    enhancer = ImageEnhance.Brightness(enhanced_img)
                    enhanced_img = enhancer.enhance(options.brightness)
                    if self.debug:
                        print(f"   ✓ Applied brightness: {options.brightness}")
                
                # 3. Contrast adjustment
                if options.contrast != 1.0:
                    enhancer = ImageEnhance.Contrast(enhanced_img)
                    enhanced_img = enhancer.enhance(options.contrast)
                    if self.debug:
                        print(f"   ✓ Applied contrast: {options.contrast}")
                
                # 4. Saturation adjustment
                if options.saturation != 1.0:
                    enhancer = ImageEnhance.Color(enhanced_img)
                    enhanced_img = enhancer.enhance(options.saturation)
                    if self.debug:
                        print(f"   ✓ Applied saturation: {options.saturation}")
                
                # 5. Gamma correction
                if options.gamma != 1.0:
                    enhanced_img = self._apply_gamma_correction(enhanced_img, options.gamma)
                    if self.debug:
                        print(f"   ✓ Applied gamma: {options.gamma}")
                
                # 6. White balance correction
                if options.white_balance:
                    enhanced_img = self._apply_white_balance(enhanced_img)
                    if self.debug:
                        print("   ✓ Applied white balance")
                
                # 7. Sharpening
                if options.sharpen:
                    enhancer = ImageEnhance.Sharpness(enhanced_img)
                    enhanced_img = enhancer.enhance(1.5)  # Moderate sharpening
                    if self.debug:
                        print("   ✓ Applied sharpening")
                
                # Create output directory if needed
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                
                # Save enhanced image
                enhanced_img.save(output_path, quality=95)
                
                # Get file info
                file_size = os.path.getsize(output_path)
                width, height = enhanced_img.size
                duration_ms = (time.time() - start_time) * 1000
                
                result = SSTVResult(
                    success=True,
                    message="Image enhancement completed successfully",
                    input_path=input_path,
                    output_path=output_path,
                    file_size=file_size,
                    duration_ms=duration_ms,
                    enhanced=True,
                    enhancements=options,
                    metadata={
                        "width": width,
                        "height": height,
                        "originalSize": os.path.getsize(input_path) if input_path != output_path else file_size
                    }
                )
                
                if self.debug:
                    print(f"✅ Enhancement successful: {result.message}")
                
                return result
                
        except Exception as e:
            return SSTVResult(
                success=False,
                message=f"Image enhancement failed: {str(e)}",
                error=str(e),
                input_path=input_path,
                output_path=output_path,
                duration_ms=(time.time() - start_time) * 1000
            )
    
    def _apply_gamma_correction(self, img: Image.Image, gamma: float) -> Image.Image:
        """Apply gamma correction to image"""
        img_array = np.array(img, dtype=np.float32) / 255.0
        img_array = np.power(img_array, 1.0 / gamma)
        img_array = (img_array * 255.0).astype(np.uint8)
        return Image.fromarray(img_array)
    
    def _apply_white_balance(self, img: Image.Image) -> Image.Image:
        """Apply simple white balance correction using gray world assumption"""
        img_array = np.array(img, dtype=np.float32)
        
        # Calculate average values for each channel
        avg_r = np.mean(img_array[:, :, 0])
        avg_g = np.mean(img_array[:, :, 1])
        avg_b = np.mean(img_array[:, :, 2])
        
        # Calculate gray value (average of all channels)
        gray = (avg_r + avg_g + avg_b) / 3
        
        # Calculate scaling factors with limits
        scale_r = min(1.5, max(0.67, gray / avg_r if avg_r > 0 else 1.0))
        scale_g = min(1.5, max(0.67, gray / avg_g if avg_g > 0 else 1.0))
        scale_b = min(1.5, max(0.67, gray / avg_b if avg_b > 0 else 1.0))
        
        # Apply scaling
        img_array[:, :, 0] *= scale_r
        img_array[:, :, 1] *= scale_g
        img_array[:, :, 2] *= scale_b
        
        # Clip values to valid range
        img_array = np.clip(img_array, 0, 255).astype(np.uint8)
        
        return Image.fromarray(img_array)
    
    def enhance_from_json(self, json_request: str) -> str:
        """
        Enhance from JSON request string, return JSON result
        Useful for cross-platform IPC
        """
        import json
        
        try:
            request_data = json.loads(json_request)
            
            # Parse enhancement options
            if "preset" in request_data and request_data["preset"] in self.PRESETS:
                options = self.PRESETS[request_data["preset"]]
            else:
                options = EnhancementOptions.from_dict(request_data.get("options", {}))
            
            result = self.enhance_image(
                request_data["inputPath"],
                request_data["outputPath"],
                options
            )
            
            return result.to_json()
            
        except Exception as e:
            error_result = SSTVResult(
                success=False,
                message=f"JSON enhance request failed: {str(e)}",
                error=str(e)
            )
            return error_result.to_json()