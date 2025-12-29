"""Transmission manager with PTT integration for SSTeVe.

Orchestrates the complete SSTV transmission pipeline:
1. Image preprocessing
2. VIS code generation
3. Image encoding
4. PTT control
5. Audio output
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Optional, Union

import numpy as np

from sstv_core.audio.ptt_controller import PTTController, PTTMethod
from sstv_core.audio.stream_manager import AudioStreamManager
from sstv_core.encode.image_preprocessor import ImagePreprocessor, ModeResolution
from sstv_core.encode.scottie_encoder import ScottieS1Encoder, ScottieS1EncoderConfig
from sstv_core.encode.vis_generator import VISGenerator, SSTVMode

logger = logging.getLogger(__name__)


class TXState(Enum):
    IDLE = "idle"
    PREPARING = "preparing"
    KEYING = "keying"
    TRANSMITTING = "transmitting"
    UNKEYING = "unkeying"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class TXProgress:
    state: TXState
    percent_complete: float
    current_line: int
    total_lines: int
    elapsed_sec: float
    remaining_sec: float
    message: str

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "percent_complete": self.percent_complete,
            "current_line": self.current_line,
            "total_lines": self.total_lines,
            "elapsed_sec": self.elapsed_sec,
            "remaining_sec": self.remaining_sec,
            "message": self.message,
        }


class TXManager:
    """Manages complete SSTV transmission with PTT control."""

    def __init__(
        self,
        stream_manager: AudioStreamManager,
        ptt_controller: Optional[PTTController] = None,
        sample_rate: int = 48000,
    ):
        self._stream_manager = stream_manager
        self._ptt = ptt_controller or PTTController(method=PTTMethod.NONE)
        self._sample_rate = sample_rate
        self._state = TXState.IDLE
        self._progress_callback: Optional[Callable] = None
        self._cancel_requested = False

    @property
    def state(self) -> TXState:
        return self._state

    @property
    def is_transmitting(self) -> bool:
        return self._state in (TXState.KEYING, TXState.TRANSMITTING, TXState.UNKEYING)

    def set_progress_callback(self, callback: Callable[[TXProgress], None]) -> None:
        self._progress_callback = callback

    def _emit_progress(self, percent: float, line: int, total: int,
                      elapsed: float, remaining: float, msg: str) -> None:
        if self._progress_callback:
            progress = TXProgress(
                state=self._state,
                percent_complete=percent,
                current_line=line,
                total_lines=total,
                elapsed_sec=elapsed,
                remaining_sec=remaining,
                message=msg,
            )
            self._progress_callback(progress)

    async def transmit(
        self,
        image_source: Union[str, Path, np.ndarray],
        mode: SSTVMode = SSTVMode.SCOTTIE_S1,
        output_device_index: Optional[int] = None,
    ) -> bool:
        """Transmit an image via SSTV.

        Args:
            image_source: Image file path or numpy array
            mode: SSTV mode to use
            output_device_index: Audio output device

        Returns:
            True if transmission completed successfully
        """
        import time
        start_time = time.time()
        self._cancel_requested = False

        try:
            # Phase 1: Prepare image
            self._state = TXState.PREPARING
            self._emit_progress(0, 0, 256, 0, 0, "Preparing image...")

            preprocessor = ImagePreprocessor.for_scottie_s1()
            result = preprocessor.process(image_source)
            image = result.image
            logger.info("Image preprocessed: %s", result.final_size)

            # Phase 2: Generate audio
            vis_gen = VISGenerator(sample_rate=self._sample_rate)
            vis_audio = vis_gen.generate(mode)

            encoder = ScottieS1Encoder()
            image_audio = encoder.encode_image(image)

            # Combine VIS + image audio
            if self._ptt.method == PTTMethod.VOX:
                # Add preamble and postamble for VOX
                preamble = self._ptt.generate_vox_preamble()
                postamble = self._ptt.generate_vox_postamble()
                full_audio = np.concatenate([preamble, vis_audio, image_audio, postamble])
            else:
                full_audio = np.concatenate([vis_audio, image_audio])

            total_duration = len(full_audio) / self._sample_rate
            logger.info("Total audio: %.1f seconds", total_duration)

            # Phase 3: Key radio
            self._state = TXState.KEYING
            self._emit_progress(5, 0, 256, time.time() - start_time, total_duration, "Keying radio...")
            await self._ptt.key_radio()

            if self._cancel_requested:
                await self._cleanup()
                return False

            # Phase 4: Start output stream and transmit
            self._state = TXState.TRANSMITTING
            self._stream_manager.start_output(device_index=output_device_index)

            # Write audio to output buffer
            buffer = self._stream_manager.get_output_buffer()
            if buffer:
                buffer.add(full_audio)

            # Wait for transmission to complete
            samples_remaining = len(full_audio)
            line_samples = len(image_audio) // 256
            current_line = 0

            while samples_remaining > 0 and not self._cancel_requested:
                await asyncio.sleep(0.1)
                samples_played = len(full_audio) - len(buffer) if buffer else len(full_audio)
                samples_remaining = max(0, len(full_audio) - samples_played)

                # Estimate current line
                image_samples_played = max(0, samples_played - len(vis_audio))
                if line_samples > 0:
                    current_line = min(255, image_samples_played // line_samples)

                elapsed = time.time() - start_time
                remaining = samples_remaining / self._sample_rate
                percent = ((len(full_audio) - samples_remaining) / len(full_audio)) * 100

                self._emit_progress(percent, current_line, 256, elapsed, remaining,
                                   f"Transmitting line {current_line + 1}/256")

                # Check if buffer is nearly empty
                if buffer and len(buffer) < self._sample_rate * 0.5:
                    break

            # Phase 5: Unkey radio
            self._state = TXState.UNKEYING
            self._emit_progress(95, 256, 256, time.time() - start_time, 0.5, "Unkeying radio...")
            await self._ptt.unkey_radio()

            # Stop output
            self._stream_manager.stop_output()

            self._state = TXState.COMPLETE
            elapsed = time.time() - start_time
            self._emit_progress(100, 256, 256, elapsed, 0, "Transmission complete!")
            logger.info("Transmission complete in %.1f seconds", elapsed)
            return True

        except Exception as e:
            logger.error("Transmission error: %s", e)
            self._state = TXState.ERROR
            self._emit_progress(0, 0, 256, time.time() - start_time, 0, f"Error: {e}")
            await self._cleanup()
            return False

    async def _cleanup(self) -> None:
        """Clean up after transmission."""
        try:
            if self._ptt.is_keyed:
                await self._ptt.unkey_radio()
            self._stream_manager.stop_output()
        except Exception as e:
            logger.warning("Cleanup error: %s", e)
        finally:
            self._state = TXState.IDLE

    async def cancel(self) -> None:
        """Cancel ongoing transmission."""
        self._cancel_requested = True
        logger.info("Transmission cancel requested")

    def get_estimated_duration(self, mode: SSTVMode = SSTVMode.SCOTTIE_S1) -> float:
        """Get estimated transmission duration in seconds."""
        vis_gen = VISGenerator(sample_rate=self._sample_rate)
        encoder = ScottieS1Encoder()
        vis_dur = vis_gen.get_duration_ms() / 1000
        img_dur = encoder.get_total_duration_sec()
        ptt_dur = (self._ptt.pre_delay_ms + self._ptt.post_delay_ms) / 1000
        vox_dur = self._ptt.vox_preamble_ms / 1000 if self._ptt.method == PTTMethod.VOX else 0
        return vis_dur + img_dur + ptt_dur + vox_dur
