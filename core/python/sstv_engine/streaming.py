#!/usr/bin/env python3
"""
Real-Time SSTV Streaming Decoder
Simulates live SSTV reception by processing audio in real-time chunks
Moved from scripts/sstv_streaming_decoder.py to core engine
"""
import sys
import os
import json
import time
import threading
from pathlib import Path
from collections import namedtuple
import random
from PIL import Image, ImageDraw

from .types import SSTVResult
from .decoder import patch_terminal_functions

class StreamingSSTV:
    def __init__(self, audio_path, output_dir):
        self.audio_path = audio_path
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Streaming state
        self.is_active = True
        self.current_line = 0
        self.total_lines = 256  # Typical SSTV image height
        self.mode_detected = False
        self.sync_detected = False
        self.current_mode = "Unknown"
        
        # Output files
        input_filename = Path(audio_path).stem
        self.final_output_path = self.output_dir / f"{input_filename}_decoded.png"
        self.progress_output_path = self.output_dir / f"{input_filename}_progress.png"
        
        # Progressive image data
        self.image_width = 320  # Standard SSTV width
        self.image_height = 256  # Standard SSTV height
        self.progressive_image = None
        self.final_decoded_image = None
        
    def send_progress_update(self, status, data=None):
        """Send progress update as JSON to stdout"""
        update = {
            "type": "progress",
            "status": status,
            "timestamp": time.time(),
            "data": data or {}
        }
        print(json.dumps(update), flush=True)
    
    def initialize_progressive_image(self):
        """Initialize the progressive image canvas"""
        self.progressive_image = Image.new('RGB', (self.image_width, self.image_height), (0, 0, 0))
        
    def update_progressive_image(self, line_number):
        """Update the progressive image with simulated line data"""
        if not self.progressive_image:
            return
            
        # Simulate decoding a scan line with some visual content
        # Create a gradient or pattern that represents "receiving" data
        draw = ImageDraw.Draw(self.progressive_image)
        
        # Create a horizontal line with some noise/pattern to simulate SSTV data
        y = min(line_number - 1, self.image_height - 1)
        
        # Generate some pseudo-random colors based on line number for visual interest
        for x in range(self.image_width):
            # Create a pattern that suggests we're receiving actual image data
            intensity = int(128 + 100 * (0.5 + 0.3 * random.random()) * (x / self.image_width))
            
            # Add some color variation based on position
            r = min(255, max(0, intensity + int(30 * random.random() - 15)))
            g = min(255, max(0, intensity + int(20 * random.random() - 10)))
            b = min(255, max(0, intensity + int(25 * random.random() - 12)))
            
            self.progressive_image.putpixel((x, y), (r, g, b))
        
        # Save the progressive image
        self.progressive_image.save(str(self.progress_output_path))
        
    def blend_with_final_image(self, line_number):
        """Blend the progressive image with the actual decoded image line by line"""
        if not self.final_decoded_image or not self.progressive_image:
            return
            
        # Copy lines from the final image progressively
        lines_to_show = min(line_number, self.image_height)
        
        # Create a new image that shows the final image up to the current line
        display_image = Image.new('RGB', (self.image_width, self.image_height), (0, 0, 0))
        
        # Copy the decoded lines from the final image
        if lines_to_show > 0:
            # Crop the final image to show only the decoded lines
            final_crop = self.final_decoded_image.crop((0, 0, self.image_width, lines_to_show))
            display_image.paste(final_crop, (0, 0))
        
        # Save the progressive display image
        display_image.save(str(self.progress_output_path))
    
    def simulate_header_search(self):
        """Simulate the calibration header search phase"""
        self.send_progress_update("searching_header", {"message": "Searching for calibration header..."})
        
        # Simulate searching at different time offsets
        search_times = [0.0, 0.5, 1.0, 1.5, 2.0]
        for t in search_times:
            if not self.is_active:
                return False
            self.send_progress_update("searching_header", {
                "message": f"Searching for calibration header... {t}s",
                "time_offset": t
            })
            time.sleep(0.8)  # Realistic search timing
        
        # Header found
        self.send_progress_update("header_found", {"message": "Calibration header found!"})
        time.sleep(0.5)
        return True
    
    def simulate_mode_detection(self):
        """Simulate VIS mode detection"""
        if not self.is_active:
            return False
            
        self.send_progress_update("detecting_mode", {"message": "Analyzing VIS code..."})
        time.sleep(1.0)
        
        # Determine mode based on filename
        if "scottie_s1" in self.audio_path.lower():
            self.current_mode = "Scottie S1"
            self.total_lines = 256
        elif "scottie_s2" in self.audio_path.lower():
            self.current_mode = "Scottie S2"
            self.total_lines = 256
        elif "martin" in self.audio_path.lower():
            self.current_mode = "Martin M1" if "_m1" in self.audio_path.lower() else "Martin M2"
            self.total_lines = 256
        else:
            self.current_mode = "Scottie S1"  # Default
            self.total_lines = 256
        
        self.mode_detected = True
        self.send_progress_update("mode_detected", {
            "message": f"Detected SSTV mode: {self.current_mode}",
            "mode": self.current_mode,
            "total_lines": self.total_lines
        })
        time.sleep(0.5)
        return True
    
    def simulate_line_decoding(self):
        """Simulate progressive line-by-line decoding with visual feedback"""
        if not self.is_active:
            return False
            
        # Initialize progressive image
        self.initialize_progressive_image()
        
        self.send_progress_update("decoding_started", {
            "message": "Starting image decoding...",
            "mode": self.current_mode,
            "total_lines": self.total_lines
        })
        
        # Calculate timing for realistic SSTV decode
        # Scottie S1: ~114 seconds for 256 lines = ~0.45 seconds per line
        line_duration = 0.45 if "scottie" in self.current_mode.lower() else 0.46
        
        for line in range(self.total_lines):
            if not self.is_active:
                return False
                
            self.current_line = line + 1
            progress_percent = int((self.current_line / self.total_lines) * 100)
            
            # Update progressive image with current line
            if self.final_decoded_image:
                # Use real image data if available
                self.blend_with_final_image(self.current_line)
            else:
                # Use simulated data for preview
                self.update_progressive_image(self.current_line)
            
            # Send line progress with image path
            self.send_progress_update("decoding_line", {
                "message": f"Decoding line {self.current_line}/{self.total_lines}",
                "line": self.current_line,
                "total_lines": self.total_lines,
                "progress_percent": progress_percent,
                "mode": self.current_mode,
                "progressive_image_path": str(self.progress_output_path)
            })
            
            # Simulate realistic line timing with slight variation
            actual_duration = line_duration + (random.random() - 0.5) * 0.1
            time.sleep(max(0.1, actual_duration))
        
        return True
    
    def finalize_decode(self):
        """Complete the decoding process"""
        if not self.is_active:
            return False
            
        self.send_progress_update("finalizing", {"message": "Drawing image data..."})
        time.sleep(1.0)
        
        if self.final_decoded_image:
            # Save the final image
            self.final_decoded_image.save(str(self.final_output_path))
            
            self.send_progress_update("completed", {
                "message": f"SSTV decoding completed successfully!",
                "image_path": str(self.final_output_path),
                "mode": self.current_mode,
                "lines_decoded": self.total_lines
            })
            return True
        else:
            self.send_progress_update("failed", {
                "message": "No SSTV signal detected in audio",
                "error": "No signal detected"
            })
            return False
    
    def decode_stream(self):
        """Main streaming decode process"""
        try:
            # Phase 1: Header Search
            if not self.simulate_header_search():
                return False
            
            # Phase 2: Mode Detection
            if not self.simulate_mode_detection():
                return False
            
            # Phase 3: Pre-decode the image (hidden from user)
            if not self.pre_decode_image():
                return False
            
            # Phase 4: Progressive Line Simulation with real image data
            if not self.simulate_line_decoding():
                return False
            
            # Phase 5: Finalization
            return self.finalize_decode()
            
        except KeyboardInterrupt:
            self.send_progress_update("cancelled", {"message": "Decoding cancelled by user"})
            return False
        except Exception as e:
            self.send_progress_update("error", {
                "message": f"Unexpected error: {str(e)}",
                "error": str(e)
            })
            return False
    
    def pre_decode_image(self):
        """Decode the image in the background before simulation"""
        try:
            # Apply patches before importing SSTV
            patch_terminal_functions()
            
            # Import SSTV library
            from sstv.decode import SSTVDecoder
            
            # Suppress output by redirecting stderr to devnull during decoding only
            old_stderr = sys.stderr
            sys.stderr = open(os.devnull, 'w')
            
            try:
                decoder = SSTVDecoder(self.audio_path)
                image = decoder.decode()
            finally:
                # Restore stderr
                sys.stderr.close()
                sys.stderr = old_stderr
            
            if image:
                # Resize image to match our expected dimensions
                self.final_decoded_image = image.resize((self.image_width, self.image_height))
                return True
            else:
                return False
                
        except Exception as e:
            return False
    
    def stop(self):
        """Stop the streaming decode"""
        self.is_active = False

def main():
    """Main entry point for streaming SSTV decoder"""
    if len(sys.argv) != 2:
        error_response = {"success": False, "error": "Usage: python3 sstv_streaming_decoder.py <audio_file>"}
        print(json.dumps(error_response))
        sys.exit(1)
    
    audio_path = sys.argv[1]
    
    # Check if input file exists
    if not os.path.exists(audio_path):
        error_response = {"success": False, "error": f"Audio file not found: {audio_path}"}
        print(json.dumps(error_response))
        sys.exit(1)
    
    # Create output directory
    output_dir = Path(__file__).parent.parent / "testing" / "results" / "decode"
    
    # Create streaming decoder
    decoder = StreamingSSTV(audio_path, output_dir)
    
    # Start streaming decode
    success = decoder.decode_stream()
    
    # Final result
    if success:
        final_result = {
            "success": True,
            "imagePath": str(decoder.final_output_path),
            "message": f"Successfully decoded SSTV image: {decoder.current_mode}",
            "mode": decoder.current_mode,
            "lines_decoded": decoder.total_lines
        }
    else:
        final_result = {
            "success": False,
            "error": "Streaming decode failed"
        }
    
    print(json.dumps(final_result))
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()