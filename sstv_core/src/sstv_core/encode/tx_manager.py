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
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import numpy as np

from sstv_core.audio.ptt_controller import PTTController, PTTMethod
from sstv_core.audio.stream_manager import AudioStreamManager
from sstv_core.encode.image_preprocessor import (
    ImagePreprocessor,
    ModeResolution,
    overlay_callsign,
)
from sstv_core.encode.martin_encoder import MartinM1Encoder
from sstv_core.encode.robot_encoder import Robot36Encoder
from sstv_core.encode.scottie_encoder import ScottieS1Encoder
from sstv_core.encode.vis_generator import SSTVMode, VISGenerator

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
        ptt_controller: PTTController | None = None,
        sample_rate: int = 48000,
    ):
        self._stream_manager = stream_manager
        self._ptt = ptt_controller or PTTController(method=PTTMethod.NONE)
        self._sample_rate = sample_rate
        self._state = TXState.IDLE
        self._progress_callback: Callable | None = None
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

    def _get_encoder(self, mode: SSTVMode):
        """Return an implemented encoder for the requested mode."""
        encoder_types = {
            SSTVMode.SCOTTIE_S1: ScottieS1Encoder,
            SSTVMode.MARTIN_M1: MartinM1Encoder,
            SSTVMode.ROBOT_36: Robot36Encoder,
        }
        try:
            return encoder_types[mode]()
        except KeyError as exc:
            supported = ", ".join(item.name for item in encoder_types)
            raise ValueError(
                f"Unsupported transmit mode {mode.name}; implemented modes: {supported}"
            ) from exc

    async def transmit(
        self,
        image_source: str | Path | np.ndarray,
        mode: SSTVMode = SSTVMode.SCOTTIE_S1,
        output_device_index: int | None = None,
        callsign: str | None = None,
    ) -> bool:
        """Transmit an image via SSTV.

        Args:
            image_source: Image file path or numpy array
            mode: SSTV mode to use
            output_device_index: Audio output device
            callsign: Optional operator callsign to overlay on the image

        Returns:
            True if transmission completed successfully

        """
        import time
        start_time = time.time()
        self._cancel_requested = False

        try:
            # Phase 1: Prepare image
            self._state = TXState.PREPARING
            encoder = self._get_encoder(mode)
            total_lines = encoder.config.height
            self._emit_progress(0, 0, total_lines, 0, 0, "Preparing image...")

            resolution = ModeResolution(
                width=encoder.config.width,
                height=encoder.config.height,
                aspect_ratio=encoder.config.width / encoder.config.height,
            )
            preprocessor = ImagePreprocessor(target_resolution=resolution)
            result = preprocessor.process(image_source)
            image = result.image
            if callsign:
                # The API has always promised "callsign overlaid on image";
                # until 2026-08-07 the value was accepted and dropped.
                image = overlay_callsign(image, callsign)
            logger.info("Image preprocessed: %s", result.final_size)

            # Phase 2: Generate audio. The manager assembles its own VIS
            # header (it needs the segment separately for playback-offset
            # math), so the encoder must NOT prepend another one --
            # encode_image defaults include_vis=True, and until 2026-08-07
            # every transmission carried a double VIS header.
            vis_gen = VISGenerator(sample_rate=self._sample_rate)
            vis_audio = vis_gen.generate(mode)

            image_audio = encoder.encode_image(image, include_vis=False)

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
            self._emit_progress(
                5,
                0,
                total_lines,
                time.time() - start_time,
                total_duration,
                "Keying radio...",
            )
            await self._ptt.key_radio()

            if self._cancel_requested:
                await self._cleanup()
                return False

            # Phase 4: Start output stream and transmit
            self._state = TXState.TRANSMITTING
            playback_lock = threading.Lock()
            playback_offset = 0

            def output_callback(frames: int) -> np.ndarray:
                """Supply exactly one output block without truncating audio."""
                nonlocal playback_offset
                block = np.zeros(frames, dtype=np.float32)
                with playback_lock:
                    remaining = len(full_audio) - playback_offset
                    count = min(frames, max(0, remaining))
                    if count:
                        block[:count] = full_audio[
                            playback_offset : playback_offset + count
                        ]
                        playback_offset += count
                return block

            self._stream_manager.start_output(
                device_index=output_device_index,
                callback=output_callback,
            )

            # Wait for transmission to complete
            samples_remaining = len(full_audio)
            line_samples = len(image_audio) // total_lines
            current_line = 0

            while samples_remaining > 0 and not self._cancel_requested:
                await asyncio.sleep(0.1)
                with playback_lock:
                    samples_played = playback_offset
                samples_remaining = max(0, len(full_audio) - samples_played)

                # Estimate current line
                image_samples_played = max(0, samples_played - len(vis_audio))
                if line_samples > 0:
                    current_line = min(
                        total_lines - 1,
                        image_samples_played // line_samples,
                    )

                elapsed = time.time() - start_time
                remaining = samples_remaining / self._sample_rate
                percent = ((len(full_audio) - samples_remaining) / len(full_audio)) * 100

                self._emit_progress(
                    percent,
                    current_line,
                    total_lines,
                    elapsed,
                    remaining,
                    f"Transmitting line {current_line + 1}/{total_lines}",
                )

            if self._cancel_requested:
                # Cooperative cancel mid-transmission: unkey and report
                # failure. Falling through here used to unkey but then mark
                # the aborted transmission COMPLETE.
                await self._cleanup()
                return False

            # Phase 5: Unkey radio
            self._state = TXState.UNKEYING
            self._emit_progress(
                95,
                total_lines,
                total_lines,
                time.time() - start_time,
                0.5,
                "Unkeying radio...",
            )
            await self._ptt.unkey_radio()

            # Stop output
            self._stream_manager.stop_output()

            self._state = TXState.COMPLETE
            elapsed = time.time() - start_time
            self._emit_progress(
                100,
                total_lines,
                total_lines,
                elapsed,
                0,
                "Transmission complete!",
            )
            logger.info("Transmission complete in %.1f seconds", elapsed)
            return True

        except asyncio.CancelledError:
            # A hard task.cancel() raises here from whatever await was
            # pending. Without this handler the radio stayed keyed and the
            # output stream stayed open -- a dead-key on a live transmitter.
            logger.info("Transmission cancelled; unkeying radio")
            self._state = TXState.ERROR
            await self._cleanup()
            raise

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
        encoder = self._get_encoder(mode)
        vis_dur = vis_gen.get_duration_ms() / 1000
        img_dur = encoder.get_total_duration_sec()
        ptt_dur = (self._ptt.pre_delay_ms + self._ptt.post_delay_ms) / 1000
        vox_dur = self._ptt.vox_preamble_ms / 1000 if self._ptt.method == PTTMethod.VOX else 0
        return float(vis_dur + img_dur + ptt_dur + vox_dur)
