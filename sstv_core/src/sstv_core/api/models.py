"""Pydantic models for API request/response validation.

These models define the API contract between the frontend and backend,
with comprehensive validation to ensure data integrity and security.
"""

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

# ============================================================================
# Enums
# ============================================================================

class SSTVMode(str, Enum):
    """Supported SSTV modes."""

    MARTIN_M1 = "MartinM1"
    MARTIN_M2 = "MartinM2"
    SCOTTIE_S1 = "ScottieS1"
    SCOTTIE_S2 = "ScottieS2"
    SCOTTIE_DX = "ScottieDX"
    ROBOT_36 = "Robot36"
    ROBOT_72 = "Robot72"
    PD_90 = "PD90"
    PD_120 = "PD120"
    PD_180 = "PD180"
    PD_240 = "PD240"
    WRAASE_SC2_180 = "WraaseSC2_180"


class DecodeState(str, Enum):
    """Decode session states."""

    LISTENING = "listening"
    VIS_DETECTED = "vis_detected"
    DECODING = "decoding"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class TransmitState(str, Enum):
    """Transmit session states."""

    PENDING = "pending"
    PTT_ENGAGED = "ptt_engaged"
    TRANSMITTING = "transmitting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PTTMethod(str, Enum):
    """PTT control methods."""

    SERIAL_RTS = "serial_rts"
    SERIAL_DTR = "serial_dtr"
    VOX = "vox"
    NONE = "none"


class ModeDetectionRequest(BaseModel):
    """Request for mode detection from sync timing."""

    session_id: UUID | None = Field(
        default=None,
        description="Optional session ID to analyze audio from active decode session",
    )
    audio_file: str | None = Field(
        default=None,
        description="Path to audio file for analysis",
    )
    duration_sec: float = Field(
        default=10.0,
        gt=0.0,
        le=60.0,
        description="Duration to analyze in seconds (default 10.0)",
    )

    @model_validator(mode="after")
    def validate_audio_source(self) -> "ModeDetectionRequest":
        """Require at least one usable source for mode detection."""
        if self.session_id is None and self.audio_file is None:
            raise ValueError("Either session_id or audio_file must be provided")
        return self


class ModeDetectionResponse(BaseModel):
    """Response from mode detection analysis."""

    mode: str | None = Field(
        default=None,
        description="Detected SSTV mode (null if confidence < 0.70)",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score 0.0-1.0 (null if no detection)",
    )
    measured_intervals: list[float] = Field(
        default_factory=list,
        description="Measured inter-pulse intervals (first 10 for debugging)",
    )
    expected_interval: float | None = Field(
        default=None,
        description="Expected interval for detected mode",
    )
    fallback_modes: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Top 3 alternative mode suggestions",
    )
    suggestion_message: str | None = Field(
        default=None,
        description="User-friendly suggestion message in SSTeVe voice",
    )


class OperatingConditionMode(str, Enum):
    """Operating conditions modes (accessibility, not aesthetic)."""

    STANDARD = "standard"
    NIGHT_VISION = "night_vision"
    SUNLIGHT = "sunlight"


# ============================================================================
# Configuration Models
# ============================================================================

class ApplySettingsRequest(BaseModel):
    """Request to apply recommended device settings."""

    profile_name: str | None = Field(
        default=None,
        description="Name of device profile to apply (e.g., 'Digirig Mobile')",
    )

    ptt_method: str | None = Field(
        default=None,
        description="PTT method: 'serial_rts', 'serial_dtr', 'vox', 'none'",
    )

    ptt_serial_signal: str | None = Field(
        default=None,
        description="Serial PTT signal: 'RTS' or 'DTR'",
    )

    ptt_pre_delay_ms: int | None = Field(
        default=None,
        ge=0,
        le=5000,
        description="PTT pre-delay in milliseconds",
    )

    ptt_post_delay_ms: int | None = Field(
        default=None,
        ge=0,
        le=5000,
        description="PTT post-delay in milliseconds",
    )

    vox_preamble_ms: int | None = Field(
        default=None,
        ge=0,
        le=5000,
        description="VOX preamble duration in milliseconds",
    )

    audio_input_device_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=256,
        description="Audio input device ID",
    )

    audio_output_device_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=256,
        description="Audio output device ID",
    )


class DeviceDetectionResponse(BaseModel):
    """Response from hardware device detection."""

    detected_profile: str | None = Field(
        default=None,
        description="Name of detected device profile (if any)",
    )

    detection_message: str | None = Field(
        default=None,
        description="User-friendly detection message in SSTeVe voice",
    )

    recommended_settings: dict[str, Any] = Field(
        default_factory=dict,
        description="Recommended configuration settings for detected device",
    )

    settings_preview: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Preview of what will change if settings are applied",
    )

    model_config = {"json_schema_extra": {"examples": []}}


class ApplySettingsResponse(BaseModel):
    """Response after applying settings."""

    updated_configuration: dict[str, Any] = Field(
        description="Updated configuration after applying settings",
    )

    applied_fields: list[str] = Field(
        description="List of configuration fields that were updated",
    )

    model_config = {"json_schema_extra": {"examples": []}}


class AudioDevice(BaseModel):
    """Audio device information."""

    device_id: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Device identifier (OS-specific)"
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=512,
        description="Human-readable device name"
    )
    channels: int = Field(
        ...,
        ge=1,
        le=32,
        description="Number of audio channels"
    )
    sample_rate: int = Field(
        ...,
        ge=8000,
        le=192000,
        description="Preferred sample rate in Hz (48000 when the device supports it)"
    )
    # device_manager already probes every supported rate and the route threw
    # the list away, keeping one. A client choosing a rate needs the choices.
    sample_rates: list[int] = Field(
        default_factory=list,
        description="All sample rates this device supports, ascending"
    )
    is_input: bool = Field(
        default=False,
        description="Device can capture audio"
    )
    is_output: bool = Field(
        default=False,
        description="Device can play audio"
    )
    is_default: bool = Field(
        default=False,
        description="Whether this is the system default device"
    )

    @field_validator("device_id")
    @classmethod
    def validate_device_id(cls, v: str) -> str:
        """Prevent path traversal attacks in device IDs."""
        if ".." in v or "/" in v or "\\" in v:
            raise ValueError("Device ID can't contain path traversal characters")
        return v


class SerialPort(BaseModel):
    """Serial port information for PTT control."""

    port: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Serial port identifier (e.g., COM3, /dev/ttyUSB0)"
    )
    description: str = Field(
        default="",
        max_length=512,
        description="Human-readable port description"
    )
    manufacturer: str | None = Field(
        default=None,
        max_length=256,
        description="Device manufacturer"
    )

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: str) -> str:
        """Prevent path traversal in serial port names."""
        if ".." in v:
            raise ValueError("Serial port can't contain path traversal")
        return v


class Configuration(BaseModel):
    """System configuration."""

    audio_input_device: str | None = Field(
        default=None,
        description="Selected audio input device ID"
    )
    audio_output_device: str | None = Field(
        default=None,
        description="Selected audio output device ID"
    )
    ptt_method: PTTMethod = Field(
        default=PTTMethod.NONE,
        description="PTT control method"
    )
    ptt_serial_port: str | None = Field(
        default=None,
        description="Serial port for PTT (if using serial PTT)"
    )
    ptt_pre_delay_ms: int = Field(
        default=500,
        ge=0,
        le=5000,
        description="PTT pre-delay in milliseconds (radio stabilization)"
    )
    ptt_post_delay_ms: int = Field(
        default=200,
        ge=0,
        le=5000,
        description="PTT post-delay in milliseconds (audio completion)"
    )
    default_transmit_mode: SSTVMode = Field(
        default=SSTVMode.MARTIN_M1,
        description="Default SSTV mode for transmissions"
    )
    image_library_path: str = Field(
        default="~/sstv_images",
        description="Path to image library directory"
    )
    operating_mode: OperatingConditionMode = Field(
        default=OperatingConditionMode.STANDARD,
        description="Operating conditions mode"
    )
    auto_detect_mode: bool = Field(
        default=True,
        description="Enable automatic SSTV mode detection from VIS"
    )
    auto_afc: bool = Field(
        default=True,
        description="Enable automatic frequency correction"
    )
    afc_range_hz: int = Field(
        default=100,
        ge=0,
        le=500,
        description="AFC search range in Hz"
    )
    auto_squelch: bool = Field(
        default=True,
        description="Enable automatic squelch threshold"
    )
    squelch_threshold_db: float = Field(
        default=-40.0,
        ge=-100.0,
        le=0.0,
        description="Squelch threshold in dB (manual mode)"
    )

    @field_validator("image_library_path")
    @classmethod
    def validate_library_path(cls, v: str) -> str:
        """Accept any path the operator names, `~` included.

        This deliberately does not constrain the location. SSTeVe is a
        single-user local app -- the same person could set the value
        directly in the database -- and an external drive or NAS mount is a
        legitimate place to keep an image library. `TransmitRequest.
        image_path` already accepts arbitrary absolute paths, so this
        matches.

        Until 2026-08-09 this claimed to enforce home-containment and did
        not: it substituted a hardcoded `/home/admin` for `~` (a path on
        neither dev nor production) and rejected only the literal substring
        `..`. `routes/config.py` does the real `expanduser().resolve()`
        before the value is stored or used.
        """
        return v

    @model_validator(mode="after")
    def validate_ptt_config(self) -> "Configuration":
        """Validate PTT configuration consistency."""
        if self.ptt_method in (PTTMethod.SERIAL_RTS, PTTMethod.SERIAL_DTR):
            if not self.ptt_serial_port:
                raise ValueError(
                    "Serial PTT method requires ptt_serial_port to be set"
                )
        return self


# ============================================================================
# Decode Models
# ============================================================================

class DecodeStartRequest(BaseModel):
    """Request to start a decode session."""

    mode: SSTVMode | None = Field(
        default=None,
        description="SSTV mode (null for auto-detect)"
    )
    auto_detect: bool = Field(
        default=True,
        description="Enable VIS-based mode auto-detection"
    )
    timeout_seconds: int | None = Field(
        default=300,
        ge=10,
        le=3600,
        description="Max listening duration in seconds (null for unlimited)"
    )
    save_image: bool = Field(
        default=True,
        description="Save decoded image to library"
    )
    callsign: str | None = Field(
        default=None,
        min_length=3,
        max_length=20,
        description="Operator callsign (for QSO logging)"
    )
    device_id: str | None = Field(
        default=None,
        max_length=256,
        description="Audio input device ID (null for system default)"
    )

    @field_validator("callsign")
    @classmethod
    def validate_callsign(cls, v: str | None) -> str | None:
        """Validate amateur radio callsign format."""
        if v is None:
            return v
        # Basic callsign validation: letters, numbers, hyphens
        if not re.match(r"^[A-Z0-9][A-Z0-9/-]{2,19}$", v.upper()):
            raise ValueError(
                "Callsign must be 3-20 characters, alphanumeric with hyphens"
            )
        return v.upper()


class DecodeStartResponse(BaseModel):
    """Response from starting a decode session."""

    session_id: UUID = Field(
        ...,
        description="Unique session identifier for tracking"
    )
    state: DecodeState = Field(
        ...,
        description="Current session state"
    )
    websocket_url: str = Field(
        ...,
        description="WebSocket URL for real-time updates"
    )
    started_at: datetime = Field(
        ...,
        description="Session start timestamp (UTC)"
    )


class DecodeStatusResponse(BaseModel):
    """Decode session status."""

    session_id: UUID
    state: DecodeState
    mode: SSTVMode | None = Field(
        default=None,
        description="Detected/selected SSTV mode"
    )
    mode_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Mode detection confidence (0-1)"
    )
    progress_percent: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Decode progress (0-100)"
    )
    scanlines_received: int = Field(
        default=0,
        ge=0,
        description="Number of scanlines decoded"
    )
    snr_db: float | None = Field(
        default=None,
        description="Signal-to-noise ratio in dB"
    )
    frequency_offset_hz: float | None = Field(
        default=None,
        description="Measured receiver offset in Hz (null until AFC locks)"
    )

    # Contract drift: backend-spec.md:407-416 specified these three and the
    # model never carried them.
    total_scanlines: int | None = Field(
        default=None,
        ge=1,
        description="Scanline count for the detected mode (null before VIS)"
    )
    vis_detected: bool = Field(
        default=False,
        description="Whether a VIS header has been identified this session"
    )
    signal_quality: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Decoder's rolling 0-1 quality estimate; not a calibrated SNR"
    )

    # AFC lock (PRODUCT.md #5: "AFC lock must be verifiable"). Three states
    # the operator must be able to tell apart, which is why this is not one
    # boolean:
    #   searching        -> afc_locked False
    #   locked+corrected -> afc_locked True, correction_applied_hz != 0
    #   locked, not applied -> afc_locked True, correction_applied_hz 0.0
    # The last is auto_afc off (Doppler/satellite work): the offset is known
    # and deliberately untouched. Collapsing that into "locked" would erase
    # the manual-override distinction CLAUDE.md requires.
    afc_locked: bool = Field(
        default=False,
        description="AFC has agreed on an offset (three sync pulses concurring)"
    )
    afc_correction_applied_hz: float | None = Field(
        default=None,
        description="Offset actually applied to the video mapping; 0.0 when locked "
                    "but auto_afc is off, null before lock"
    )

    image_id: UUID | None = Field(
        default=None,
        description="Image ID if decode completed and saved"
    )
    error: str | None = Field(
        default=None,
        description="Error message if state is 'failed'"
    )
    started_at: datetime
    completed_at: datetime | None = None


# ============================================================================
# Transmit Models
# ============================================================================

class TransmitRequest(BaseModel):
    """Request to transmit an SSTV image."""

    image_path: str = Field(
        ...,
        min_length=1,
        max_length=4096,
        description="Absolute path to image file"
    )
    mode: SSTVMode = Field(
        ...,
        description="SSTV mode for transmission"
    )
    callsign: str | None = Field(
        default=None,
        min_length=3,
        max_length=20,
        description="Operator callsign (overlaid on image)"
    )
    # (include_vis was removed 2026-08-07: it was accepted and ignored --
    # every transmission includes VIS, as it must for receivers to
    # auto-detect the mode.)
    vox_enabled: bool = Field(
        default=False,
        description="Use VOX (silence preamble) instead of PTT"
    )
    device_id: str | None = Field(
        default=None,
        max_length=256,
        description="Audio output device ID (null for system default)"
    )
    serial_port: str | None = Field(
        default=None,
        max_length=256,
        description="Serial port for PTT control (e.g., /dev/ttyUSB0, COM3)"
    )

    @field_validator("image_path")
    @classmethod
    def validate_image_path(cls, v: str) -> str:
        """Prevent path traversal in image paths."""
        if ".." in v:
            raise ValueError("Image path can't contain path traversal")
        # Must be absolute path
        if not v.startswith("/"):
            raise ValueError("Image path must be absolute")
        return v

    @field_validator("callsign")
    @classmethod
    def validate_callsign(cls, v: str | None) -> str | None:
        """Validate amateur radio callsign format."""
        if v is None:
            return v
        if not re.match(r"^[A-Z0-9][A-Z0-9/-]{2,19}$", v.upper()):
            raise ValueError(
                "Callsign must be 3-20 characters, alphanumeric with hyphens"
            )
        return v.upper()


class TransmitResponse(BaseModel):
    """Response from starting a transmission."""

    tx_id: UUID = Field(
        ...,
        description="Unique transmission identifier"
    )
    state: TransmitState = Field(
        ...,
        description="Current transmission state"
    )
    websocket_url: str = Field(
        ...,
        description="WebSocket URL for real-time updates"
    )
    estimated_duration_seconds: float = Field(
        ...,
        ge=0.0,
        description="Estimated transmission duration"
    )
    started_at: datetime = Field(
        ...,
        description="Transmission start timestamp (UTC)"
    )


class TransmitStatusResponse(BaseModel):
    """Transmission status."""

    tx_id: UUID
    state: TransmitState
    # None in the degenerate lost-metadata case -- previously fabricated
    # as MartinM1.
    mode: SSTVMode | None = None
    progress_percent: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Transmission progress (0-100)"
    )
    scanlines_transmitted: int = Field(
        default=0,
        ge=0,
        description="Number of scanlines transmitted"
    )
    elapsed_seconds: float = Field(
        default=0.0,
        ge=0.0,
        description="Elapsed transmission time"
    )
    estimated_duration_seconds: float = Field(
        ...,
        ge=0.0,
        description="Total estimated duration"
    )
    image_id: UUID | None = Field(
        default=None,
        description="Image ID if saved to library"
    )
    error: str | None = Field(
        default=None,
        description="Error message if state is 'failed'"
    )
    started_at: datetime
    completed_at: datetime | None = None


# ============================================================================
# Image Models
# ============================================================================

class ImageMetadata(BaseModel):
    """Metadata for a stored SSTV image."""

    id: UUID = Field(
        ...,
        description="Unique image identifier"
    )
    filepath: str = Field(
        ...,
        description="Absolute path to image file"
    )
    # None when the stored mode string is not a known SSTVMode (imported
    # files) -- previously coerced to MartinM1, which was a fabrication.
    mode: SSTVMode | None = Field(
        default=None,
        description="SSTV mode used (null when unknown)"
    )
    direction: str = Field(
        ...,
        pattern="^(rx|tx)$",
        description="Receive or transmit"
    )
    callsign: str | None = Field(
        default=None,
        description="Operator callsign"
    )
    timestamp: datetime = Field(
        ...,
        description="Capture/transmit timestamp (UTC)"
    )
    snr_db: float | None = Field(
        default=None,
        description="Signal quality (RX only)"
    )
    frequency_hz: float | None = Field(
        default=None,
        description="Dial frequency the image was received on (RX only)"
    )
    thumbnail_path: str | None = Field(
        default=None,
        description="Path to thumbnail image"
    )
    # None when the file on disk cannot be read -- previously fabricated
    # as 320x256.
    width: int | None = Field(
        default=None,
        ge=1,
        description="Image width in pixels (null if file unreadable)"
    )
    height: int | None = Field(
        default=None,
        ge=1,
        description="Image height in pixels (null if file unreadable)"
    )
    filename: str | None = Field(
        default=None,
        description="Base filename on disk"
    )
    rx_quality_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Decoder's 0-1 quality estimate (RX only); not a calibrated SNR"
    )

    # Auto-RSV. Computed and persisted since PR #38; never exposed until
    # 2026-08-09. All null for TX images and for decodes predating RSV.
    rsv_readability: int | None = Field(
        default=None, ge=1, le=5, description="RSV readability, 1-5"
    )
    rsv_signal: int | None = Field(
        default=None, ge=1, le=9, description="RSV signal strength, 1-9"
    )
    rsv_video: int | None = Field(
        default=None, ge=1, le=9, description="RSV video quality, 1-9"
    )
    rsv_report: str | None = Field(
        default=None, description="Formatted RSV report, e.g. '595'"
    )
    peak_amplitude: float | None = Field(
        default=None, description="Measured peak input amplitude (0-1)"
    )
    noise_floor: float | None = Field(
        default=None, description="Measured pre-signal noise floor (0-1)"
    )

    # FSKID. There is deliberately no separate fskid_callsign field: a
    # checksum-valid decoded call is adopted INTO `callsign` when the
    # operator supplied none, so a second field would imply a distinction
    # the schema does not make. fskid_detected + callsign is the full story.
    fskid_detected: bool | None = Field(
        default=None, description="Whether an FSKID burst was found"
    )
    fskid_confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="FSKID decode confidence"
    )
    fskid_checksum_valid: bool | None = Field(
        default=None,
        description="FSKID checksum passed; false means the callsign is suspect"
    )


class ImageListResponse(BaseModel):
    """Paginated image list."""

    images: list[ImageMetadata] = Field(
        ...,
        description="List of image metadata"
    )
    total: int = Field(
        ...,
        ge=0,
        description="Total number of images matching filters"
    )
    limit: int = Field(
        ...,
        ge=1,
        le=100,
        description="Pagination limit"
    )
    offset: int = Field(
        ...,
        ge=0,
        description="Pagination offset"
    )


# ============================================================================
# WebSocket Event Models
# ============================================================================

class WSEvent(BaseModel):
    """Base WebSocket event."""

    event_type: str = Field(
        ...,
        description="Event type identifier"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Event timestamp (UTC)"
    )
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Event payload"
    )


class VISDetectedEvent(BaseModel):
    """VIS code detected event."""

    event_type: str = "vis_detected"
    mode: SSTVMode
    confidence: float = Field(ge=0.0, le=1.0)
    # The correlation detector identifies the mode by envelope matching, so
    # a raw VIS byte is not always available; None means "mode known, code
    # not separately decoded".
    vis_code: int | None = Field(default=None, ge=0, le=255)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ScanlineUpdateEvent(BaseModel):
    """Scanline decode/transmit progress event."""

    event_type: str = "scanline_update"
    scanline_number: int = Field(ge=0)
    total_scanlines: int = Field(ge=1)
    progress_percent: float = Field(ge=0.0, le=100.0)
    signal_quality: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Decoder's per-line quality estimate (0-1); not a calibrated SNR",
    )
    snr_db: float | None = None
    frequency_offset_hz: float | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AudioLevelsEvent(BaseModel):
    """Live input level meter event (mono source: left == right)."""

    event_type: str = "audio_levels"
    left_db: float
    right_db: float
    peak_db: float
    is_clipping: bool = False
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TransmitProgressEvent(BaseModel):
    """Transmission progress event."""

    event_type: str = "tx_progress"
    progress_percent: float = Field(ge=0.0, le=100.0)
    current_scanline: int = Field(ge=0)
    time_remaining_seconds: float = Field(ge=0.0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DecodeCompleteEvent(BaseModel):
    """Decode complete event."""

    event_type: str = "decode_complete"
    # None when the database is disabled and no gallery record was created.
    image_id: UUID | None = None
    filepath: str | None = None
    # None only in the degenerate case where session metadata was lost;
    # normal completions always carry the decoded mode.
    mode: SSTVMode | None = None
    # None: the engine does not currently measure calibrated SNR. A number
    # here must be a measurement, not a guess.
    snr_db: float | None = None
    duration_seconds: float = Field(ge=0.0)

    # Auto-RSV and FSKID at the moment a client would show them, so the
    # gallery does not have to re-fetch the image record to render the
    # report it just earned. Null when the decode produced none.
    rsv_report: str | None = Field(
        default=None, description="Formatted RSV report, e.g. '595'"
    )
    fskid_detected: bool | None = Field(
        default=None, description="Whether an FSKID burst was found"
    )
    fskid_checksum_valid: bool | None = Field(
        default=None,
        description="FSKID checksum passed; false means any decoded call is suspect"
    )

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TransmitCompleteEvent(BaseModel):
    """Transmit complete event."""

    event_type: str = "transmit_complete"
    tx_id: UUID
    # None only in the degenerate case where session metadata was lost;
    # normal completions always carry the transmitted mode.
    mode: SSTVMode | None = None
    duration_seconds: float = Field(ge=0.0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ErrorEvent(BaseModel):
    """Error event."""

    event_type: str = "error"
    error_code: str
    message: str
    recoverable: bool = Field(
        default=False,
        description="Whether operation can be retried"
    )
    suggested_action: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================================
# Import Models (Phase 4: Filesystem Integration)
# ============================================================================

class MMSStvImportRequest(BaseModel):
    """Request to import MMSSTV library."""

    directory_path: str = Field(
        ...,
        min_length=1,
        max_length=1024,
        description="Path to MMSSTV image library directory"
    )
    recursive: bool = Field(
        default=True,
        description="Recursively scan subdirectories"
    )

    @field_validator("directory_path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        """Validate directory path is absolute and safe."""
        import os
        from pathlib import Path

        # Must be absolute path
        if not os.path.isabs(v):
            raise ValueError("Path must be absolute")

        # Check for path traversal
        path = Path(v)
        for part in path.parts:
            if part == "..":
                raise ValueError("Path cannot contain '..'")

        return v


class MMSStvImportResponse(BaseModel):
    """Response from MMSSTV import operation."""

    imported: int = Field(
        ...,
        ge=0,
        description="Number of images successfully imported"
    )
    skipped: int = Field(
        ...,
        ge=0,
        description="Number of images skipped (already exist)"
    )
    errors: list[str] = Field(
        default_factory=list,
        description="List of error messages"
    )
    total: int = Field(
        ...,
        ge=0,
        description="Total files scanned"
    )


class DirectoryValidationRequest(BaseModel):
    """Request to validate directory for import."""

    directory_path: str = Field(
        ...,
        min_length=1,
        max_length=1024,
        description="Path to directory to validate"
    )

    @field_validator("directory_path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        """Validate directory path is absolute and safe."""
        import os
        from pathlib import Path

        # Must be absolute path
        if not os.path.isabs(v):
            raise ValueError("Path must be absolute")

        # Check for path traversal
        path = Path(v)
        for part in path.parts:
            if part == "..":
                raise ValueError("Path cannot contain '..'")

        return v


class DirectoryValidationResponse(BaseModel):
    """Response from directory validation."""

    valid: bool = Field(
        ...,
        description="True if directory can be imported"
    )
    exists: bool = Field(
        ...,
        description="True if directory exists"
    )
    is_directory: bool = Field(
        ...,
        description="True if path is a directory"
    )
    image_count: int = Field(
        ...,
        ge=0,
        description="Number of importable images found"
    )
    error: str | None = Field(
        default=None,
        description="Error message if validation failed"
    )


class ImageMetadataSample(BaseModel):
    """Sample image metadata from preview."""

    filename: str = Field(..., description="Image filename")
    path: str = Field(..., description="Full file path")
    metadata: dict[str, Any] = Field(..., description="Parsed metadata")


class ImportPreviewResponse(BaseModel):
    """Preview of what would be imported from a directory."""

    total_files: int = Field(
        ...,
        ge=0,
        description="Total importable image files"
    )
    samples: list[ImageMetadataSample] = Field(
        default_factory=list,
        description="Sample files with parsed metadata"
    )
    validation: DirectoryValidationResponse = Field(
        ...,
        description="Directory validation result"
    )
