"""Enhanced VIS detector with correlation-based detection.

Uses cross-correlation with known VIS waveform templates for robust
detection in noisy conditions (-15 dB SNR), significantly outperforming
simple Goertzel tone detection.

Reference: Black Cat SSTV benchmark - correlation detects at -15 dB SNR
vs tone detection which fails at -5 dB SNR.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import ClassVar

import numpy as np
from scipy import signal

from sstv_core.decode.demodulator import instantaneous_frequency
from sstv_core.decode.vis_detector import SSTVMode, VISDetectionResult

logger = logging.getLogger(__name__)

# Envelope resolution. VIS data bits are 30ms, so 1kHz gives 30 points per bit
# -- far more than needed to tell 1100 Hz from 1300 Hz, while making the
# correlation search cheap enough to run on every incoming chunk.
ENVELOPE_RATE_HZ = 1000


def frequency_envelope(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    """Instantaneous frequency of `samples`, decimated to ENVELOPE_RATE_HZ.

    The matching domain for VIS detection. See VISWaveformTemplate.envelope
    for why frequency rather than raw samples.
    """
    if len(samples) < 4:
        return np.zeros(0, dtype=np.float64)
    decimation = max(1, sample_rate // ENVELOPE_RATE_HZ)
    return instantaneous_frequency(samples, sample_rate)[::decimation]


class VISWaveformTemplate:
    """VIS waveform template for correlation detection."""

    def __init__(
        self,
        mode: SSTVMode,
        sample_rate: int = 48000,
    ) -> None:
        self.mode = mode
        self._sample_rate = sample_rate

        # Generate the complete VIS waveform for this mode
        self._waveform = self._generate_vis_waveform(mode)
        self._envelope = frequency_envelope(self._waveform, sample_rate)

    @property
    def waveform(self) -> np.ndarray:
        """Get the VIS waveform template."""
        return self._waveform

    @property
    def envelope(self) -> np.ndarray:
        """Frequency envelope of the template, decimated.

        Matching happens on this rather than on the raw waveform. A 1900 Hz
        carrier decorrelates within one cycle, so raw-sample correlation needs
        alignment to about one sample: measured, it falls from 1.00 to 0.45
        after five samples of offset. Searching 43,680 offsets across eleven
        templates for every incoming chunk is not viable in a live stream.

        Instantaneous frequency carries the same information and is phase
        independent, so the envelope still correlates above 0.89 at 20ms of
        misalignment -- a tolerance roughly 400x wider, which a coarse search
        can actually cover.
        """
        return self._envelope

    def _generate_vis_waveform(self, mode: SSTVMode) -> np.ndarray:
        """Generate VIS waveform for a given mode.

        VIS structure (from SSTV specification):
        - Leader tone: 1900 Hz for 300ms
        - Break: 1200 Hz for 10ms
        - Leader tone: 1900 Hz for 300ms
        - Start bit: 1200 Hz for 30ms
        - 8 data bits: 1100 Hz = 1, 1300 Hz = 0, each 30ms
        - Stop bit: 1200 Hz for 30ms

        The 8 data bits encode the VIS code in LSB first order.
        """
        # Convert VIS code to binary
        vis_code = mode.value
        bits = [(vis_code >> i) & 1 for i in range(8)]  # LSB first

        # Durations in SECONDS. The previous code multiplied these values by
        # `sample_rate / 1000` (samples per millisecond) while holding them in
        # seconds, so every segment came out 1000x too short: the 300ms leader
        # was 14 samples, the 10ms break was 0 samples, and each 30ms data bit
        # was 1 sample. Every template collapsed to 38 samples of near-identical
        # noise, all eleven the same length, carrying no VIS information at all
        # -- which is why mode auto-detection never once succeeded.
        leader_duration_s = 0.300
        break_duration_s = 0.010
        bit_duration_s = 0.030

        def samples_for(duration_s: float) -> int:
            return int(duration_s * self._sample_rate)

        segments = []

        # Leader tone (1900 Hz, 300ms)
        segments.append(self._generate_tone(1900.0, samples_for(leader_duration_s)))

        # Break (1200 Hz, 10ms)
        segments.append(self._generate_tone(1200.0, samples_for(break_duration_s)))

        # Second leader tone (1900 Hz, 300ms)
        segments.append(self._generate_tone(1900.0, samples_for(leader_duration_s)))

        # Start bit (1200 Hz, 30ms)
        segments.append(self._generate_tone(1200.0, samples_for(bit_duration_s)))

        # 8 data bits, LSB first: 1100 Hz = 1, 1300 Hz = 0
        for bit in bits:
            freq = 1100.0 if bit else 1300.0
            segments.append(self._generate_tone(freq, samples_for(bit_duration_s)))

        # Stop bit (1200 Hz, 30ms)
        segments.append(self._generate_tone(1200.0, samples_for(bit_duration_s)))

        return np.concatenate(segments)

    def _generate_tone(self, freq: float, num_samples: int) -> np.ndarray:
        """Generate a pure sine wave at given frequency."""
        t = np.arange(num_samples) / self._sample_rate
        return np.sin(2 * np.pi * freq * t).astype(np.float32)


@dataclass
class CorrelationVISConfig:
    """Configuration for correlation-based VIS detection."""

    sample_rate: int = 48000
    threshold: float = 0.85  # Minimum correlation coefficient for detection
    min_confidence: float = 0.70  # Minimum confidence to report mode

    # Pre-filtering to improve SNR
    enable_pre_filter: bool = True
    filter_low_freq: float = 1000.0
    filter_high_freq: float = 2500.0


class CorrelationVISDetector:
    """VIS code detector using cross-correlation.

    Advantages over simple Goertzel tone detection:
    - Robust to noise (-15 dB SNR vs -5 dB for tone detection)
    - Detects buried VIS codes in static
    - Matches exact VIS waveform timing

    Algorithm:
    1. Maintain a rolling buffer of audio samples
    2. Correlate buffer with each VIS template waveform
    3. Find peak correlation coefficient
    4. Validate with additional confidence checks
    5. Return detected mode with confidence score
    """

    # A detection must beat the runner-up mode by this margin.
    #
    # VIS codes differ in only one or two of ten bit periods, so near-neighbour
    # templates score very close on a clean header: a Scottie S1 header scores
    # 1.0000 for Scottie S1 and 0.9946 for both Scottie S2 and Martin M1. The
    # correct mode does win, but only just, and reporting a winner without
    # checking the gap picked Martin M1 for a Scottie S1 transmission.
    #
    # Requiring separation means an ambiguous header reports nothing rather
    # than something wrong, which is the right failure: a wrong mode decodes
    # the picture with the wrong geometry and the operator sees garbage, where
    # no detection just asks them to choose.
    MIN_MODE_MARGIN = 0.002

    # VIS templates for all supported modes
    SUPPORTED_MODES: ClassVar[list[SSTVMode]] = [
        SSTVMode.SCOTTIE_S1,
        SSTVMode.SCOTTIE_S2,
        SSTVMode.SCOTTIE_DX,
        SSTVMode.MARTIN_M1,
        SSTVMode.MARTIN_M2,
        SSTVMode.ROBOT_36,
        SSTVMode.ROBOT_72,
        SSTVMode.PD_90,
        SSTVMode.PD_120,
        SSTVMode.PD_180,
        SSTVMode.PD_240,
    ]

    def __init__(self, config: CorrelationVISConfig | None = None) -> None:
        """Initialize correlation VIS detector.

        Args:
            config: Detection configuration

        """
        self._config = config or CorrelationVISConfig()

        # Generate templates for all supported modes
        self._templates: dict[SSTVMode, VISWaveformTemplate] = {}
        self._generate_templates()

        # Rolling buffer for incoming audio. Sized larger than the longest
        # template so a header that does not happen to end on a chunk boundary
        # is still fully inside the buffer and can be found by searching
        # offsets -- see the alignment search in process_samples.
        self._max_template_length = max(len(t.waveform) for t in self._templates.values())
        self._buffer = np.zeros(int(self._max_template_length * 1.5), dtype=np.float32)
        self._samples_buffered = 0

        # Largest chunk that may be buffered before correlating. Detection runs
        # once per step, and neighbouring modes score within MIN_MODE_MARGIN of
        # each other on a real header, so a mode is only reported on the step
        # whose alignment happens to separate it from its runner-up. A caller
        # feeding big chunks gets fewer attempts at that alignment and can miss
        # a header it correlated at 0.92: measured at 11025 Hz, a quarter of a
        # template recovers every off-air transmission that half a template
        # still dropped, and finer steps buy nothing.
        self._max_step_samples = max(1, self._max_template_length // 4)

        # Track best correlation
        self._best_correlation: float = 0.0
        self._best_mode: SSTVMode | None = None


    def _generate_templates(self) -> None:
        """Generate VIS waveform templates for all supported modes."""
        logger.info("Generating VIS correlation templates for %d modes", len(self.SUPPORTED_MODES))

        for mode in self.SUPPORTED_MODES:
            template = VISWaveformTemplate(mode, self._config.sample_rate)
            self._templates[mode] = template

        logger.debug("VIS templates generated: %s", list(self._templates.keys()))

    def reset(self) -> None:
        """Reset detector state for new detection cycle."""
        self._buffer[:] = 0
        self._samples_buffered = 0
        self._best_correlation = 0.0
        self._best_mode = None

    def process_samples(self, samples: np.ndarray) -> VISDetectionResult | None:
        """Process audio samples and detect VIS code.

        Callers choose their own block size, so an arbitrarily large chunk
        arrives here as one call. Detection only ever runs once per call, and
        the buffer holds the most RECENT audio, so a chunk larger than the
        detection step would carry the header in and scroll it back out
        before anything looked at it -- measured at 11025 Hz, chunk 9600 and
        24000 missed every transmission in the off-air corpus. Split oversized
        input and step through it instead, so the answer is a property of the
        audio rather than of the caller's buffering.

        Args:
            samples: Incoming audio samples

        Returns:
            VISDetectionResult if mode detected with confidence, None otherwise

        """
        step = self._max_step_samples
        if len(samples) > step:
            for offset in range(0, len(samples), step):
                result = self._process_step(samples[offset : offset + step])
                if result is not None:
                    return result
            return None

        return self._process_step(samples)

    def _process_step(self, samples: np.ndarray) -> VISDetectionResult | None:
        """Buffer one bounded chunk and correlate against every template."""
        # Apply pre-filtering if enabled
        if self._config.enable_pre_filter:
            samples = self._apply_bandpass_filter(samples)

        # Update rolling buffer
        buffer_size = len(self._buffer)
        samples_size = len(samples)

        if samples_size >= buffer_size:
            self._buffer[:] = samples[-buffer_size:]
            self._samples_buffered = buffer_size
        else:
            self._buffer = np.roll(self._buffer, -samples_size)
            self._buffer[-samples_size:] = samples
            self._samples_buffered = min(
                buffer_size,
                self._samples_buffered + samples_size,
            )

        # Do NOT wait for the buffer to fill. A VIS header arrives at the very
        # start of a transmission, and the buffer holds the most RECENT audio:
        # measured at 11025 Hz, the buffer spans 1.36s while the header ends at
        # 0.91s, so by the time it filled the header had already scrolled out
        # and the peak correlation dropped from 0.999 to 0.43. Match as soon as
        # there is one template's worth of audio.
        if self._samples_buffered < self._max_template_length:
            return None

        # Correlate with all templates
        best_mode = None
        best_correlation = 0.0
        runner_up = 0.0

        # Match in the frequency-envelope domain across a range of
        # alignments. Raw-sample correlation needs about one sample of
        # alignment (see VISWaveformTemplate.envelope) and callers feed
        # arbitrary chunk sizes, so the header essentially never lands where a
        # single fixed offset would find it -- measured, a real header scored
        # 0.32 against a 0.85 threshold and was never detected.
        # Only the region actually written to, oldest-first. While the buffer
        # is still filling its tail holds the audio; once full it is the whole
        # buffer.
        filled = self._buffer[-self._samples_buffered :]
        buffer_envelope = frequency_envelope(filled, self._config.sample_rate)

        for mode, template in self._templates.items():
            template_envelope = template.envelope
            span = len(template_envelope)
            if span == 0 or len(buffer_envelope) < span:
                continue

            latest = len(buffer_envelope) - span
            # One envelope point is ~1ms regardless of input rate. Step one
            # point at a time: the envelope is only ~910 points long, so an
            # exhaustive search is a few hundred correlations per template and
            # runs in milliseconds. A coarser stride measured 0.43 at 11025 Hz
            # against 0.96 at 48000 -- the sweep has to be fine enough that the
            # true alignment is actually visited, not merely bracketed.
            stride = 1

            for start_index in range(0, latest + 1, stride):
                window = buffer_envelope[start_index : start_index + span]
                correlation = self._correlate_envelopes(window, template_envelope)
                if correlation > best_correlation:
                    if best_mode is not mode:
                        runner_up = best_correlation
                    best_correlation = correlation
                    best_mode = mode
                elif mode is not best_mode and correlation > runner_up:
                    runner_up = correlation

        # Every template is scored before deciding. VIS codes differ in only a
        # few of ten bit periods, so several modes clear the threshold on the
        # same header and the first one over it is often not the right one:
        # a Scottie S1 transmission matched Martin M1 at 0.918 and was reported
        # as Martin until this loop was allowed to finish.

        # Update best tracking
        if best_correlation > self._best_correlation:
            self._best_correlation = best_correlation
            self._best_mode = best_mode

        margin = best_correlation - runner_up
        if (
            best_correlation >= self._config.threshold
            and best_mode is not None
            and margin >= self.MIN_MODE_MARGIN
        ):
            logger.info(
                "VIS detected via correlation: %s (correlation: %.3f)",
                best_mode.name,
                best_correlation,
            )

            # Extract bit pattern from mode value
            vis_code = best_mode.value
            bit_pattern = [(vis_code >> i) & 1 for i in range(8)]

            return VISDetectionResult(
                mode=best_mode,
                vis_code=vis_code,
                confidence=best_correlation,
                bit_pattern=bit_pattern,
                parity_valid=self._check_parity(vis_code),
            )

        return None

    @staticmethod
    def _correlate_envelopes(window: np.ndarray, template: np.ndarray) -> float:
        """Pearson correlation of two frequency envelopes.

        Returns 0.0 when either side is flat: a constant window has no
        variance, and numpy would return NaN rather than a usable score.
        """
        if len(window) != len(template) or len(window) == 0:
            return 0.0
        w_std = float(np.std(window))
        t_std = float(np.std(template))
        if w_std < 1e-9 or t_std < 1e-9:
            return 0.0
        return float(np.mean((window - np.mean(window)) * (template - np.mean(template)))
                     / (w_std * t_std))

    def _normalized_correlation(self, signal: np.ndarray, template: np.ndarray) -> float:
        """Calculate normalized cross-correlation.

        Normalized correlation coefficient (Pearson correlation coefficient)
        is robust to amplitude differences between signal and template.

        Returns value in [-1, 1] where:
        - 1 = perfect match (same shape, proportional amplitude)
        - 0 = no correlation
        - -1 = perfect anti-correlation (inverse shape)
        """
        # Ensure equal length
        min_len = min(len(signal), len(template))
        sig = signal[:min_len]
        tmpl = template[:min_len]

        # Calculate means
        sig_mean = np.mean(sig)
        tmpl_mean = np.mean(tmpl)

        # Calculate standard deviations
        sig_std = np.std(sig)
        tmpl_std = np.std(tmpl)

        # Avoid division by zero
        if sig_std == 0 or tmpl_std == 0:
            return 0.0

        # Calculate Pearson correlation coefficient
        numerator = np.sum((sig - sig_mean) * (tmpl - tmpl_mean))
        denominator = sig_std * tmpl_std * min_len

        return numerator / denominator if denominator != 0 else 0.0

    def _apply_bandpass_filter(self, samples: np.ndarray) -> np.ndarray:
        """Apply bandpass filter to improve SNR before correlation.

        Filter passes 1000-2500 Hz to focus on VIS frequency range
        and reject low-frequency noise, high-frequency hiss.

        Args:
            samples: Input audio samples

        Returns:
            Filtered samples

        """
        nyquist = self._config.sample_rate / 2.0
        low = self._config.filter_low_freq / nyquist
        high = self._config.filter_high_freq / nyquist

        # 4th order Butterworth bandpass filter
        b, a = signal.butter(4, [low, high], btype="band")

        # Apply filter using filtfilt for zero-phase filtering
        filtered = signal.filtfilt(b, a, samples)

        return np.asarray(filtered)

    @staticmethod
    def _check_parity(vis_code: int) -> bool:
        """Whether the VIS code's own parity bit is consistent.

        Always True for this detector, and the reason is worth stating.

        VIS transmits 7 data bits plus an even-parity bit. `SSTVMode` stores
        the 7-bit code *without* that bit (Scottie S1 is 60, Martin M1 is 44),
        so there is no parity bit here to check. The previous implementation
        counted set bits across all 8 and required an odd total, which asked
        whether the mode's *number* happened to have odd popcount -- unrelated
        to signal integrity, and false for Scottie S1, Martin M1, and Robot 36
        among others.

        This detector matches whole waveform templates rather than decoding
        individual bits, so a match already implies the received bit pattern
        agreed with a known code end to end. Correlation confidence is the
        meaningful quality figure; parity would only add information to a
        bit-slicing decoder, which this is not.
        """
        return True

    def get_correlation_score(self) -> float:
        """Get current best correlation score."""
        return self._best_correlation

    def get_detected_mode(self) -> SSTVMode | None:
        """Get current detected mode (below threshold)."""
        return self._best_mode
