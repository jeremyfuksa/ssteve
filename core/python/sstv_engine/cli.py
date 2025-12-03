"""
SSTV Engine CLI - Command-line interface for cross-platform use
"""

import argparse
import json
import sys
from pathlib import Path

from .decoder import SSTVDecoder
from .encoder import SSTVEncoder
from .enhancer import SSTVEnhancer
from .types import SSTVDecodeRequest, SSTVEncodeRequest, EnhancementOptions

def decode_cli():
    """Command-line interface for SSTV decoding"""
    parser = argparse.ArgumentParser(description="SSTV Audio Decoder")
    parser.add_argument("audio_file", help="Input SSTV audio file")
    parser.add_argument("output_file", help="Output image file")
    parser.add_argument("--skip", type=float, default=0.0, help="Skip seconds at start")
    parser.add_argument("--enhance", help="Enhancement preset (conservative, moderate, aggressive)")
    parser.add_argument("--json", action="store_true", help="Output JSON result")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    
    args = parser.parse_args()
    
    # Create decoder
    decoder = SSTVDecoder(debug=args.debug)
    
    # Check dependencies
    if not decoder.check_dependencies():
        if args.json:
            result = {"success": False, "error": "Missing colaclanth/sstv library"}
            print(json.dumps(result))
        else:
            print("❌ Error: colaclanth/sstv library not installed")
            print("Install with: pip install sstv")
        sys.exit(1)
    
    # Prepare enhancement options
    enhance = None
    if args.enhance:
        enhancer = SSTVEnhancer()
        presets = enhancer.get_presets()
        if args.enhance in presets:
            enhance = presets[args.enhance]
        else:
            if args.json:
                result = {"success": False, "error": f"Unknown preset: {args.enhance}"}
                print(json.dumps(result))
            else:
                print(f"❌ Error: Unknown preset '{args.enhance}'")
                print(f"Available presets: {', '.join(presets.keys())}")
            sys.exit(1)
    
    # Create decode request
    request = SSTVDecodeRequest(
        audio_path=args.audio_file,
        output_path=args.output_file,
        skip_seconds=args.skip,
        enhance=enhance
    )
    
    # Decode
    result = decoder.decode(request)
    
    # Output result
    if args.json:
        print(result.to_json())
    else:
        if result.success:
            print(f"✅ {result.message}")
            print(f"📊 Mode: {result.mode}")
            print(f"📁 Size: {result.file_size} bytes")
            print(f"⏱️  Duration: {result.duration_ms:.0f}ms")
            if result.enhanced:
                print("🎨 Enhanced: Yes")
        else:
            print(f"❌ {result.message}")
            if result.error:
                print(f"Error: {result.error}")
    
    sys.exit(0 if result.success else 1)

def encode_cli():
    """Command-line interface for SSTV encoding"""
    parser = argparse.ArgumentParser(description="SSTV Image Encoder")
    parser.add_argument("image_file", help="Input image file")
    parser.add_argument("output_file", help="Output SSTV audio file")
    parser.add_argument("--mode", default="ScottieS1", help="SSTV mode")
    parser.add_argument("--rate", type=int, default=22050, help="Sample rate")
    parser.add_argument("--bits", type=int, default=16, help="Bits per sample")
    parser.add_argument("--vox", action="store_true", help="Add VOX tones")
    parser.add_argument("--fskid", help="Add FSKID callsign")
    parser.add_argument("--no-resize", action="store_true", help="Don't resize image")
    parser.add_argument("--json", action="store_true", help="Output JSON result")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("--list-modes", action="store_true", help="List available modes")
    
    args = parser.parse_args()
    
    # Create encoder
    encoder = SSTVEncoder(debug=args.debug)
    
    # List modes if requested
    if args.list_modes:
        modes = encoder.get_supported_modes()
        if args.json:
            print(json.dumps({"modes": modes}))
        else:
            print("Available SSTV encoding modes:")
            for mode in modes:
                print(f"  {mode}")
        return
    
    # Check dependencies
    if not encoder.check_dependencies():
        if args.json:
            result = {"success": False, "error": "Missing PySSTV library"}
            print(json.dumps(result))
        else:
            print("❌ Error: PySSTV library not installed")
            print("Install with: pip install pysstv")
        sys.exit(1)
    
    # Create encode request
    request = SSTVEncodeRequest(
        image_path=args.image_file,
        output_path=args.output_file,
        mode=args.mode,
        sample_rate=args.rate,
        bits_per_sample=args.bits,
        vox=args.vox,
        fskid=args.fskid,
        resize=not args.no_resize
    )
    
    # Encode
    result = encoder.encode(request)
    
    # Output result
    if args.json:
        print(result.to_json())
    else:
        if result.success:
            print(f"✅ {result.message}")
            print(f"📊 Mode: {result.mode}")
            print(f"📁 Size: {result.file_size} bytes")
            print(f"⏱️  Duration: {result.duration_ms:.0f}ms")
            if result.metadata:
                print(f"🎵 Audio: {result.metadata.get('sampleRate')}Hz/{result.metadata.get('bitsPerSample')}-bit")
        else:
            print(f"❌ {result.message}")
            if result.error:
                print(f"Error: {result.error}")
    
    sys.exit(0 if result.success else 1)

def enhance_cli():
    """Command-line interface for image enhancement"""
    parser = argparse.ArgumentParser(description="SSTV Image Enhancer")
    parser.add_argument("input_file", help="Input image file")
    parser.add_argument("output_file", help="Output enhanced image file")
    parser.add_argument("--preset", help="Enhancement preset")
    parser.add_argument("--contrast", type=float, default=1.0, help="Contrast multiplier")
    parser.add_argument("--brightness", type=float, default=1.0, help="Brightness multiplier")
    parser.add_argument("--saturation", type=float, default=1.0, help="Saturation multiplier")
    parser.add_argument("--auto-level", action="store_true", help="Apply auto-level")
    parser.add_argument("--gamma", type=float, default=1.0, help="Gamma correction")
    parser.add_argument("--sharpen", action="store_true", help="Apply sharpening")
    parser.add_argument("--white-balance", action="store_true", help="Apply white balance")
    parser.add_argument("--json", action="store_true", help="Output JSON result")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("--list-presets", action="store_true", help="List available presets")
    
    args = parser.parse_args()
    
    # Create enhancer
    enhancer = SSTVEnhancer(debug=args.debug)
    
    # List presets if requested
    if args.list_presets:
        presets = enhancer.get_presets()
        if args.json:
            preset_data = {name: preset.to_dict() for name, preset in presets.items()}
            print(json.dumps({"presets": preset_data}))
        else:
            print("Available enhancement presets:")
            for name, preset in presets.items():
                print(f"  {name}: contrast={preset.contrast}, brightness={preset.brightness}")
        return
    
    # Check dependencies
    if not enhancer.check_dependencies():
        if args.json:
            result = {"success": False, "error": "Missing PIL/numpy libraries"}
            print(json.dumps(result))
        else:
            print("❌ Error: PIL/numpy libraries not installed")
            print("Install with: pip install pillow numpy")
        sys.exit(1)
    
    # Determine enhancement options
    if args.preset:
        presets = enhancer.get_presets()
        if args.preset not in presets:
            if args.json:
                result = {"success": False, "error": f"Unknown preset: {args.preset}"}
                print(json.dumps(result))
            else:
                print(f"❌ Error: Unknown preset '{args.preset}'")
                print(f"Available presets: {', '.join(presets.keys())}")
            sys.exit(1)
        options = presets[args.preset]
    else:
        options = EnhancementOptions(
            contrast=args.contrast,
            brightness=args.brightness,
            saturation=args.saturation,
            auto_level=args.auto_level,
            gamma=args.gamma,
            sharpen=args.sharpen,
            white_balance=args.white_balance
        )
    
    # Enhance
    result = enhancer.enhance_image(args.input_file, args.output_file, options)
    
    # Output result
    if args.json:
        print(result.to_json())
    else:
        if result.success:
            print(f"✅ {result.message}")
            print(f"📁 Size: {result.file_size} bytes")
            print(f"⏱️  Duration: {result.duration_ms:.0f}ms")
            if result.metadata:
                print(f"📐 Dimensions: {result.metadata.get('width')}x{result.metadata.get('height')}")
        else:
            print(f"❌ {result.message}")
            if result.error:
                print(f"Error: {result.error}")
    
    sys.exit(0 if result.success else 1)

if __name__ == "__main__":
    # Subcommand dispatcher
    if len(sys.argv) < 2:
        print("Usage: python -m sstv_engine.cli [decode|encode|enhance] ...")
        sys.exit(1)

    subcommand = sys.argv[1]
    # Remove the subcommand from argv so argparse sees the right args
    sys.argv = [sys.argv[0]] + sys.argv[2:]

    if subcommand == "decode":
        decode_cli()
    elif subcommand == "encode":
        encode_cli()
    elif subcommand == "enhance":
        enhance_cli()
    else:
        print(f"Unknown subcommand: {subcommand}")
        print("Usage: python -m sstv_engine.cli [decode|encode|enhance] ...")
        sys.exit(1)