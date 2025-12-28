"""
SSTV Engine Types - Universal data structures for cross-platform communication
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from enum import Enum
import json

class SSTVMode(Enum):
    """Supported SSTV modes"""
    MARTIN_M1 = "Martin M1"
    MARTIN_M2 = "Martin M2"
    SCOTTIE_S1 = "Scottie S1"
    SCOTTIE_S2 = "Scottie S2"
    SCOTTIE_DX = "Scottie DX"
    ROBOT_36 = "Robot 36"
    ROBOT_72 = "Robot 72"
    PD_50 = "PD 50"
    PD_90 = "PD 90"
    PD_120 = "PD 120"
    PD_160 = "PD 160"
    PD_180 = "PD 180"
    PD_240 = "PD 240"
    PD_290 = "PD 290"

@dataclass
class EnhancementOptions:
    """Image enhancement configuration"""
    contrast: float = 1.25
    brightness: float = 1.05
    saturation: float = 1.1
    auto_level: bool = False
    gamma: float = 1.0
    sharpen: bool = False
    white_balance: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "contrast": self.contrast,
            "brightness": self.brightness,
            "saturation": self.saturation,
            "autoLevel": self.auto_level,
            "gamma": self.gamma,
            "sharpen": self.sharpen,
            "whiteBalance": self.white_balance
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EnhancementOptions':
        return cls(
            contrast=data.get("contrast", 1.25),
            brightness=data.get("brightness", 1.05),
            saturation=data.get("saturation", 1.1),
            auto_level=data.get("autoLevel", False),
            gamma=data.get("gamma", 1.0),
            sharpen=data.get("sharpen", False),
            white_balance=data.get("whiteBalance", True)
        )

@dataclass
class SSTVResult:
    """Universal SSTV operation result"""
    success: bool
    message: str
    mode: Optional[str] = None
    input_path: Optional[str] = None
    output_path: Optional[str] = None
    file_size: int = 0
    duration_ms: float = 0
    enhanced: bool = False
    enhancements: Optional[EnhancementOptions] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {
            "success": self.success,
            "message": self.message,
            "mode": self.mode,
            "inputPath": self.input_path,
            "outputPath": self.output_path,
            "fileSize": self.file_size,
            "duration": self.duration_ms,
            "enhanced": self.enhanced
        }
        
        if self.enhancements:
            result["enhancements"] = self.enhancements.to_dict()
        
        if self.error:
            result["error"] = self.error
            
        if self.metadata:
            result["metadata"] = self.metadata
            
        return result
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SSTVResult':
        """Create from dictionary"""
        enhancements = None
        if "enhancements" in data:
            enhancements = EnhancementOptions.from_dict(data["enhancements"])
        
        return cls(
            success=data["success"],
            message=data["message"],
            mode=data.get("mode"),
            input_path=data.get("inputPath"),
            output_path=data.get("outputPath"),
            file_size=data.get("fileSize", 0),
            duration_ms=data.get("duration", 0),
            enhanced=data.get("enhanced", False),
            enhancements=enhancements,
            error=data.get("error"),
            metadata=data.get("metadata")
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> 'SSTVResult':
        """Create from JSON string"""
        return cls.from_dict(json.loads(json_str))

@dataclass
class SSTVDecodeRequest:
    """SSTV decode request structure"""
    audio_path: str
    output_path: str
    skip_seconds: float = 0.0
    enhance: Optional[EnhancementOptions] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "audioPath": self.audio_path,
            "outputPath": self.output_path,
            "skipSeconds": self.skip_seconds
        }
        
        if self.enhance:
            result["enhance"] = self.enhance.to_dict()
            
        return result

@dataclass
class SSTVEncodeRequest:
    """SSTV encode request structure"""
    image_path: str
    output_path: str
    mode: str = "ScottieS1"
    sample_rate: int = 22050
    bits_per_sample: int = 16
    vox: bool = False
    fskid: Optional[str] = None
    resize: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "imagePath": self.image_path,
            "outputPath": self.output_path,
            "mode": self.mode,
            "sampleRate": self.sample_rate,
            "bitsPerSample": self.bits_per_sample,
            "vox": self.vox,
            "fskid": self.fskid,
            "resize": self.resize
        }