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
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np

from sstv_core.audio.bandpass_filter import BandpassPresets, SSTVBandpassFilter
from sstv_core.audio.stream_manager import AudioStreamManager
from sstv_core.decode.correlation_vis_detector import (
    CorrelationVISConfig,
    CorrelationVISDetector,
)
from sstv_core.decode.hough_slant_corrector import HoughSlantCorrector
from sstv_core.decode.image_saver import ImageSaver
from sstv_core.decode.martin_decoder import MartinM1Config, MartinM1Decoder
from sstv_core.decode.robot_decoder import Robot36Config, Robot36Decoder
from sstv_core.decode.rsv import DecodeMetrics
from sstv_core.decode.scottie_decoder import ScottieS1Config, ScottieS1Decoder
from sstv_core.decode.sync_detector import SyncPulseDetector

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
    mode: str | None
    mode_confidence: float
    percent_complete: float
    current_line: int
    total_lines: int
    elapsed_sec: float
    signal_quality: float
    message: str
    audio_levels: Any | None = None

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
        save_directory: Path | None = None,
        slant_correction: bool = False,
        auto_afc: bool = True,
        afc_range_hz: float = 100.0,
        auto_squelch: bool = False,
        squelch_threshold_db: float = -40.0,
    ):
        self._stream_manager = stream_manager
        self._sample_rate = sample_rate
        self._save_directory = save_directory or Path.home() / "sstv_images"
        self._state = RXState.IDLE
        self._progress_callback: Callable | None = None
        self._cancel_requested = False
        self._image_saver = ImageSaver(self._save_directory)

        # New: Bandpass filter for noise reduction
        self._bandpass_filter = SSTVBandpassFilter(BandpassPresets.standard())

        # Correlation VIS detector, built for THIS stream's sample rate.
        # Constructing it bare left it at the 48000 Hz default, so its
        # templates were the wrong length for any other rate -- the same class
        # of bug that made the decoders unusable at 11025 and 22050 Hz.
        self._correlation_vis = CorrelationVISDetector(
            CorrelationVISConfig(sample_rate=sample_rate)
        )

        # Hough slant corrector, opt-in. See the decision recorded at the call
        # site in `receive` for the measurements behind the default.
        self._hough_corrector = HoughSlantCorrector()
        self._slant_correction_enabled = slant_correction

        # Measured decode metrics for the most recent session (Auto-RSV).
        self._metrics: DecodeMetrics | None = None

        # FSKID result from the most recent decode (None = none detected).
        self._fskid_result: Any | None = None

        # Rolling window of RAW input for on-demand analysis (session-based
        # mode detection). ~15s covers >30 scanlines of every mode.
        self._analysis_window = np.zeros(0, dtype=np.float32)
        self._analysis_window_samples = sample_rate * 15

        # AFC: correct the video frequency mapping by the measured sync
        # offset. Manual override is auto_afc=False -- auto-only AFC is
        # dangerous for satellite (Doppler) work, so the switch must exist.
        self._auto_afc = auto_afc
        self._afc_range_hz = afc_range_hz

        # Squelch: skip VIS processing while input sits below the
        # threshold. auto_squelch=False = wide open (manual override).
        self._auto_squelch = auto_squelch
        self._squelch_threshold_db = squelch_threshold_db

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

    def _measure_pulse_offset(
        self,
        stream_audio: np.ndarray,
        stream_base_position: int,
        pulse: Any,
    ) -> float | None:
        """Measured frequency of one sync pulse minus nominal 1200 Hz.

        Uses the Hilbert instantaneous-frequency estimator over the pulse
        interior (edges trimmed -- they blend into video). Returns None
        when the pulse is not fully buffered or the estimate is wild.
        """
        from sstv_core.decode.demodulator import instantaneous_frequency

        start = pulse.position_samples - stream_base_position
        length = int(pulse.duration_ms * self._sample_rate / 1000.0)
        if start < 0 or length < 8 or start + length > len(stream_audio):
            return None
        trim = max(1, length // 5)
        window = stream_audio[start + trim : start + length - trim]
        if len(window) < 4:
            return None
        freqs = instantaneous_frequency(window, self._sample_rate)
        measured = float(np.median(freqs))
        offset = measured - 1200.0
        # A sync estimate outside +-300 Hz is video bleed, not an offset.
        if abs(offset) > 300.0:
            return None
        return offset

    def get_recent_audio(self) -> np.ndarray:
        """Copy of the last ~15s of raw input (session mode detection)."""
        window: np.ndarray = self._analysis_window.copy()
        return window

    def _extend_analysis_window(self, samples: np.ndarray) -> None:
        self._analysis_window = np.concatenate(
            (self._analysis_window, samples)
        )[-self._analysis_window_samples:]

    def get_fskid_result(self) -> Any | None:
        """FSKID callsign result from the most recent decode, if any."""
        return self._fskid_result

    def get_decode_metrics(self) -> DecodeMetrics | None:
        """Measured metrics for the current/most recent decode (Auto-RSV)."""
        return self._metrics

    @property
    def current_snr_db(self) -> float | None:
        """Live SNR estimate, or None before noise floor + signal exist."""
        m = self._metrics
        if m is None or m.noise_floor <= 0.0 or m.peak_amplitude <= 0.0:
            return None
        return m.snr_db

    def _emit_progress(
        self,
        mode: str | None,
        confidence: float,
        percent: float,
        line: int,
        total: int,
        elapsed: float,
        quality: float,
        msg: str,
        audio_levels: Any | None = None,
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
        input_device_index: int | None = None,
        mode: str | None = None,
        timeout_sec: float = 120.0,
        save_image: bool = True,
        callsign: str | None = None,
    ) -> Path | None:
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

        # Reset filters, detectors, and per-session measurements
        self._bandpass_filter.reset_state()
        self._correlation_vis.reset()
        self._metrics = DecodeMetrics()
        self._fskid_result = None
        self._analysis_window = np.zeros(0, dtype=np.float32)
        pre_vis_rms: list[float] = []

        try:
            # Phase 1: Start listening
            self._state = RXState.LISTENING
            audio_levels = self._stream_manager.get_input_levels()
            self._emit_progress(
                None, 0.0, 0, 0, 0, 0, 0, "Listening for signal...", audio_levels=audio_levels
            )

            # Start input stream
            self._stream_manager.start_input(device_index=input_device_index)
            ring_buffer = self._stream_manager.get_input_buffer()

            if ring_buffer is None:
                raise RuntimeError("Failed to create audio ring buffer")

            # Phase 2: Detect VIS code (unless mode forced)
            detected_mode = mode
            vis_confidence = 1.0 if mode else 0.0
            stream_position = 0
            vis_tail = np.array([], dtype=np.float32)
            vis_tail_samples = self._sample_rate * 2

            if not mode:
                logger.info("Detecting VIS code (timeout: %.1fs)", timeout_sec)

                # Wait for VIS detection using correlation detector
                vis_start = time.time()
                vis_result = None

                while time.time() - vis_start < timeout_sec and not self._cancel_requested:
                    await asyncio.sleep(0.1)
                    samples = ring_buffer.pop(len(ring_buffer))

                    if len(samples) > 0:
                        stream_position += len(samples)
                        vis_tail = np.concatenate((vis_tail, samples))[
                            -vis_tail_samples:
                        ]

                        self._extend_analysis_window(samples)

                        # Noise floor: RMS of pre-signal chunks. The lower
                        # quartile rejects the chunks that already contain
                        # the transmission's leading edge.
                        chunk_rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
                        pre_vis_rms.append(chunk_rms)

                        # Squelch: below the threshold there is no signal to
                        # correlate against; skip the (expensive) VIS work
                        # but keep the chunk counted in the noise floor.
                        if self._auto_squelch:
                            rms_db = (
                                20.0 * float(np.log10(chunk_rms))
                                if chunk_rms > 0
                                else -120.0
                            )
                            if rms_db < self._squelch_threshold_db:
                                continue

                        # The correlation detector bandpasses internally
                        # (CorrelationVISConfig.enable_pre_filter), so feed it
                        # raw samples. Filtering here too cascaded two
                        # 4th-order Butterworths (~-6 dB at the 2300 Hz edge).
                        vis_result = self._correlation_vis.process_samples(samples)

                        # Update audio levels
                        audio_levels = self._stream_manager.get_input_levels()

                        if vis_result and vis_result.confidence > 0.7:
                            detected_mode = self._mode_name(vis_result.mode)
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

            # Finalize pre-signal measurements
            if pre_vis_rms:
                quietest = sorted(pre_vis_rms)[: max(1, len(pre_vis_rms) // 4)]
                self._metrics.noise_floor = float(np.mean(quietest))
            self._metrics.vis_confidence = vis_confidence
            # The correlation detector identifies mode by envelope matching
            # and does not decode the parity bit; a forced mode skips VIS
            # entirely. Neither case is evidence of a parity FAILURE.
            self._metrics.vis_parity_valid = True

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

            # Shortest gap accepted between line starts, from the selected
            # mode's own line time. See SyncPulseDetector.LINE_SPACING_TOLERANCE.
            min_line_samples = int(
                decoder.config.total_line_samples * SyncPulseDetector.LINE_SPACING_TOLERANCE
            )

            # Detect sync pulses
            sync_detector = SyncPulseDetector(sample_rate=self._sample_rate)
            sync_positions: list[int] = []
            sync_intervals_ms: list[float] = []
            afc_samples_hz: list[float] = []
            afc_locked = False
            for pulse in sync_detector.process_samples(
                vis_tail,
                position=stream_position - len(vis_tail),
            ):
                if (
                    sync_positions
                    and pulse.position_samples - sync_positions[-1] < min_line_samples
                ):
                    continue
                sync_positions.append(pulse.position_samples)
            stream_audio = vis_tail.copy()
            stream_base_position = stream_position - len(vis_tail)
            line_number = 0
            last_sync_time = time.monotonic()

            # Decoding loop
            while line_number < total_lines and not self._cancel_requested:
                await asyncio.sleep(0.05)  # Allow cancellation

                # Consume each input sample exactly once.
                if ring_buffer.dropped_samples > 0:
                    # Overflow broke the gapless-stream assumption every sync
                    # position depends on; the decode would silently tear.
                    raise RuntimeError(
                        f"Audio buffer overflowed ({ring_buffer.dropped_samples} "
                        "samples lost) -- the decode timeline is corrupted. "
                        "Is the machine overloaded?"
                    )
                samples = ring_buffer.pop(len(ring_buffer))
                if len(samples) == 0:
                    stalled_sec = time.monotonic() - last_sync_time
                    if stalled_sec > 2.0 and line_number > 0:
                        # The signal has ended. A line only completes when
                        # the NEXT sync arrives, so the final line has no
                        # closer -- silence follows the transmission. Flush
                        # any pending line using the mode's nominal length,
                        # then finish with what was decoded. Without this,
                        # every live decode stalled at the last line and
                        # timed out (found by the first end-to-end live
                        # pipeline test, 2026-08-08).
                        flushed = False
                        if sync_positions:
                            nominal = decoder.config.total_line_samples
                            line_start = sync_positions[0] - stream_base_position
                            if (
                                0 <= line_start
                                and line_start + nominal <= len(stream_audio)
                            ):
                                tail_line = stream_audio[
                                    line_start : line_start + nominal
                                ]
                                scanline = decoder.decode_scanline(
                                    tail_line, line_number
                                )
                                self._metrics.scanline_confidences.append(
                                    float(scanline.decode_quality)
                                )
                                line_number += 1
                                sync_positions.pop(0)
                                flushed = True
                        if not flushed:
                            logger.info(
                                "Signal ended after %d/%d lines; finishing",
                                line_number,
                                total_lines,
                            )
                            break
                        continue
                    if stalled_sec > 5.0:
                        raise TimeoutError("No scanline sync received for 5 seconds")
                    continue

                self._extend_analysis_window(samples)

                # Peak level from the RAW audio -- the filter would hide
                # clipping and level problems the metric exists to expose.
                chunk_peak = float(np.max(np.abs(samples)))
                if chunk_peak > self._metrics.peak_amplitude:
                    self._metrics.peak_amplitude = chunk_peak
                    if self._metrics.noise_floor > 0.0:
                        self._metrics.snr_db = 20.0 * float(
                            np.log10(chunk_peak / self._metrics.noise_floor)
                        )

                # Bandpass the image audio. The filter's documented job is to
                # clean the whole DSP path, but until 2026-08-07 it ran only
                # in the VIS phase (twice, cascaded with the correlation
                # detector's internal filter) and the decode loop got raw
                # audio. The stateful streaming path keeps chunk continuity.
                samples = self._bandpass_filter.filter(samples)

                chunk_position = stream_position
                stream_position += len(samples)
                stream_audio = np.concatenate((stream_audio, samples))

                new_syncs = sync_detector.process_samples(
                    samples,
                    position=chunk_position,
                )
                if new_syncs:
                    last_sync_time = time.monotonic()
                    # Drop pulses arriving well inside the current line: those
                    # are picture content that momentarily looked like 1200 Hz,
                    # and treating them as line starts tears the image. The
                    # mode is known here, so the real line time is too.
                    for pulse in new_syncs:
                        if (
                            sync_positions
                            and pulse.position_samples - sync_positions[-1] < min_line_samples
                        ):
                            continue
                        if sync_positions:
                            interval_ms = (
                                (pulse.position_samples - sync_positions[-1])
                                * 1000.0 / self._sample_rate
                            )
                            sync_intervals_ms.append(interval_ms)
                        sync_positions.append(pulse.position_samples)

                        # AFC: the sync pulse is a known 1200 Hz reference,
                        # so its measured frequency IS the receiver's offset.
                        if not afc_locked:
                            offset = self._measure_pulse_offset(
                                stream_audio, stream_base_position, pulse
                            )
                            if offset is not None:
                                afc_samples_hz.append(offset)

                # Lock AFC once three pulses agree; correct the decoder's
                # video mapping by the median offset, clamped to the
                # configured range. auto_afc=False leaves the mapping alone
                # (Doppler/satellite work needs the manual override).
                if not afc_locked and len(afc_samples_hz) >= 3:
                    afc_locked = True
                    measured = float(np.median(afc_samples_hz))
                    clamped = max(-self._afc_range_hz, min(self._afc_range_hz, measured))
                    self._metrics.afc_correction_hz = clamped
                    if self._auto_afc and abs(clamped) >= 5.0:
                        decoder.config.black_freq += clamped
                        decoder.config.white_freq += clamped
                        logger.info(
                            "AFC: correcting video mapping by %+.1f Hz "
                            "(measured %+.1f)", clamped, measured
                        )

                # Decode every complete frame currently buffered.
                while len(sync_positions) >= 2 and line_number < total_lines:
                    sync_pos = sync_positions[0]
                    next_sync = sync_positions[1]
                    line_start = sync_pos - stream_base_position
                    line_end = next_sync - stream_base_position

                    if line_start < 0:
                        sync_positions.pop(0)
                        continue
                    if line_end > len(stream_audio):
                        break

                    line_samples = stream_audio[line_start:line_end]

                    # Decode scanline
                    scanline = decoder.decode_scanline(line_samples, line_number)
                    self._metrics.scanline_confidences.append(
                        float(scanline.decode_quality)
                    )

                    # Update progress
                    progress = decoder.get_progress()
                    elapsed = time.time() - start_time

                    # Levels ride along on every line (~2-7 Hz depending on
                    # mode) so the UI's meter and waterfall stay live during
                    # decode -- previously they updated about three times per
                    # session.
                    self._emit_progress(
                        detected_mode,
                        vis_confidence,
                        progress.percent_complete,
                        line_number + 1,
                        total_lines,
                        elapsed,
                        scanline.decode_quality,
                        f"Decoding line {line_number + 1}/{total_lines}",
                        audio_levels=self._stream_manager.get_input_levels(),
                    )

                    line_number += 1
                    sync_positions.pop(0)

                    # Retain the remaining sync and following audio only.
                    keep_from = sync_positions[0] - stream_base_position
                    if keep_from > 0:
                        stream_audio = stream_audio[keep_from:]
                        stream_base_position += keep_from

            # FSKID: the callsign ID follows the image immediately
            # (docs/features/FSKID_SPECIFICATION.md). Only worth looking for
            # after a full decode; collect up to ~3s more audio.
            if line_number >= total_lines and not self._cancel_requested:
                fskid_tail = stream_audio
                fskid_deadline = time.monotonic() + 3.0
                fskid_needed = int(self._sample_rate * 3.0)
                while (
                    len(fskid_tail) < len(stream_audio) + fskid_needed
                    and time.monotonic() < fskid_deadline
                ):
                    await asyncio.sleep(0.1)
                    extra = ring_buffer.pop(len(ring_buffer))
                    if len(extra):
                        fskid_tail = np.concatenate(
                            (fskid_tail, self._bandpass_filter.filter(extra))
                        )
                try:
                    from sstv_core.decode.fsk_decoder import FSKIDDecoder

                    self._fskid_result = FSKIDDecoder(
                        sample_rate=self._sample_rate
                    ).decode(fskid_tail)
                    if self._fskid_result:
                        logger.info(
                            "FSKID: %s (confidence %.2f, checksum %s)",
                            self._fskid_result.callsign,
                            self._fskid_result.confidence,
                            "ok" if self._fskid_result.checksum_valid else "BAD",
                        )
                except Exception as exc:
                    # FSKID is a bonus; its failure must not fail the decode.
                    logger.warning("FSKID decode error: %s", exc)

            # Finalize timing metrics for Auto-RSV
            if len(sync_intervals_ms) >= 3:
                self._metrics.sync_pulse_jitter_ms = float(np.std(sync_intervals_ms))
            self._metrics.rx_quality_score = (
                self._metrics.mean_scanline_quality
            )

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
                    # Hough slant correction is OFF by default. Measured on the
                    # reference corpus with its confidence gate removed, it
                    # lowered SSIM on 5 of 9 files and helped 1, by large
                    # margins: winter_creek 0.499 -> 0.225, operator_shack
                    # 0.343 -> 0.077. It infers a rotation angle from image
                    # content and reports -13 to -15 degrees on pictures that
                    # are not slanted, then resamples away detail the radio
                    # actually delivered.
                    #
                    # With the shipped 0.7 confidence gate it is inert on every
                    # reference file anyway (confidences measure 0.00-0.45), so
                    # this changes no behaviour today -- it makes the default
                    # honest and stops a latent regression if that gate is ever
                    # lowered. See PRODUCT.md "Explicitly undecided" for the
                    # timing-based alternative.
                    corrected_image = image
                    if self._slant_correction_enabled:
                        logger.info("Applying Hough slant correction...")
                        self._metrics.slant_correction_applied = True
                        slant_result = self._hough_corrector.correct_slant(image)
                        if slant_result.slant_angle_degrees != 0:
                            logger.info(
                                "Slant corrected: %.2f° (confidence: %.2f, lines: %d)",
                                slant_result.slant_angle_degrees,
                                slant_result.confidence,
                                slant_result.num_lines_detected,
                            )
                        corrected_image = slant_result.corrected_image

                    saved_path = self._image_saver.save_image(
                        image_array=corrected_image,
                        mode=detected_mode or "Unknown",
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
            # Re-raise so the caller can tell "failed" from "found nothing".
            # Swallowing errors here made every failure -- bad device, decode
            # crash, anything -- present to API clients as a session that
            # cleanly "stopped" with error: null.
            raise

        finally:
            # Always stop input stream
            self._stream_manager.stop_input()
            self._state = RXState.IDLE

    @staticmethod
    def _mode_name(mode: Any) -> str:
        """Normalize a VIS enum or user string to the public mode spelling."""
        name = getattr(mode, "name", None)
        names = {
            "SCOTTIE_S1": "ScottieS1",
            "MARTIN_M1": "MartinM1",
            "ROBOT_36": "Robot36",
        }
        if name in names:
            return names[name]
        return str(mode)

    def _get_decoder(self, mode: str):
        """Get decoder instance for mode, configured for the stream's rate.

        The sample rate must be passed explicitly: decoder configs default to
        48000 Hz, and every timing property (samples per line, per sync, per
        colour channel) derives from it. A decoder left at the default while
        the stream runs at 22050 reads four times too much audio per line and
        decodes nothing usable.
        """
        mode_lower = mode.lower().replace(" ", "").replace("_", "")
        rate = self._sample_rate

        if mode_lower == "scotties1":
            return ScottieS1Decoder(ScottieS1Config(sample_rate=rate))
        elif mode_lower == "martinm1":
            return MartinM1Decoder(MartinM1Config(sample_rate=rate))
        elif mode_lower == "robot36":
            return Robot36Decoder(Robot36Config(sample_rate=rate))
        else:
            return None

    async def cancel(self) -> None:
        """Cancel ongoing reception."""
        self._cancel_requested = True
        logger.info("Reception cancel requested")
