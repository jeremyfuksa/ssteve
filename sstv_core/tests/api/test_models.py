"""
Unit tests for API Pydantic models.

Tests validation rules, security constraints, and serialization.
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from pydantic import ValidationError

from sstv_core.api.models import (
    OperatingConditionMode,
    PTTMethod,
    SSTVMode,
    DecodeState,
    TransmitState,
    AudioDevice,
    SerialPort,
    Configuration,
    DecodeStartRequest,
    DecodeStartResponse,
    DecodeStatusResponse,
    TransmitRequest,
    TransmitStatusResponse,
    ImageMetadata,
    ImageListResponse,
    ModeDetectionRequest,
    VISDetectedEvent,
    ScanlineUpdateEvent,
    DecodeCompleteEvent,
    ErrorEvent,
)


class TestModeDetectionRequest:
    """Test cross-field validation for mode detection sources."""

    def test_audio_file_is_accepted(self) -> None:
        request = ModeDetectionRequest(audio_file="/tmp/signal.wav")
        assert request.audio_file == "/tmp/signal.wav"

    def test_missing_source_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Either session_id or audio_file"):
            ModeDetectionRequest()


class TestAudioDevice:
    """Test AudioDevice model validation."""

    def test_valid_audio_device(self):
        """Valid audio device should pass."""
        device = AudioDevice(
            device_id="hw:0,0",
            name="USB Audio Device",
            channels=2,
            sample_rate=48000,
            is_default=True,
        )
        assert device.device_id == "hw:0,0"
        assert device.channels == 2

    def test_device_id_path_traversal_rejected(self):
        """Device IDs with path traversal should be rejected."""
        with pytest.raises(ValidationError, match="path traversal"):
            AudioDevice(
                device_id="../etc/passwd",
                name="Evil Device",
                channels=2,
                sample_rate=48000,
            )

        with pytest.raises(ValidationError, match="path traversal"):
            AudioDevice(
                device_id="hw:0/../1",
                name="Evil Device",
                channels=2,
                sample_rate=48000,
            )

    def test_channels_validation(self):
        """Channel count must be 1-32."""
        with pytest.raises(ValidationError):
            AudioDevice(
                device_id="hw:0,0",
                name="Device",
                channels=0,  # Too low
                sample_rate=48000,
            )

        with pytest.raises(ValidationError):
            AudioDevice(
                device_id="hw:0,0",
                name="Device",
                channels=33,  # Too high
                sample_rate=48000,
            )

    def test_sample_rate_validation(self):
        """Sample rate must be 8000-192000 Hz."""
        with pytest.raises(ValidationError):
            AudioDevice(
                device_id="hw:0,0",
                name="Device",
                channels=2,
                sample_rate=7999,  # Too low
            )


class TestSerialPort:
    """Test SerialPort model validation."""

    def test_valid_serial_port(self):
        """Valid serial port should pass."""
        port = SerialPort(
            port="/dev/ttyUSB0",
            description="USB Serial Device",
            manufacturer="FTDI",
        )
        assert port.port == "/dev/ttyUSB0"

    def test_windows_com_port(self):
        """Windows COM ports should be valid."""
        port = SerialPort(port="COM3", description="Arduino")
        assert port.port == "COM3"

    def test_path_traversal_rejected(self):
        """Serial ports with path traversal should be rejected."""
        with pytest.raises(ValidationError, match="path traversal"):
            SerialPort(port="../dev/ttyUSB0")


class TestConfiguration:
    """Test Configuration model validation."""

    def test_default_configuration(self):
        """Default configuration should be valid."""
        config = Configuration()
        assert config.ptt_method == PTTMethod.NONE
        assert config.ptt_pre_delay_ms == 500
        assert config.auto_detect_mode is True

    def test_serial_ptt_requires_port(self):
        """Serial PTT methods require serial port to be set."""
        with pytest.raises(ValidationError, match="ptt_serial_port"):
            Configuration(
                ptt_method=PTTMethod.SERIAL_RTS,
                ptt_serial_port=None,  # Missing!
            )

    def test_serial_ptt_with_port_valid(self):
        """Serial PTT with port should be valid."""
        config = Configuration(
            ptt_method=PTTMethod.SERIAL_DTR,
            ptt_serial_port="/dev/ttyUSB0",
        )
        assert config.ptt_serial_port == "/dev/ttyUSB0"

    def test_vox_ptt_no_port_required(self):
        """VOX PTT doesn't require serial port."""
        config = Configuration(ptt_method=PTTMethod.VOX)
        assert config.ptt_serial_port is None

    def test_library_path_traversal_rejected(self):
        """Library paths with traversal should be rejected."""
        with pytest.raises(ValidationError, match="path traversal"):
            Configuration(image_library_path="/home/../../etc/passwd")

    def test_afc_range_validation(self):
        """AFC range must be 0-500 Hz."""
        with pytest.raises(ValidationError):
            Configuration(afc_range_hz=501)  # Too high

        config = Configuration(afc_range_hz=100)
        assert config.afc_range_hz == 100

    def test_squelch_threshold_validation(self):
        """Squelch threshold must be -100 to 0 dB."""
        with pytest.raises(ValidationError):
            Configuration(squelch_threshold_db=5.0)  # Too high

        config = Configuration(squelch_threshold_db=-45.0)
        assert config.squelch_threshold_db == -45.0


class TestDecodeStartRequest:
    """Test DecodeStartRequest validation."""

    def test_minimal_request(self):
        """Minimal decode request should be valid."""
        req = DecodeStartRequest()
        assert req.auto_detect is True
        assert req.save_image is True

    def test_with_mode_specified(self):
        """Request with explicit mode should be valid."""
        req = DecodeStartRequest(mode=SSTVMode.MARTIN_M1, auto_detect=False)
        assert req.mode == SSTVMode.MARTIN_M1
        assert req.auto_detect is False

    def test_callsign_validation(self):
        """Callsigns should be validated and uppercased."""
        req = DecodeStartRequest(callsign="w1aw")
        assert req.callsign == "W1AW"

        req = DecodeStartRequest(callsign="KC1ABC")
        assert req.callsign == "KC1ABC"

    def test_invalid_callsign_rejected(self):
        """Invalid callsigns should be rejected."""
        with pytest.raises(ValidationError):
            DecodeStartRequest(callsign="AB")  # Too short

        with pytest.raises(ValidationError):
            DecodeStartRequest(callsign="W1AW@")  # Invalid characters

    def test_timeout_validation(self):
        """Timeout must be 10-3600 seconds."""
        with pytest.raises(ValidationError):
            DecodeStartRequest(timeout_seconds=5)  # Too short

        with pytest.raises(ValidationError):
            DecodeStartRequest(timeout_seconds=3601)  # Too long

        req = DecodeStartRequest(timeout_seconds=300)
        assert req.timeout_seconds == 300


class TestDecodeStartResponse:
    """Test DecodeStartResponse serialization."""

    def test_valid_response(self):
        """Valid decode start response should serialize."""
        session_id = uuid4()
        resp = DecodeStartResponse(
            session_id=session_id,
            state=DecodeState.LISTENING,
            websocket_url=f"ws://localhost:8000/api/v1/ws/decode/{session_id}",
            started_at=datetime.now(timezone.utc),
        )
        assert resp.session_id == session_id
        assert resp.state == DecodeState.LISTENING


class TestDecodeStatusResponse:
    """Test DecodeStatusResponse validation."""

    def test_listening_state(self):
        """Listening state should have minimal fields."""
        resp = DecodeStatusResponse(
            session_id=uuid4(),
            state=DecodeState.LISTENING,
            started_at=datetime.now(timezone.utc),
        )
        assert resp.progress_percent == 0.0
        assert resp.mode is None

    def test_decoding_state_with_progress(self):
        """Decoding state should include progress."""
        resp = DecodeStatusResponse(
            session_id=uuid4(),
            state=DecodeState.DECODING,
            mode=SSTVMode.SCOTTIE_S1,
            mode_confidence=0.92,
            progress_percent=45.5,
            scanlines_received=120,
            snr_db=12.5,
            frequency_offset_hz=-15.3,
            started_at=datetime.now(timezone.utc),
        )
        assert resp.progress_percent == 45.5
        assert resp.scanlines_received == 120
        assert resp.snr_db == 12.5

    def test_failed_state_with_error(self):
        """Failed state should include error message."""
        resp = DecodeStatusResponse(
            session_id=uuid4(),
            state=DecodeState.FAILED,
            error="Audio device disconnected during decode",
            started_at=datetime.now(timezone.utc),
        )
        assert resp.state == DecodeState.FAILED
        assert resp.error is not None

    def test_progress_validation(self):
        """Progress must be 0-100."""
        with pytest.raises(ValidationError):
            DecodeStatusResponse(
                session_id=uuid4(),
                state=DecodeState.DECODING,
                progress_percent=101.0,  # Too high
                started_at=datetime.now(timezone.utc),
            )


class TestTransmitRequest:
    """Test TransmitRequest validation."""

    def test_minimal_request(self):
        """Minimal transmit request should be valid."""
        req = TransmitRequest(
            image_path="/home/admin/sstv_images/test.png",
            mode=SSTVMode.MARTIN_M1,
        )
        assert req.vox_enabled is False

    def test_path_traversal_rejected(self):
        """Image paths with traversal should be rejected."""
        with pytest.raises(ValidationError, match="path traversal"):
            TransmitRequest(
                image_path="/home/../etc/passwd",
                mode=SSTVMode.MARTIN_M1,
            )

    def test_relative_path_rejected(self):
        """Relative paths should be rejected."""
        with pytest.raises(ValidationError, match="absolute"):
            TransmitRequest(
                image_path="images/test.png",  # Relative!
                mode=SSTVMode.MARTIN_M1,
            )

    def test_callsign_overlay(self):
        """Callsign should be validated and uppercased."""
        req = TransmitRequest(
            image_path="/home/admin/test.png",
            mode=SSTVMode.ROBOT_36,
            callsign="n0call",
        )
        assert req.callsign == "N0CALL"

    def test_vox_mode(self):
        """VOX mode should be supported."""
        req = TransmitRequest(
            image_path="/home/admin/test.png",
            mode=SSTVMode.PD_120,
            vox_enabled=True,
        )
        assert req.vox_enabled is True


class TestTransmitStatusResponse:
    """Test TransmitStatusResponse validation."""

    def test_transmitting_state(self):
        """Transmitting state should include progress."""
        resp = TransmitStatusResponse(
            tx_id=uuid4(),
            state=TransmitState.TRANSMITTING,
            mode=SSTVMode.SCOTTIE_DX,
            progress_percent=67.2,
            scanlines_transmitted=180,
            elapsed_seconds=45.3,
            estimated_duration_seconds=67.5,
            started_at=datetime.now(timezone.utc),
        )
        assert resp.progress_percent == 67.2
        assert resp.elapsed_seconds == 45.3

    def test_completed_state(self):
        """Completed state should have 100% progress."""
        resp = TransmitStatusResponse(
            tx_id=uuid4(),
            state=TransmitState.COMPLETED,
            mode=SSTVMode.ROBOT_72,
            progress_percent=100.0,
            scanlines_transmitted=240,
            elapsed_seconds=72.1,
            estimated_duration_seconds=72.0,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        assert resp.state == TransmitState.COMPLETED
        assert resp.completed_at is not None


class TestImageMetadata:
    """Test ImageMetadata model."""

    def test_rx_image_metadata(self):
        """RX image should include SNR and frequency offset."""
        img = ImageMetadata(
            id=uuid4(),
            filepath="/home/admin/sstv_images/rx_20250115_123045.png",
            mode=SSTVMode.MARTIN_M2,
            direction="rx",
            callsign="W1AW",
            timestamp=datetime.now(timezone.utc),
            snr_db=15.2,
            frequency_offset_hz=-8.5,
            width=320,
            height=256,
        )
        assert img.direction == "rx"
        assert img.snr_db == 15.2

    def test_tx_image_metadata(self):
        """TX image shouldn't have SNR/offset."""
        img = ImageMetadata(
            id=uuid4(),
            filepath="/home/admin/sstv_images/tx_20250115_123045.png",
            mode=SSTVMode.ROBOT_36,
            direction="tx",
            timestamp=datetime.now(timezone.utc),
            width=320,
            height=240,
        )
        assert img.direction == "tx"
        assert img.snr_db is None

    def test_direction_validation(self):
        """Direction must be 'rx' or 'tx'."""
        with pytest.raises(ValidationError, match="rx|tx"):
            ImageMetadata(
                id=uuid4(),
                filepath="/home/admin/test.png",
                mode=SSTVMode.PD_90,
                direction="invalid",  # Bad value
                timestamp=datetime.now(timezone.utc),
                width=320,
                height=256,
            )


class TestImageListResponse:
    """Test ImageListResponse pagination."""

    def test_empty_list(self):
        """Empty image list should be valid."""
        resp = ImageListResponse(
            images=[],
            total=0,
            limit=20,
            offset=0,
        )
        assert len(resp.images) == 0
        assert resp.total == 0

    def test_paginated_list(self):
        """Paginated list should track offset/limit."""
        images = [
            ImageMetadata(
                id=uuid4(),
                filepath=f"/home/admin/img{i}.png",
                mode=SSTVMode.MARTIN_M1,
                direction="rx",
                timestamp=datetime.now(timezone.utc),
                width=320,
                height=256,
            )
            for i in range(10)
        ]
        resp = ImageListResponse(
            images=images,
            total=50,
            limit=10,
            offset=20,
        )
        assert len(resp.images) == 10
        assert resp.total == 50
        assert resp.offset == 20


class TestWebSocketEvents:
    """Test WebSocket event models."""

    def test_vis_detected_event(self):
        """VIS detected event should serialize."""
        event = VISDetectedEvent(
            mode=SSTVMode.SCOTTIE_S1,
            confidence=0.95,
            vis_code=60,
        )
        assert event.event_type == "vis_detected"
        assert event.confidence == 0.95

    def test_scanline_update_event(self):
        """Scanline update event should track progress."""
        event = ScanlineUpdateEvent(
            scanline_number=120,
            total_scanlines=256,
            progress_percent=46.875,
            snr_db=14.2,
            frequency_offset_hz=-5.3,
        )
        assert event.scanline_number == 120
        assert event.progress_percent == 46.875

    def test_decode_complete_event(self):
        """Decode complete event should include final stats."""
        event = DecodeCompleteEvent(
            image_id=uuid4(),
            mode=SSTVMode.ROBOT_36,
            snr_db=18.5,
            duration_seconds=72.3,
        )
        assert event.event_type == "decode_complete"
        assert event.duration_seconds == 72.3

    def test_error_event(self):
        """Error event should include recovery info."""
        event = ErrorEvent(
            error_code="DEVICE_FAILURE",
            message="Can't find that device - did you unplug it?",
            recoverable=True,
            suggested_action="Check audio device connections",
        )
        assert event.recoverable is True
        assert "unplug" in event.message  # SSTeVe voice


class TestEnums:
    """Test enum values match spec."""

    def test_sstv_modes(self):
        """All supported SSTV modes should be defined."""
        modes = [mode.value for mode in SSTVMode]
        assert "MartinM1" in modes
        assert "ScottieS1" in modes
        assert "Robot36" in modes
        assert "PD120" in modes

    def test_ptt_methods(self):
        """All PTT methods should be defined."""
        methods = [method.value for method in PTTMethod]
        assert "serial_rts" in methods
        assert "serial_dtr" in methods
        assert "vox" in methods
        assert "none" in methods

    def test_operating_modes(self):
        """Operating modes should match spec."""
        modes = [mode.value for mode in OperatingConditionMode]
        assert "standard" in modes
        assert "night_vision" in modes
        assert "sunlight" in modes
