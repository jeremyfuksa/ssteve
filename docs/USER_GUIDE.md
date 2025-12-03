# SSTV Station User Guide

This guide explains how to operate the SSTV Station desktop app for receiving and transmitting SSTV images. It is written for end users, not developers, and assumes you installed the desktop build or are running `npm run tauri dev` from `sstv-station/`.

## Quick Start
- Launch the app (desktop build) or run `npm run tauri dev` while the bundled Python engine is present.
- Keep the **AUTO MODE** toggle on to auto-detect common modes (Scottie and Martin families, Robot 36).
- To decode a recording, click **LOAD FILE** (or press `Ctrl+O`) and pick a WAV/MP3/OGG/FLAC file. Progress appears on the VFD display; decoded images land in the gallery.
- To encode an image, switch to **TRANSMIT**, click **ENCODE AUDIO** (or press `Ctrl+O` in transmit mode), choose a PNG/JPG/BMP file, then click **SAVE AUDIO** (or `Ctrl+S`) to store the generated WAV.
- Drag-and-drop also works: drop audio files to decode or image files to encode. The title bar updates with the current file name, and the **Recent** list in the status panel lets you reopen recent items quickly.

## Receive Mode (Decode)
1. Choose **RECEIVE** in the top button bank.
2. Click **LOAD FILE** (or drop a file) and select your recording. The status panel shows progress and any errors.
3. If **AUTO MODE** is enabled, the app picks the mode. To force a mode, uncheck **AUTO MODE** and pick from the dropdown.
4. Watch the progressive canvas while decoding; once complete, the image appears on the VFD display and is added to the gallery.
5. Use **ENHANCE** to toggle contrast/brightness/saturation sliders, or apply presets (Conservative/Moderate/Aggressive/Reset).
6. Click **SAVE IMAGE** to export the decoded image via the native dialog.

Tips:
- Keep recordings normalized and free of DC offset for best results.
- If the decode stalls, re-run with a lower input level or trim silence at the start of the file.
- Use the status text and toasts in the bottom-right for quick error context.

## Transmit Mode (Encode)
1. Switch to **TRANSMIT**.
2. Pick a mode (Scottie S1/S2/DX, Martin M1/M2, Robot 36). AUTO MODE is off in transmit because you must choose the mode to send.
3. Click **ENCODE AUDIO** (or drop an image) and select a PNG/JPG/BMP. The app builds a WAV using the bundled engine.
4. When encoding completes, **SAVE AUDIO** appears. Click it (or press `Ctrl+S`) and choose where to store the WAV. The temporary file is cleaned up after saving.
5. The status panel shows the last file name; recent items stay in the **Recent** list for quick reuse.

Encoding tips:
- Use images at or near the target aspect ratio (320x256 for Scottie/Martin). The encoder scales while preserving aspect ratio.
- Prefer PNG for sharp edges; JPEG is fine for photos.
- If encoding fails, check the toast message—corrupt or unsupported images are common culprits.

## Gallery Mode
- Open **GALLERY** to browse all images decoded during the session.
- Use **◀ PREV / NEXT ▶** to cycle. Buttons enable automatically when multiple images exist.
- Saving an image from the gallery uses the same **SAVE IMAGE** control in the status area.

## Settings
- The **SETTINGS** tab is minimal in this version; device info is shown in the status panel. Mic capture is used only for the live “START LISTENING” demo.
- Keyboard shortcuts: `Ctrl+O` opens a file (audio in Receive, image in Transmit); `Ctrl+S` saves the current artifact (encoded audio in Transmit if available, otherwise the current decoded image).
- Drag-and-drop: drop audio files anywhere on the app to decode; drop images to encode. Unsupported files show an error toast.

## Troubleshooting
- **“Tauri bridge unavailable”**: You are in the browser preview. Install/run the desktop build to access file dialogs and the Python engine.
- **“Python engine not found”**: Ensure the bundled Python directory exists under `sstv-station/src-tauri/resources/python/` (built) or `core/python/.venv/` (dev). Re-run `tools/bundle_python.sh` if missing.
- **Decode fails or produces noise**: Verify the recording is mono or stereo PCM, trim silence, and ensure the sample rate is 44.1k/48k or the standard 22.05k. Extremely compressed MP3s can lose sync—try WAV instead.
- **Encode fails**: Make sure the image is a valid PNG/JPG/BMP and smaller than a few megapixels. If you see a mode error, pick a supported mode from the dropdown.
- **No file dialog appears**: On some Linux desktops, the native dialog needs X11/Wayland. Run the app from a session with GUI access or use `npm run tauri dev` with `xvfb-run` in headless setups.
- **Recent files not opening**: The recent list stores absolute paths. If files were moved or removed, re-open them via **LOAD FILE**/**ENCODE AUDIO** to refresh the list.

## Getting Help
- For issues with bundled Python, confirm your environment matches the project prerequisites (Node 18+, Rust toolchain, Python 3.10+).
- Reference sample assets live in `core/shared/testing/reference/`; use them to validate decoding behavior.
- File bug reports with the mode used, the source file (if shareable), and the platform (Windows/macOS/Linux). Screenshots of the status panel and toast messages help diagnose problems quickly.
