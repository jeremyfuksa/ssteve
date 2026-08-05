"""Command-line interface for SSTeVe SSTV operations.

Provides decode and encode operations with verbose/JSON logging modes
for accessibility (screen reader compatibility).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class JSONFormatter(logging.Formatter):
    """JSON log formatter for screen reader accessibility."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
        }

        # Add extra fields if present
        if hasattr(record, "event_type"):
            log_data["event"] = record.event_type
        if hasattr(record, "progress"):
            log_data["progress"] = record.progress
        if hasattr(record, "data"):
            log_data.update(record.data)

        return json.dumps(log_data)


def setup_logging(verbose: bool = False, json_mode: bool = False) -> None:
    """Configure logging based on CLI mode.

    Args:
        verbose: Enable verbose logging (DEBUG level)
        json_mode: Use JSON formatter for screen readers
    """
    level = logging.DEBUG if verbose else logging.INFO

    # Create console handler
    handler = logging.StreamHandler(sys.stderr)

    if json_mode:
        # JSON mode for screen readers
        formatter = JSONFormatter()
    else:
        # Human-readable format
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(handler)


def log_event(event_type: str, **kwargs: Any) -> None:
    """Log an event with optional JSON data.

    Args:
        event_type: Type of event (vis_detected, scanline_update, etc.)
        **kwargs: Additional event data
    """
    # Create log record with extra attributes
    extra = {"event_type": event_type, "data": kwargs}
    logger.info(f"{event_type}: {kwargs}", extra=extra)


def cmd_decode(args: argparse.Namespace) -> int:
    """Execute decode command.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 = success)
    """
    from sstv_core.audio.device_manager import AudioDeviceManager

    log_event("decode_start", mode=args.mode, device=args.device)

    # Get audio devices
    device_mgr = AudioDeviceManager()
    devices = device_mgr.list_all_devices()

    if not devices:
        log_event("error", message="Can't find any audio devices")
        return 1

    # Select device
    if args.device:
        selected_device = None
        for dev in devices:
            if dev.id == args.device:
                selected_device = dev
                break

        if not selected_device:
            log_event(
                "error",
                message=f"Can't find device '{args.device}'",
                available_devices=[d.id for d in devices],
            )
            return 1
    else:
        # Use default input device
        selected_device = next(
            (d for d in devices if d.is_default and d.is_input),
            None,
        )
        if not selected_device:
            log_event("error", message="Can't find default input device")
            return 1

    log_event("device_selected", device_id=selected_device.id, device_name=selected_device.name)

    # TODO: Implement actual decode logic with StreamManager
    # For now, just demonstrate event logging
    log_event("listening", mode=args.mode, timeout_sec=args.timeout)

    # Simulate VIS detection
    log_event("vis_detected", mode=args.mode, confidence=0.98)

    # Simulate scanline updates
    for line in range(0, 256, 32):
        progress = (line / 256) * 100
        log_event(
            "scanline_update",
            line=line,
            total=256,
            progress=round(progress, 1),
        )

    log_event("decode_complete", lines=256, output_path="/tmp/decoded.jpg")

    return 0


def cmd_encode(args: argparse.Namespace) -> int:
    """Execute encode command.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 = success)
    """
    from sstv_core.audio.device_manager import AudioDeviceManager

    # Validate image path
    image_path = Path(args.image)
    if not image_path.exists():
        log_event("error", message=f"Can't find image file: {args.image}")
        return 1

    if not image_path.is_file():
        log_event("error", message=f"Not a file: {args.image}")
        return 1

    log_event("encode_start", image=args.image, mode=args.mode)

    # Get audio devices
    device_mgr = AudioDeviceManager()
    devices = device_mgr.list_all_devices()

    if not devices:
        log_event("error", message="Can't find any audio devices")
        return 1

    # Select device
    if args.device:
        selected_device = None
        for dev in devices:
            if dev.id == args.device:
                selected_device = dev
                break

        if not selected_device:
            log_event(
                "error",
                message=f"Can't find device '{args.device}'",
                available_devices=[d.id for d in devices],
            )
            return 1
    else:
        # Use default output device
        selected_device = next(
            (d for d in devices if d.is_default and d.is_output),
            None,
        )
        if not selected_device:
            log_event("error", message="Can't find default output device")
            return 1

    log_event("device_selected", device_id=selected_device.id, device_name=selected_device.name)

    # TODO: Implement actual encode logic
    # For now, demonstrate event logging
    log_event("image_loaded", width=320, height=256, mode=args.mode)
    log_event("encoding", estimated_duration_sec=114)

    # Simulate encoding progress
    for progress in range(0, 101, 10):
        log_event("encode_progress", progress=progress)

    log_event("transmit_complete", duration_sec=114)

    return 0


def cmd_list_devices(args: argparse.Namespace) -> int:
    """List available audio devices.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 = success)
    """
    from sstv_core.audio.device_manager import AudioDeviceManager

    device_mgr = AudioDeviceManager()
    devices = device_mgr.list_all_devices()

    if not devices:
        log_event("info", message="No audio devices found")
        return 0

    for dev in devices:
        device_info = {
            "device_id": dev.id,
            "name": dev.name,
            "inputs": dev.channels if dev.is_input else 0,
            "outputs": dev.channels if dev.is_output else 0,
            "sample_rate": dev.sample_rates[0] if dev.sample_rates else None,
            "is_default": dev.is_default,
        }

        if args.json:
            print(json.dumps({"event": "device", **device_info}))
        else:
            default_marker = " [DEFAULT]" if dev.is_default else ""
            print(
                f"{dev.id}: {dev.name}{default_marker}\n"
                f"  Inputs: {device_info['inputs']}, Outputs: {device_info['outputs']}, "
                f"Sample Rate: {device_info['sample_rate']} Hz"
            )

    return 0


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser for CLI.

    Returns:
        Configured ArgumentParser
    """
    parser = argparse.ArgumentParser(
        prog="sstv-cli",
        description="SSTeVe SSTV command-line interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Decode SSTV signal (auto-detect mode)
  sstv-cli decode --device "USB Audio" --timeout 300

  # Decode with specific mode
  sstv-cli decode --mode ScottieS1 --device "USB Audio"

  # Encode and transmit image
  sstv-cli encode --image photo.jpg --mode ScottieS1 --device "USB Audio"

  # List audio devices
  sstv-cli list-devices

  # Verbose mode with JSON logging (for screen readers)
  sstv-cli decode --verbose --json --device "USB Audio"
""",
    )

    # Global options
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging (DEBUG level)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output logs in JSON format (for screen readers)",
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Decode command
    decode_parser = subparsers.add_parser("decode", help="Decode SSTV signal from audio input")
    decode_parser.add_argument(
        "--mode",
        type=str,
        default=None,
        help="SSTV mode (ScottieS1, ScottieS2, MartinM1, Robot36, etc.). Auto-detect if not specified.",
    )
    decode_parser.add_argument(
        "--device",
        type=str,
        required=True,
        help="Audio input device ID (use list-devices to see options)",
    )
    decode_parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout in seconds (default: 300)",
    )
    decode_parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output image path (default: auto-generated timestamp)",
    )

    # Encode command
    encode_parser = subparsers.add_parser("encode", help="Encode image and transmit as SSTV")
    encode_parser.add_argument(
        "--image",
        type=str,
        required=True,
        help="Path to image file to transmit",
    )
    encode_parser.add_argument(
        "--mode",
        type=str,
        default="ScottieS1",
        help="SSTV mode (default: ScottieS1)",
    )
    encode_parser.add_argument(
        "--device",
        type=str,
        required=True,
        help="Audio output device ID (use list-devices to see options)",
    )
    encode_parser.add_argument(
        "--callsign",
        type=str,
        default=None,
        help="Callsign to overlay on image",
    )

    # List devices command
    subparsers.add_parser("list-devices", help="List available audio devices")

    return parser


def main(argv: list[str] | None = None) -> int:
    """Main entry point for CLI.

    Args:
        argv: Command-line arguments (None = use sys.argv)

    Returns:
        Exit code
    """
    parser = create_parser()
    args = parser.parse_args(argv)

    # Setup logging
    setup_logging(verbose=args.verbose, json_mode=args.json)

    # Dispatch to command handler
    if args.command == "decode":
        return cmd_decode(args)
    elif args.command == "encode":
        return cmd_encode(args)
    elif args.command == "list-devices":
        return cmd_list_devices(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
