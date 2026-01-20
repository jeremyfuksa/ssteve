"""Reception manager for SSTeVe decode operations.

Orchestrates the complete SSTV reception pipeline:
1. Audio input stream
2. VIS detection
3. Decoder selection
4. Sync detection
5. Scanline decoding
6. Image saving

NOTE: This is a simplified initial implementation. Full streaming decode
with real-time audio processing will be enhanced in future versions.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from sstv_core.audio.stream_manager import AudioStreamManager
from sstv_core.audio.bandpass_filter import SSTVBandpassFilter, BandpassPresets
from sstv_core.decode.correlation_vis_detector import CorrelationVISDetector
from sstv_core.decode.sync_detector import SyncDetector
from sstv_core.decode.scottie_decoder import ScottieS1Decoder
from sstv_core.decode.martin_decoder import MartinM1Decoder
from sstv_core.decode.robot_decoder import Robot36Decoder
from sstv_core.decode.image_saver import ImageSaver
from sstv_core.decode.hough_slant_corrector import HoughSlantCorrector
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class RXState(Enum):
    """Receive states."""
    IDLE = "idle"
    LISTENING = "listening"
    VIS_DETECTED = "vis_detected"
    DECODING = "decoding"
    SAVING = "saving"
    COMPLETE = "complete"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class RXProgress:
    """Reception progress information."""
    state: RXState
    mode: Optional[str]
    mode_confidence: float
    percent_complete: float
    current_line: int
    total_lines: int
    elapsed_sec: float
    signal_quality: float
    message: str
    audio_levels: Optional[Any] = None

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "mode": self.mode,
            "mode_confidence": self.mode_confidence,
            "percent_complete": self.percent_complete,
            "current_line": self.current_line,
            "total_lines": self.total_lines,
            "elapsed_sec": self.elapsed_sec,
            "signal_quality": self.signal_quality,
            "message": self.message,
        }


class RXManager:
    """Manages complete SSTV reception pipeline."""

    def __init__(
        self,
        stream_manager: AudioStreamManager,
        sample_rate: int = 48000,
        save_directory: Optional[Path] = None,
    ):
        self._stream_manager = stream_manager
        self._sample_rate = sample_rate
        self._save_directory = save_directory or Path.home() / "sstv_images"
        self._state = RXState.IDLE
        self._progress_callback: Optional[Callable] = None
        self._cancel_requested = False
        self._image_saver = ImageSaver(self._save_directory)

        # New: Bandpass filter for noise reduction
        self._bandpass_filter = SSTVBandpassFilter(BandpassPresets.standard())

        # New: Correlation VIS detector (replaces Goertzel)
        self._correlation_vis = CorrelationVISDetector()

        # New: Hough slant corrector for post-decode
        self._hough_corrector = HoughSlantCorrector()

    @property
    def state(self) -> RXState:
        return self._state

    @property
    def is_receiving(self) -> bool:
        return self._state in (
            RXState.LISTENING,
            RXState.VIS_DETECTED,
            RXState.DECODING,
        )

    def set_progress_callback(self, callback: Callable[[RXProgress], None]) -> None:
        """Set callback for progress updates."""
        self._progress_callback = callback

    def _emit_progress(
        self,
        mode: Optional[str],
        confidence: float,
        percent: float,
        line: int,
        total: int,
        elapsed: float,
        quality: float,
        msg: str,
        audio_levels: Optional[Any] = None,
    ) -> None:
        """Emit progress update via callback."""
        if self._progress_callback:
            progress = RXProgress(
                state=self._state,
                mode=mode,
                mode_confidence=confidence,
                percent_complete=percent,
                current_line=line,
                total_lines=total,
                elapsed_sec=elapsed,
                signal_quality=quality,
                message=msg,
                audio_levels=audio_levels,
            )
            self._progress_callback(progress)

    async def receive(
        self,
        input_device_index: Optional[int] = None,
        mode: Optional[str] = None,
        timeout_sec: float = 120.0,
        save_image: bool = True,
        callsign: Optional[str] = None,
    ) -> Optional[Path]:
        """Receive and decode an SSTV image.

        Args:
            input_device_index: Audio input device (None = default)
            mode: Force specific mode (None = auto-detect from VIS)
            timeout_sec: Timeout for VIS detection
            save_image: Whether to save decoded image
            callsign: Optional callsign for filename

        Returns:
            Path to saved image, or None if failed/cancelled
        """
        import time
        start_time = time.time()
        self._cancel_requested = False

        # Reset filters and detectors
        self._bandpass_filter.reset_state()
        self._correlation_vis.reset()

        try:
            # Phase 1: Start listening
            self._state = RXState.LISTENING
            audio_levels = self._stream_manager.get_input_levels()
            self._emit_progress(None, 0.0, 0, 0, 0, 0, "Listening for signal...", audio_levels=audio_levels)

            # Start input stream
            self._stream_manager.start_input(device_index=input_device_index)
            ring_buffer = self._stream_manager.get_input_buffer()

            if ring_buffer is None:
                raise RuntimeError("Failed to create audio ring buffer")

            # Phase 2: Detect VIS code (unless mode forced)
            detected_mode = mode
            vis_confidence = 1.0 if mode else 0.0

            if not mode:
                logger.info("Detecting VIS code (timeout: %.1fs)", timeout_sec)

                # Wait for VIS detection using correlation detector
                vis_start = time.time()
                vis_result: Optional[VISDetectionResult] = None

                while time.time() - vis_start < timeout_sec and not self._cancel_requested:
                    await asyncio.sleep(0.1)
                    samples = ring_buffer.get()

                    if len(samples) > 0:
                        # NEW: Apply bandpass filter before VIS detection
                        filtered_samples = self._bandpass_filter.filter(samples)

                        # NEW: Use correlation VIS detector (more robust)
                        vis_result = self._correlation_vis.process_samples(filtered_samples)

                        # Update audio levels
                        audio_levels = self._stream_manager.get_input_levels()

                        if vis_result and vis_result.confidence > 0.7:
                            detected_mode = vis_result.mode
                            vis_confidence = vis_result.confidence
                            logger.info(
                                "VIS detected: %s (confidence: %.2f)",
                                detected_mode,
                                vis_confidence,
                            )
                            break

                if not detected_mode:
                    logger.warning("No VIS code detected within timeout")
                    self._state = RXState.ERROR
                    audio_levels = self._stream_manager.get_input_levels()
                    self._emit_progress(
                        None, 0, 0, 0, 0, time.time() - start_time, 0,
                        "No SSTV signal detected", audio_levels=audio_levels
                    )
                    return None

            # Phase 3: Select decoder
            self._state = RXState.VIS_DETECTED
            self._emit_progress(
                detected_mode, vis_confidence, 5, 0, 256,
                time.time() - start_time, 0,
                f"Mode detected: {detected_mode}"
            )

            decoder = self._get_decoder(detected_mode)
            if decoder is None:
                raise ValueError(f"Unsupported mode: {detected_mode}")

            decoder.reset()
            total_lines = decoder.height

            # Phase 4: Decode image
            self._state = RXState.DECODING
            logger.info("Starting decode with %s", detected_mode)

            # Detect sync pulses
            sync_detector = SyncDetector(sample_rate=self._sample_rate)
            syncs_detected = []
            line_number = 0

            # Decoding loop
            while line_number < total_lines and not self._cancel_requested:
                await asyncio.sleep(0.05)  # Allow cancellation

                # Get audio samples
                samples = ring_buffer.get()
                if len(samples) == 0:
                    continue

                # Detect sync pulses
                new_syncs = sync_detector.detect_sync_pulses(samples)
                syncs_detected.extend(new_syncs)

                # If we have enough syncs, decode scanlines
                if len(syncs_detected) >= 2:
                    # Calculate scanline boundaries
                    sync_pos = syncs_detected[0]
                    next_sync = syncs_detected[1]

                    line_start = sync_pos + decoder.config.samples_per_sync
                    line_end = next_sync

                    if line_end <= len(samples):
                        # Extract scanline samples
                        line_samples = samples[line_start:line_end]

                        # Decode scanline
                        scanline = decoder.decode_scanline(line_samples, line_number)

                        # Update progress
                        progress = decoder.get_progress()
                        elapsed = time.time() - start_time

                        self._emit_progress(
                            detected_mode,
                            vis_confidence,
                            progress.percent_complete,
                            line_number + 1,
                            total_lines,
                            elapsed,
                            scanline.decode_quality,
                            f"Decoding line {line_number + 1}/{total_lines}",
                        )

                        line_number += 1
                        syncs_detected.pop(0)  # Remove processed sync

            # Check if cancelled
            if self._cancel_requested:
                self._state = RXState.STOPPED
                self._emit_progress(
                    detected_mode, vis_confidence, 0, line_number, total_lines,
                    time.time() - start_time, 0, "Decode cancelled"
                )
                return None

            # Phase 5: Save image
            if save_image:
                self._state = RXState.SAVING
                audio_levels = self._stream_manager.get_input_levels()
                self._emit_progress(
                    detected_mode, vis_confidence, 95, total_lines, total_lines,
                    time.time() - start_time, 0, "Saving image...", audio_levels=audio_levels
                )

                image = decoder.get_image()
                if image is not None:
                    # NEW: Apply Hough slant correction
                    logger.info("Applying Hough slant correction...")
                    slant_result = self._hough_corrector.correct_slant(image)

                    # Log correction results
                    if slant_result.slant_angle_degrees != 0:
                        logger.info(
                            "Slant corrected: %.2f° (confidence: %.2f, lines: %d)",
                            slant_result.slant_angle_degrees,
                            slant_result.confidence,
                            slant_result.num_lines_detected,
                        )

                    # Use corrected image if slant was detected
                    corrected_image = slant_result.corrected_image

                    # Generate filename
                    from datetime import datetime
                    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                    callsign_part = f"_{callsign}" if callsign else ""
                    filename = f"{timestamp}_{detected_mode}{callsign_part}.png"

                    # Save
                    saved_path = self._image_saver.save_image(
                        corrected_image,
                        filename=filename,
                        metadata={
                            "mode": detected_mode,
                            "callsign": callsign,
                            "timestamp": datetime.utcnow().isoformat(),
                            "vis_confidence": vis_confidence,
                            "slant_angle_degrees": float(slant_result.slant_angle_degrees),
                            "slant_confidence": slant_result.confidence,
                        },
                    )

                    logger.info("Image saved: %s", saved_path)
                else:
                    logger.warning("No image data to save")
                    saved_path = None
            else:
                saved_path = None

            # Complete
            self._state = RXState.COMPLETE
            elapsed = time.time() - start_time
            self._emit_progress(
                detected_mode, vis_confidence, 100, total_lines, total_lines,
                elapsed, 0, "Decode complete!"
            )

            logger.info("Decode complete in %.1f seconds", elapsed)
            return saved_path

        except Exception as e:
            logger.error("Reception error: %s", e, exc_info=True)
            self._state = RXState.ERROR
            self._emit_progress(
                None, 0, 0, 0, 0, time.time() - start_time, 0,
                f"Error: {e}"
            )
            return None

        finally:
            # Always stop input stream
            self._stream_manager.stop_input()
            self._state = RXState.IDLE

    def _get_decoder(self, mode: str):
        """Get decoder instance for mode."""
        mode_lower = mode.lower().replace(" ", "")

        if "scottie" in mode_lower:
            return ScottieS1Decoder()
        elif "martin" in mode_lower:
            return MartinM1Decoder()
        elif "robot" in mode_lower:
            return Robot36Decoder()
        else:
            return None

    async def cancel(self) -> None:
        """Cancel ongoing reception."""
        self._cancel_requested = True
        logger.info("Reception cancel requested")
