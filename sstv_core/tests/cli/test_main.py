"""Tests for CLI main interface."""

import json
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from sstv_core.cli.main import JSONFormatter, create_parser, log_event, setup_logging


class TestArgumentParser:
    """Tests for CLI argument parser."""

    def test_parser_requires_command(self):
        """Parser requires a subcommand."""
        parser = create_parser()

        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_decode_command_requires_device(self):
        """Decode command requires --device."""
        parser = create_parser()

        with pytest.raises(SystemExit):
            parser.parse_args(["decode"])

    def test_decode_command_with_device(self):
        """Decode command parses with device."""
        parser = create_parser()
        args = parser.parse_args(["decode", "--device", "test_device"])

        assert args.command == "decode"
        assert args.device == "test_device"
        assert args.mode is None  # Auto-detect
        assert args.timeout == 300  # Default

    def test_decode_command_with_mode(self):
        """Decode command parses with mode specified."""
        parser = create_parser()
        args = parser.parse_args(["decode", "--device", "test", "--mode", "ScottieS1"])

        assert args.mode == "ScottieS1"

    def test_decode_command_with_timeout(self):
        """Decode command parses with custom timeout."""
        parser = create_parser()
        args = parser.parse_args(["decode", "--device", "test", "--timeout", "600"])

        assert args.timeout == 600

    def test_encode_command_requires_image_and_device(self):
        """Encode command requires --image and --device."""
        parser = create_parser()

        with pytest.raises(SystemExit):
            parser.parse_args(["encode"])

        with pytest.raises(SystemExit):
            parser.parse_args(["encode", "--image", "test.jpg"])

    def test_encode_command_with_required_args(self):
        """Encode command parses with required arguments."""
        parser = create_parser()
        args = parser.parse_args(["encode", "--image", "test.jpg", "--device", "test_device"])

        assert args.command == "encode"
        assert args.image == "test.jpg"
        assert args.device == "test_device"
        assert args.mode == "ScottieS1"  # Default

    def test_encode_command_with_mode_and_callsign(self):
        """Encode command parses with mode and callsign."""
        parser = create_parser()
        args = parser.parse_args([
            "encode",
            "--image", "test.jpg",
            "--device", "test_device",
            "--mode", "MartinM1",
            "--callsign", "W1AW",
        ])

        assert args.mode == "MartinM1"
        assert args.callsign == "W1AW"

    def test_list_devices_command(self):
        """List-devices command parses correctly."""
        parser = create_parser()
        args = parser.parse_args(["list-devices"])

        assert args.command == "list-devices"

    def test_global_verbose_flag(self):
        """Global --verbose flag works."""
        parser = create_parser()
        args = parser.parse_args(["--verbose", "list-devices"])

        assert args.verbose is True

    def test_global_json_flag(self):
        """Global --json flag works."""
        parser = create_parser()
        args = parser.parse_args(["--json", "list-devices"])

        assert args.json is True


class TestLogging:
    """Tests for logging functionality."""

    def test_json_formatter_basic(self):
        """JSONFormatter formats log record as JSON."""
        import logging

        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert "timestamp" in parsed
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "Test message"

    def test_json_formatter_with_event_type(self):
        """JSONFormatter includes event_type if present."""
        import logging

        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="VIS detected",
            args=(),
            exc_info=None,
        )
        record.event_type = "vis_detected"

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["event"] == "vis_detected"

    def test_json_formatter_with_extra_data(self):
        """JSONFormatter includes extra data fields."""
        import logging

        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Progress",
            args=(),
            exc_info=None,
        )
        record.event_type = "scanline_update"
        record.data = {"line": 128, "total": 256}

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["event"] == "scanline_update"
        assert parsed["line"] == 128
        assert parsed["total"] == 256

    def test_setup_logging_default(self):
        """Setup logging with default settings."""
        import logging

        # Clear existing handlers
        root = logging.getLogger()
        root.handlers.clear()

        setup_logging(verbose=False, json_mode=False)

        assert root.level == logging.INFO
        assert len(root.handlers) == 1

    def test_setup_logging_verbose(self):
        """Setup logging with verbose enabled."""
        import logging

        root = logging.getLogger()
        root.handlers.clear()

        setup_logging(verbose=True, json_mode=False)

        assert root.level == logging.DEBUG

    def test_setup_logging_json_mode(self):
        """Setup logging with JSON formatter."""
        import logging

        root = logging.getLogger()
        root.handlers.clear()

        setup_logging(verbose=False, json_mode=True)

        handler = root.handlers[0]
        assert isinstance(handler.formatter, JSONFormatter)

    @patch("sstv_core.cli.main.logger")
    def test_log_event_basic(self, mock_logger):
        """log_event emits structured event."""
        log_event("test_event", foo="bar", value=42)

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args

        # Check message
        assert "test_event" in call_args[0][0]

        # Check extra attributes
        assert call_args[1]["extra"]["event_type"] == "test_event"
        assert call_args[1]["extra"]["data"]["foo"] == "bar"
        assert call_args[1]["extra"]["data"]["value"] == 42


class TestCLICommands:
    """Tests for CLI command execution."""

    @patch("sstv_core.audio.device_manager.AudioDeviceManager")
    @patch("sstv_core.database.models.init_database")
    def test_decode_command_no_devices(self, mock_init_db, mock_device_mgr):
        """Decode command fails gracefully when no devices found."""
        from sstv_core.cli.main import cmd_decode

        mock_device_mgr.return_value.list_devices.return_value = []

        parser = create_parser()
        args = parser.parse_args(["decode", "--device", "test"])

        exit_code = cmd_decode(args)

        assert exit_code == 1  # Error

    @patch("sstv_core.audio.device_manager.AudioDeviceManager")
    def test_encode_command_missing_image(self, mock_device_mgr):
        """Encode command fails when image file doesn't exist."""
        from sstv_core.cli.main import cmd_encode

        parser = create_parser()
        args = parser.parse_args(["encode", "--image", "/nonexistent/image.jpg", "--device", "test"])

        exit_code = cmd_encode(args)

        assert exit_code == 1  # Error

    @patch("sstv_core.audio.device_manager.AudioDeviceManager")
    def test_list_devices_command_empty(self, mock_device_mgr):
        """List-devices command handles no devices gracefully."""
        from sstv_core.cli.main import cmd_list_devices

        mock_device_mgr.return_value.list_devices.return_value = []

        parser = create_parser()
        args = parser.parse_args(["list-devices"])

        exit_code = cmd_list_devices(args)

        assert exit_code == 0  # Success (but no devices)

    @patch("sstv_core.audio.device_manager.AudioDeviceManager")
    def test_list_devices_command_with_devices(self, mock_device_mgr):
        """List-devices command displays devices."""
        from sstv_core.api.models import AudioDevice
        from sstv_core.cli.main import cmd_list_devices

        # Mock devices
        devices = [
            AudioDevice(
                device_id="dev1",
                name="Test Device 1",
                max_input_channels=2,
                max_output_channels=2,
                default_sample_rate=48000,
                is_default=True,
            ),
            AudioDevice(
                device_id="dev2",
                name="Test Device 2",
                max_input_channels=0,
                max_output_channels=2,
                default_sample_rate=44100,
                is_default=False,
            ),
        ]
        mock_device_mgr.return_value.list_devices.return_value = devices

        parser = create_parser()
        args = parser.parse_args(["list-devices"])

        exit_code = cmd_list_devices(args)

        assert exit_code == 0


class TestCLIMain:
    """Tests for main entry point."""

    @patch("sstv_core.cli.main.cmd_list_devices")
    def test_main_dispatches_to_list_devices(self, mock_cmd):
        """main() dispatches to correct command handler."""
        from sstv_core.cli.main import main

        mock_cmd.return_value = 0

        exit_code = main(["list-devices"])

        assert exit_code == 0
        mock_cmd.assert_called_once()

    def test_main_with_no_args_fails(self):
        """main() with no arguments exits with error."""
        from sstv_core.cli.main import main

        with pytest.raises(SystemExit):
            main([])
