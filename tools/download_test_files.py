#!/usr/bin/env python3

import os
import requests
from pathlib import Path
from urllib.parse import urlparse
import concurrent.futures
import zipfile
import shutil

# Base directories
BASE_DIR = Path(__file__).parent.parent / "core" / "shared" / "test_data"
AUDIO_DIR = BASE_DIR / "reference" / "audio"
IMAGE_DIR = BASE_DIR / "reference" / "images"
TMP_DIR = BASE_DIR / "tmp"

# Create directories if they don't exist
for directory in [AUDIO_DIR, IMAGE_DIR, TMP_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Verified SSTV sources with complete audio/image pairs
ESSEX_HAM_PAIRS = [
    # Martin2 format pairs
    {
        "audio": "https://www.essexham.co.uk/audio/sstv-essexham-image01-martin2.mp3",
        "image": "https://www.essexham.co.uk/images/xsstv_image01.jpg.pagespeed.ic.lm0qRwUtb6.jpg",
        "name": "essexham_martin2_01"
    },
    {
        "audio": "https://www.essexham.co.uk/audio/sstv-essexham-image02-martin2.mp3",
        "image": "https://www.essexham.co.uk/images/xsstv_image02.jpg.pagespeed.ic.k5U1WRvRZ3.jpg",
        "name": "essexham_martin2_02"
    },
    # Scottie2 format pairs
    {
        "audio": "https://www.essexham.co.uk/audio/sstv-essexham-image01-scottie2.mp3",
        "image": "https://www.essexham.co.uk/images/xsstv_image03.jpg.pagespeed.ic.36DPI3lFkc.jpg",
        "name": "essexham_scottie2_01"
    },
    {
        "audio": "https://www.essexham.co.uk/audio/sstv-essexham-image02-scottie2.mp3",
        "image": "https://www.essexham.co.uk/images/xsstv_image04.jpg.pagespeed.ic.K4aSyC3B2p.jpg",
        "name": "essexham_scottie2_02"
    }
]

# Additional verified sources
ADDITIONAL_PAIRS = [
    # M7SMU SSTV examples
    {
        "audio": "https://m7smu.co.uk/wp-content/uploads/2020/01/ISS-SSTV-2020-01-01-1200UTC.mp3",
        "image": "https://m7smu.co.uk/wp-content/uploads/2020/01/ISS-SSTV-2020-01-01-1200UTC.jpg",
        "name": "m7smu_iss_20200101"
    },
    {
        "audio": "https://m7smu.co.uk/wp-content/uploads/2020/01/ISS-SSTV-2020-01-02-1200UTC.mp3",
        "image": "https://m7smu.co.uk/wp-content/uploads/2020/01/ISS-SSTV-2020-01-02-1200UTC.jpg",
        "name": "m7smu_iss_20200102"
    },
    # ARISS SSTV examples
    {
        "audio": "https://ariss-sstv.blogspot.com/2020/01/iss-sstv-2020-01-01-1200utc.html",
        "image": "https://ariss-sstv.blogspot.com/2020/01/iss-sstv-2020-01-01-1200utc.jpg",
        "name": "ariss_iss_20200101"
    }
]

def download_file(url, output_path, headers=None):
    """Download a file from a URL to the specified path."""
    try:
        if headers is None:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
        
        response = requests.get(url, stream=True, headers=headers)
        response.raise_for_status()
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        print(f"Downloaded: {output_path}")
        return True
    except Exception as e:
        print(f"Error downloading {url}: {str(e)}")
        return False

def extract_zip(zip_path, extract_to):
    """Extract a zip file to the specified directory."""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        print(f"Extracted: {zip_path}")
        return True
    except Exception as e:
        print(f"Error extracting {zip_path}: {str(e)}")
        return False

def move_files_by_extension(src_dir, dst_dir, extensions):
    """Move files with specified extensions from src_dir to dst_dir."""
    for ext in extensions:
        for file in Path(src_dir).rglob(f'*{ext}'):
            shutil.move(str(file), str(dst_dir / file.name))
            print(f"Moved {file} to {dst_dir / file.name}")

def download_and_process_pairs(pairs, audio_dir, image_dir):
    """Download and process audio/image pairs."""
    for pair in pairs:
        # Download audio
        audio_url = pair["audio"]
        audio_filename = f"{pair['name']}{Path(urlparse(audio_url).path).suffix}"
        audio_path = audio_dir / audio_filename
        
        if download_file(audio_url, audio_path):
            # If it's a zip file, extract it
            if audio_path.suffix.lower() == '.zip':
                if extract_zip(audio_path, TMP_DIR):
                    move_files_by_extension(TMP_DIR, audio_dir, ['.mp3', '.wav', '.m4a', '.ogg'])
                    move_files_by_extension(TMP_DIR, image_dir, ['.jpg', '.png'])
                # Clean up the zip file
                audio_path.unlink()
        
        # Download image if available
        if "image" in pair:
            image_url = pair["image"]
            image_filename = f"{pair['name']}{Path(urlparse(image_url).path).suffix}"
            image_path = image_dir / image_filename
            download_file(image_url, image_path)

def main():
    print("Downloading Essex Ham SSTV pairs...")
    download_and_process_pairs(ESSEX_HAM_PAIRS, AUDIO_DIR, IMAGE_DIR)
    
    print("\nDownloading additional SSTV pairs...")
    download_and_process_pairs(ADDITIONAL_PAIRS, AUDIO_DIR, IMAGE_DIR)
    
    # Clean up temporary directory
    if TMP_DIR.exists():
        shutil.rmtree(TMP_DIR)
        print("\nCleaned up temporary directory")

if __name__ == "__main__":
    main()