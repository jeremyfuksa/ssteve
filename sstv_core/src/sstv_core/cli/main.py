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
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)

# SSTV calling frequencies per band (PRODUCT.md "Push-button band access").
# HF only: FM demodulation is out of scope, so the 2m entries -- 145.500
# simplex and the 145.800 ARISS downlink -- are deliberately absent rather
# than tuned and mis-demodulated as SSB. 20m resolves to 14.230; the other
# common 20m frequency, 14.233, is reachable via --frequency.
BAND_PRESETS: dict[str, int] = {
    "80m": 3_845_000,
    "40m": 7_171_000,
    "20m": 14_230_000,
    "15m": 21_340_000,
    "10m": 28_680_000,
}

#: Bands we can name but not demodulate. Called out by name so the error
#: says why, instead of "unknown band" for a frequency an operator can
#: plainly see is a real SSTV calling frequency.
FM_BANDS: frozenset[str] = frozenset({"2m"})


#: RMS below which the receiver is effectively deaf rather than merely on
#: a quiet band. Measured on an Airspy HF+ against WWV 10 MHz (issue #90):
#: gain 0 gave rms 0.000231 with a spectral peak/mean of 4.5 -- noise, with
#: no carrier distinguishable in it -- while gain 6 gave rms 0.004929 and a
#: clean 155:1 carrier. This sits an order of magnitude above the deaf
#: reading and an order below the working noise floor, so neither
#: measurement lands near the boundary.
DEAF_RMS = 0.0005

#: RMS at or above which the input level is not the problem. The working
#: noise floor at a usable gain measured ~0.005; at or above that, "raise
#: the gain" would be bad advice.
HEALTHY_RMS = 0.005


def describe_level(rms: float) -> str:
    """Describe an RMS figure in one word.

    A bare float doesn't tell an operator whether 0.0002 is fine. These
    three words are the whole point of the listening heartbeat: they make
    "I'm hearing nothing at all" different from "I'm hearing noise" at a
    glance (issue #90).
    """
    if rms < DEAF_RMS:
        return "silent"
    if rms < HEALTHY_RMS:
        return "faint"
    return "healthy"


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

    formatter: logging.Formatter
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

    # A tuning flag means the SDR path even without --spyserver itself:
    # --band and --frequency are only meaningful there, so decoding from a
    # sound card instead would be a lie. --gain deliberately does NOT
    # count -- it's a SpyServer setting, but on its own it's too weak a
    # signal of intent to hijack a --file or --device run.
    wants_spyserver = bool(
        args.spyserver or args.band is not None or args.frequency is not None
    )
    if wants_spyserver:
        if args.file or args.device:
            log_event(
                "error",
                message="I can only listen to one source at a time.",
                suggested_action="Use --spyserver, --device, or --file -- not more than one.",
            )
            return 1
        return _decode_spyserver(args)

    if args.gain is not None and (args.file or args.device):
        # Saying so beats silently ignoring it: --gain is a SpyServer
        # setting and does nothing on a file or sound-card decode.
        log_event(
            "warning",
            message="--gain only applies to --spyserver, so I'm ignoring it here.",
        )

    if args.file:
        return _decode_file(args)

    if not args.device:
        # No source named at all. A stored SpyServer host is a real
        # answer to "listen to what?", so use it before complaining --
        # that's the point of saving one.
        if _spyserver_settings()["host"]:
            return _decode_spyserver(args)
        log_event(
            "error",
            message="I need either --device or --file to decode",
            suggested_action=(
                "Pass --device, --file, or --spyserver -- or save a server "
                "as spyserver.host in your settings."
            ),
        )
        return 1

    log_event("decode_start", mode=args.mode, device=args.device)

    # Get audio devices
    device_mgr = AudioDeviceManager()
    devices = device_mgr.list_all_devices()

    if not devices:
        log_event("error", message="Can't find any audio devices")
        return 1

    # Select device. --device is guaranteed non-empty here: the guard above
    # already returned when neither --device nor --file was given.
    selected_device = next((d for d in devices if d.id == args.device), None)
    if not selected_device:
        log_event(
            "error",
            message=f"Can't find device '{args.device}'",
            available_devices=[d.id for d in devices],
        )
        return 1

    log_event("device_selected", device_id=selected_device.id, device_name=selected_device.name)

    device_index = device_mgr.get_device_index(selected_device.id)
    return _decode_live(args, device_index)


def _decode_live(args: argparse.Namespace, device_index: int | None) -> int:
    """Decode from a live audio device through the real RX pipeline.

    Same RXManager the API server uses: VIS auto-detect (or forced --mode),
    bandpass, sync detection, per-mode decode, image save. (Until
    2026-08-08 the CLI's device path was an honest not-wired-up error; long
    before that it fabricated success events.)
    """
    import asyncio
    import shutil

    from sstv_core.audio.stream_manager import AudioStreamManager
    from sstv_core.decode.rx_manager import RXManager

    save_directory = (
        Path(args.output).resolve().parent if args.output else Path.home() / "sstv_images"
    )
    rx = RXManager(
        stream_manager=AudioStreamManager(),
        save_directory=save_directory,
    )

    def on_progress(progress) -> None:
        log_event(
            "rx_progress",
            state=progress.state.value,
            mode=progress.mode,
            line=progress.current_line,
            total=progress.total_lines,
            percent=round(progress.percent_complete, 1),
        )

    rx.set_progress_callback(on_progress)

    try:
        result = asyncio.run(
            rx.receive(
                input_device_index=device_index,
                mode=args.mode,
                timeout_sec=float(args.timeout),
                save_image=True,
                callsign=None,
            )
        )
    except KeyboardInterrupt:
        log_event("decode_stopped", message="Stopped by user.")
        return 130
    except Exception as exc:
        log_event(
            "error",
            message="Live decode failed.",
            detail=str(exc),
            suggested_action="Check the audio device with list-devices.",
        )
        return 1

    if result is None:
        log_event(
            "error",
            message="I didn't hear an SSTV transmission before the timeout.",
            suggested_action="Check the frequency and input level, or raise --timeout.",
        )
        return 2

    output = Path(args.output) if args.output else Path(result)
    if args.output and Path(result) != output:
        shutil.move(str(result), str(output))

    log_event("decode_complete", output_path=str(output))
    return 0


#: What SpyServerSettings gives us when there's no database to read.
#: Mirrors the model's own defaults (config/manager.py SpyServerSettings);
#: an empty host means "the operator hasn't saved one".
_SPYSERVER_CONFIG_DEFAULTS: dict[str, Any] = {
    "host": "",
    "port": 5555,
    "frequency_hz": 14_230_000,
    # None, not 0: 0 is a legal gain and a deaf one, so "unset" has to be
    # its own value. The source derives a gain from the device's ladder.
    "gain": None,
    "stall_timeout_sec": 5.0,
}


def _read_spyserver_config() -> dict[str, Any]:
    """Read stored SpyServer settings, following DSPManager's pattern.

    Synchronous where DSPManager._read_decode_config is async -- the CLI
    has no event loop -- but the same shape: a defaults dict, one
    ConfigManager, dot-notation keys, and the documented defaults when
    there's no usable database.
    """
    import os

    from sstv_core.config.manager import ConfigManager
    from sstv_core.database import init_database

    _engine, session_factory = init_database(db_path=os.environ.get("SSTVE_DB_PATH"))
    with session_factory() as db_session:
        config = ConfigManager(db_session)
        return {
            key: config.get(f"spyserver.{key}", default)
            for key, default in _SPYSERVER_CONFIG_DEFAULTS.items()
        }


def _spyserver_settings() -> dict[str, Any]:
    """Return stored settings, or the defaults when the database can't be read.

    A config failure must never stop a command that specified everything
    on the command line, so this never raises -- callers that genuinely
    need a stored value (an absent --spyserver) fail later, on the empty
    host, with an error that names the real problem.
    """
    try:
        return _read_spyserver_config()
    except Exception as exc:
        logger.warning("Couldn't read stored SpyServer settings: %s", exc)
        return dict(_SPYSERVER_CONFIG_DEFAULTS)


def _resolve_spyserver_target(
    args: argparse.Namespace, stored: dict[str, Any]
) -> tuple[str, int, int] | None:
    """Resolve the target to (host, port, frequency_hz).

    Flags always win; stored settings fill whatever a flag didn't specify,
    so an operator who saved a host and frequency once can just run
    `decode`. Returns None when nothing names a target we can tune; the
    error has already been logged.

    --band is validated here rather than with argparse `choices=`, which
    aborts the process with SystemExit(2) before main() can return an exit
    code or say anything in our voice.
    """
    if args.spyserver:
        host, _, port_text = args.spyserver.partition(":")
        if not host:
            log_event(
                "error",
                message="I need a hostname for --spyserver.",
                suggested_action="Pass --spyserver host or --spyserver host:port.",
            )
            return None
        try:
            port = int(port_text) if port_text else int(stored["port"])
        except ValueError:
            log_event(
                "error",
                message=f"I couldn't read '{port_text}' as a port number.",
                suggested_action=(
                    "Use --spyserver host:port, for example sdr.example.com:5555."
                ),
            )
            return None
    else:
        host = str(stored["host"])
        port = int(stored["port"])
        if not host:
            log_event(
                "error",
                message="I don't know which server to connect to.",
                suggested_action=(
                    "Pass --spyserver host:port, or save one in your settings "
                    "as spyserver.host."
                ),
            )
            return None

    if not 1 <= port <= 65535:
        log_event(
            "error",
            message=f"Port {port} is outside the range I can connect to.",
            suggested_action="Use a port between 1 and 65535.",
        )
        return None

    # A cheap sanity check only. The authoritative range is the device's
    # own maximum_gain_index, which doesn't arrive until connect(), so
    # SpyServerSource._resolve_gain does the real check and names the
    # actual range. This one just keeps obvious nonsense off the wire
    # without a round trip -- unvalidated, -1 raised a bare struct.error
    # (which is NOT a ValueError) and 99999 went silently onto the wire.
    if args.gain is not None and not 0 <= args.gain <= 63:
        log_event(
            "error",
            message=f"I can't set the gain to {args.gain}.",
            suggested_action=(
                "Use a gain index of 0 or more; your device's real upper "
                "limit is reported once I connect."
            ),
        )
        return None

    if args.frequency is not None:
        frequency = args.frequency
        if not 0 <= frequency <= 4_294_967_295:
            log_event(
                "error",
                message=f"I can't tune {frequency} Hz.",
                suggested_action="Give --frequency in Hz, for example 14230000 for 20m.",
            )
            return None
    elif args.band is not None:
        band = args.band.lower()
        if band in FM_BANDS:
            log_event(
                "error",
                message=f"I can't listen on {args.band} yet -- it's FM, and I only demodulate SSB.",
                suggested_action=(
                    "Use an HF band for now: " + ", ".join(sorted(BAND_PRESETS)) + "."
                ),
            )
            return None
        if band not in BAND_PRESETS:
            log_event(
                "error",
                message=f"I don't know a calling frequency for '{args.band}'.",
                suggested_action=(
                    "Try one of: "
                    + ", ".join(sorted(BAND_PRESETS))
                    + " -- or give --frequency in Hz."
                ),
            )
            return None
        frequency = BAND_PRESETS[band]
    else:
        # Neither flag given: the stored frequency, whose own default is
        # the 20m calling frequency.
        frequency = int(stored["frequency_hz"])

    return host, port, frequency


def _decode_spyserver(args: argparse.Namespace) -> int:
    """Decode from a SpyServer network stream.

    Same RXManager the sound-card path uses: the source is swapped, the
    decode stack is not.
    """
    import asyncio
    import shutil

    from sstv_core.decode.rx_manager import RXManager
    from sstv_core.sdr import source as source_module
    from sstv_core.sdr.spyserver.client import SpyServerError, StreamStalledError

    stored = _spyserver_settings()
    target = _resolve_spyserver_target(args, stored)
    if target is None:
        return 1
    host, port, frequency = target

    # Flag beats stored setting; None from both means "nobody chose", and
    # SpyServerSource derives one from the device's own gain ladder once
    # it has connected. Passing 0 here instead would be the deaf default
    # issue #90 is about.
    stored_gain = stored["gain"]
    gain = args.gain if args.gain is not None else (
        int(stored_gain) if stored_gain is not None else None
    )

    save_directory = (
        Path(args.output).resolve().parent if args.output else Path.home() / "sstv_images"
    )
    save_directory.mkdir(parents=True, exist_ok=True)

    # Looked up on the module at call time, not bound at import: the tests
    # substitute SpyServerSource here, and a direct import would give them
    # the real class and a real socket.
    src = source_module.SpyServerSource(
        host=host,
        port=port,
        frequency_hz=frequency,
        gain=gain,
        # No flag for this one -- config is its only route in.
        stall_timeout_sec=float(stored["stall_timeout_sec"]),
        monitor_port=getattr(args, "monitor_stream", None),
    )
    log_event(
        "decode_start",
        mode=args.mode,
        spyserver=f"{host}:{port}",
        frequency_hz=frequency,
        gain=gain if gain is not None else "auto",
    )

    # RXManager starts the source itself. Starting it here too would build
    # a second ring buffer that RXManager then replaces -- the audio would
    # land in the discarded one.
    rx = RXManager(stream_manager=src, save_directory=save_directory)

    # The loudest level seen while listening. The timeout message needs it:
    # "I heard nothing" and "I heard noise but no SSTV" call for different
    # advice, and only a measurement separates them. Peak rather than last,
    # so one quiet moment can't mask a band that was alive earlier.
    loudest_listening_rms = 0.0

    # The monitor's port is only known after RXManager has started the
    # source -- with --monitor-stream 0 the OS assigns it. The first
    # progress callback is the earliest point it can be read, and the
    # flag says the number is "reported once bound", so report it there.
    monitor_reported = False

    def on_progress(progress) -> None:
        nonlocal loudest_listening_rms, monitor_reported
        if not monitor_reported:
            # getattr, not attribute access: the source here is duck-typed
            # (AudioStreamManager is the other implementation, and tests
            # substitute their own), and only SpyServerSource carries a
            # monitor. A bare src.audio_monitor turned every such source
            # into a failed decode.
            monitor = getattr(src, "audio_monitor", None)
            if monitor is not None:
                monitor_reported = True
                log_event(
                    "monitor_stream",
                    port=monitor.port,
                    sample_rate=src.sample_rate,
                    encoding="pcm_s16le",
                    channels=1,
                )
        listening = progress.state.value == "listening"
        rms = getattr(progress.audio_levels, "rms", None)
        if listening and rms is not None:
            loudest_listening_rms = max(loudest_listening_rms, float(rms))
            # Its own event, not a field on rx_progress: this is the line
            # the operator watches during a long listen, and log_event
            # keeps it structured for --json screen-reader output.
            # `signal_level`, not `level`: JSONFormatter already emits
            # `level` for the log severity, and reusing the name
            # overwrote INFO with "silent" -- a screen reader parsing
            # severity would have read the audio reading instead.
            log_event(
                "listening_level",
                signal_level=describe_level(float(rms)),
                rms=round(float(rms), 6),
                elapsed_sec=round(progress.elapsed_sec, 1),
            )
            return

        log_event(
            "rx_progress",
            state=progress.state.value,
            mode=progress.mode,
            line=progress.current_line,
            total=progress.total_lines,
            percent=round(progress.percent_complete, 1),
        )

    rx.set_progress_callback(on_progress)

    result: Path | None = None
    try:
        result = asyncio.run(
            rx.receive(mode=args.mode, timeout_sec=float(args.timeout), save_image=True)
        )
    except SpyServerError as exc:
        log_event("error", message=exc.message, suggested_action=exc.suggested_action)
        return 1
    except KeyboardInterrupt:
        log_event("decode_stopped", message="Stopped by user.")
        return 130
    except Exception as exc:
        log_event(
            "error",
            message="The SpyServer decode failed.",
            detail=str(exc),
            suggested_action="Check the server address and frequency, then try again.",
        )
        return 1
    finally:
        # RXManager stops the source in its own finally block; this covers
        # a failure before receive() got that far. stop_input never raises.
        src.stop_input()

    # Order matters: a stream that dropped mid-decode also returns None.
    # Checking `result is None` first would report a dead TCP link as a
    # quiet band -- the one thing this command must never do.
    failure = src.stream_failure
    if failure is not None:
        # The detail follows the failure. It was hardcoded to "that's a
        # network problem" back when that was true of every stream
        # failure; once stall became its own case, a stalled stream got
        # three lines that contradicted each other -- the network both
        # was and wasn't at fault. Both branches still say "not a weak
        # signal", which is the confusion the ordering rule above exists
        # to prevent.
        if isinstance(failure, StreamStalledError):
            detail = (
                "The stream went silent -- that's the source or the radio, "
                "not a weak signal."
            )
        else:
            detail = "The stream failed -- that's a network problem, not a weak signal."
        log_event(
            "error",
            message=failure.message,
            detail=detail,
            suggested_action=failure.suggested_action,
        )
        if result is None:
            return 1
    if src.dropped_frames:
        log_event(
            "stream_warning",
            message=f"The server dropped {src.dropped_frames} frames.",
            suggested_action="Any gaps in the image came from the stream, not the signal.",
        )

    if result is None:
        # A quiet band and a deaf receiver produced identical wording
        # until now, which is what cost the first live session its first
        # decode (issue #90). The measured level separates them, so say
        # which one it was.
        if loudest_listening_rms < DEAF_RMS:
            log_event(
                "error",
                message=(
                    "I didn't hear an SSTV transmission before the timeout -- "
                    "and I barely heard anything at all."
                ),
                detail=(
                    f"Input stayed at {loudest_listening_rms:.6f} RMS the whole "
                    f"time, which reads as a deaf receiver rather than a quiet band."
                ),
                suggested_action=(
                    f"Raise --gain (I used {src.resolved_gain}) and try again."
                ),
            )
        else:
            log_event(
                "error",
                message="I didn't hear an SSTV transmission before the timeout.",
                detail=(
                    f"Input level was fine -- {loudest_listening_rms:.6f} RMS at its "
                    f"loudest -- so I was hearing the band, just no SSTV on it."
                ),
                suggested_action="Check the frequency and the band, or raise --timeout.",
            )
        return 2

    output = Path(args.output) if args.output else Path(result)
    if args.output and Path(result) != output:
        shutil.move(str(result), str(output))
    log_event("decode_complete", output_path=str(output))
    return 0


def _detect_mode_from_vis(audio: np.ndarray, sample_rate: int) -> str | None:
    """Detect the SSTV mode from the VIS header at the start of a recording.

    Returns the mode name (e.g. "SCOTTIE_S1") or None when no header is
    found with confidence. Only the opening seconds are searched -- a VIS
    header lives at the start of a transmission.
    """
    from sstv_core.decode.correlation_vis_detector import (
        CorrelationVISConfig,
        CorrelationVISDetector,
    )

    detector = CorrelationVISDetector(CorrelationVISConfig(sample_rate=sample_rate))
    chunk = 4096
    search_span = min(len(audio), sample_rate * 5)
    for start in range(0, search_span, chunk):
        result = detector.process_samples(audio[start : start + chunk])
        if result is not None and result.mode is not None:
            return result.mode.name
    return None


def _decode_file(args: argparse.Namespace) -> int:
    """Decode an SSTV image from a WAV file.

    Args:
        args: Parsed command-line arguments; `args.file` is the input path.

    Returns:
        Exit code (0 = success)

    """
    import wave
    from pathlib import Path

    import numpy as np

    from sstv_core.decode.martin_decoder import MartinM1Config, MartinM1Decoder
    from sstv_core.decode.robot_decoder import Robot36Config, Robot36Decoder
    from sstv_core.decode.scottie_decoder import ScottieS1Config, ScottieS1Decoder
    from sstv_core.decode.sync_detector import SyncPulseDetector

    decoders = {
        "scotties1": (ScottieS1Decoder, ScottieS1Config, 428.22),
        "martinm1": (MartinM1Decoder, MartinM1Config, 446.446),
        "robot36": (Robot36Decoder, Robot36Config, 150.0),
    }

    path = Path(args.file)
    if not path.exists():
        log_event("error", message=f"I couldn't find {path}")
        return 1

    try:
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            rate = handle.getframerate()
            frames = handle.readframes(handle.getnframes())
    except (wave.Error, OSError) as exc:
        log_event(
            "error",
            message=f"I couldn't read {path.name} as a WAV file.",
            detail=str(exc),
        )
        return 1

    if width != 2:
        log_event(
            "error",
            message=f"I can only read 16-bit WAV files; {path.name} is {width * 8}-bit.",
        )
        return 1

    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)

    log_event("audio_loaded", sample_rate=rate, duration_sec=round(len(audio) / rate, 2))

    if args.mode:
        mode_name = args.mode
    else:
        # No --mode: read the VIS header. Until 2026-08-07 this path
        # silently decoded everything as ScottieS1 while the help text
        # promised auto-detection.
        mode_name = _detect_mode_from_vis(audio, rate)
        if mode_name is None:
            log_event(
                "error",
                message="I couldn't find a VIS header to auto-detect the mode.",
                suggested_action=(
                    "Tell me the mode explicitly, e.g. --mode "
                    + " or --mode ".join(sorted(decoders))
                ),
            )
            return 2
        log_event("mode_detected", mode=mode_name, source="vis")

    mode_key = mode_name.lower().replace(" ", "").replace("_", "")
    entry = decoders.get(mode_key)
    if entry is None:
        log_event(
            "error",
            message=f"I don't have a decoder for '{mode_name}'.",
            suggested_action=f"Try one of: {', '.join(sorted(decoders))}",
        )
        return 1
    decoder_cls, config_cls, line_ms = entry

    log_event("decode_start", mode=mode_name, file=str(path))

    detector = SyncPulseDetector(sample_rate=rate)
    detector.detect_in_buffer(audio)
    positions = detector.get_sync_positions(line_duration_ms=line_ms)

    if not positions:
        log_event(
            "error",
            message="I couldn't find any sync pulses in that audio.",
            suggested_action=(
                "Check the file really contains an SSTV transmission, and that "
                "--mode matches how it was sent."
            ),
        )
        return 1

    log_event("sync_detected", line_starts=len(positions))

    config = config_cls(sample_rate=rate)
    decoder = decoder_cls(config)

    lines = 0
    for _ in decoder.decode_stream(iter([audio]), positions):
        lines += 1
        if lines % 32 == 0:
            log_event(
                "scanline_update",
                line=lines,
                total=config.height,
                progress=round(lines / config.height * 100, 1),
            )

    image = decoder.get_image()
    if image is None or lines == 0:
        log_event("error", message="I decoded no scanlines from that audio.")
        return 1

    output = Path(args.output) if args.output else path.with_suffix(".png")
    try:
        import cv2

        # imwrite reports failure (bad path, permissions) by returning False,
        # not by raising. Unchecked, we'd log decode_complete naming a file
        # that doesn't exist.
        if not cv2.imwrite(str(output), cv2.cvtColor(image, cv2.COLOR_RGB2BGR)):
            log_event(
                "error",
                message=f"I couldn't write the image to {output}.",
                suggested_action="Check the path exists and is writable.",
            )
            return 1
    except ImportError:
        log_event("error", message="I need opencv-python installed to save the image.")
        return 1

    log_event("decode_complete", lines=lines, output_path=str(output))
    return 0


def cmd_encode(args: argparse.Namespace) -> int:
    """Execute encode command.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 = success)

    """
    # Validate image path
    image_path = Path(args.image)
    if not image_path.exists():
        log_event("error", message=f"Can't find image file: {args.image}")
        return 1

    if not image_path.is_file():
        log_event("error", message=f"Not a file: {args.image}")
        return 1

    if not args.output and not args.device:
        log_event(
            "error",
            message="I need somewhere to put the audio.",
            suggested_action="Pass --output out.wav to write a file, or --device to transmit.",
        )
        return 1

    encoders = {
        "scotties1": ("SCOTTIE_S1", "ScottieS1Encoder"),
        "martinm1": ("MARTIN_M1", "MartinM1Encoder"),
        "robot36": ("ROBOT_36", "Robot36Encoder"),
    }
    mode_key = (args.mode or "ScottieS1").lower().replace(" ", "").replace("_", "")
    if mode_key not in encoders:
        log_event(
            "error",
            message=f"I don't have an encoder for '{args.mode}'.",
            suggested_action=f"Try one of: {', '.join(sorted(encoders))}",
        )
        return 1

    from sstv_core.encode.image_preprocessor import ImagePreprocessor, ModeResolution
    from sstv_core.encode.martin_encoder import MartinM1Encoder
    from sstv_core.encode.robot_encoder import Robot36Encoder
    from sstv_core.encode.scottie_encoder import ScottieS1Encoder
    from sstv_core.encode.vis_generator import SSTVMode

    encoder = {
        "scotties1": ScottieS1Encoder,
        "martinm1": MartinM1Encoder,
        "robot36": Robot36Encoder,
    }[mode_key]()
    mode = SSTVMode[encoders[mode_key][0]]

    log_event("encode_start", image=args.image, mode=mode.name)

    if args.callsign:
        # Overlay isn't implemented yet; saying so beats silently dropping it.
        log_event(
            "warning",
            message=f"I can't overlay '{args.callsign}' on the image yet -- sending without it.",
        )

    resolution = ModeResolution(
        width=encoder.config.width,
        height=encoder.config.height,
        aspect_ratio=encoder.config.width / encoder.config.height,
    )
    try:
        result = ImagePreprocessor(target_resolution=resolution).process(image_path)
    except Exception as exc:  # any load failure gets the same honest report
        log_event(
            "error",
            message=f"I couldn't load {image_path.name} as an image.",
            detail=str(exc),
        )
        return 1

    log_event(
        "image_loaded",
        width=encoder.config.width,
        height=encoder.config.height,
        mode=mode.name,
    )

    if args.output:
        import wave

        import numpy as np

        audio = encoder.encode_image(result.image, include_vis=True)
        duration = len(audio) / encoder.config.sample_rate
        pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
        try:
            with wave.open(args.output, "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(encoder.config.sample_rate)
                handle.writeframes(pcm.tobytes())
        except OSError as exc:
            log_event(
                "error",
                message=f"I couldn't write {args.output}.",
                detail=str(exc),
            )
            return 1
        log_event(
            "encode_complete",
            output_path=args.output,
            duration_sec=round(duration, 1),
        )
        return 0

    return _transmit_to_device(args, result.image, mode)


def _transmit_to_device(args: argparse.Namespace, image: np.ndarray, mode: Any) -> int:
    """Transmit a preprocessed image through a real audio device.

    Uses the same TXManager the API server uses: VOX PTT by default, real
    output stream, real completion status.
    """
    import asyncio

    from sstv_core.audio.device_manager import AudioDeviceManager
    from sstv_core.audio.ptt_controller import PTTController, PTTMethod
    from sstv_core.audio.stream_manager import AudioStreamManager
    from sstv_core.encode.tx_manager import TXManager

    device_mgr = AudioDeviceManager()
    devices = device_mgr.list_all_devices()
    selected = next((d for d in devices if d.id == args.device), None)
    if selected is None:
        log_event(
            "error",
            message=f"Can't find device '{args.device}'",
            available_devices=[d.id for d in devices],
        )
        return 1
    device_index = device_mgr.get_device_index(selected.id)
    log_event("device_selected", device_id=selected.id, device_name=selected.name)

    tx = TXManager(
        stream_manager=AudioStreamManager(),
        ptt_controller=PTTController(method=PTTMethod.VOX),
    )

    def on_progress(progress) -> None:
        log_event("tx_progress", **progress.to_dict())

    tx.set_progress_callback(on_progress)

    try:
        ok = asyncio.run(tx.transmit(image, mode=mode, output_device_index=device_index))
    except Exception as exc:  # report any transmit failure honestly
        log_event("error", message="Transmission failed.", detail=str(exc))
        return 1

    if not ok:
        log_event("error", message="Transmission did not complete.")
        return 1

    log_event("transmit_complete")
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


def _add_global_flags(
    parser: argparse.ArgumentParser, *, dest_suffix: str = ""
) -> None:
    """Register --verbose/--json on a parser.

    Called once for the top-level parser and once per subparser, and the
    two copies must not collide. argparse merges the subparser's results
    over the top-level namespace, so sharing a dest loses the earlier
    flag: with a `store_true` default of False, `--verbose decode` comes
    back False, and even `default=None` only downgrades True to None.
    Verified both ways before settling on separate dests.

    So the top-level copy stores to `verbose_global`/`json_global` and the
    subparser copy keeps the plain names; main() ORs the pair. `--verbose`
    then means the same thing on either side of the subcommand.
    """
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=None,
        dest=f"verbose{dest_suffix}",
        help="Enable verbose logging (DEBUG level)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=None,
        dest=f"json{dest_suffix}",
        help="Output logs in JSON format (for screen readers)",
    )


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

  # Decode from a SpyServer instead of a sound card (HF/SSB only)
  sstv-cli decode --spyserver sdr.example.com:5555 --band 20m

  # With a server saved in settings, no flags are needed at all
  sstv-cli decode

  # Encode and transmit image
  sstv-cli encode --image photo.jpg --mode ScottieS1 --device "USB Audio"

  # List audio devices
  sstv-cli list-devices

  # Verbose mode with JSON logging (for screen readers)
  sstv-cli decode --verbose --json --device "USB Audio"
""",
    )

    # Global options. Added to the top-level parser AND to every subparser
    # (see _add_global_flags): argparse only accepts a top-level flag
    # BEFORE the subcommand, and the console scripts -- sstv-decode,
    # sstv-encode -- prepend the subcommand, so the user's argv always
    # lands after it. Registering both places makes `--verbose` and
    # `--json` work in either position, which is what --json being the
    # screen-reader output path requires (issue #91).
    _add_global_flags(parser, dest_suffix="_global")

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Decode command
    decode_parser = subparsers.add_parser("decode", help="Decode SSTV signal from audio input")
    _add_global_flags(decode_parser)
    decode_parser.add_argument(
        "--mode",
        type=str,
        default=None,
        help="SSTV mode (ScottieS1, ScottieS2, MartinM1, Robot36, etc.). "
        "Auto-detect if not specified.",
    )
    decode_parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="Audio input device ID (use list-devices to see options). "
        "Required unless --file is given.",
    )
    decode_parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Decode a WAV file instead of listening to a device",
    )
    decode_parser.add_argument(
        "--spyserver",
        type=str,
        default=None,
        help="SpyServer to receive from, as host or host:port. Use instead of "
        "--device or --file. Defaults to the stored spyserver.host/port "
        "settings, so a saved server needs no flag at all.",
    )
    decode_parser.add_argument(
        "--band",
        type=str,
        default=None,
        help="Tune --spyserver to a band's SSTV calling frequency: "
        + ", ".join(sorted(BAND_PRESETS)),
    )
    decode_parser.add_argument(
        "--frequency",
        type=int,
        default=None,
        help="Tune --spyserver to this frequency in Hz (overrides --band). "
        "Defaults to the stored spyserver.frequency_hz setting "
        "(14230000, the 20m calling frequency, until you change it).",
    )
    decode_parser.add_argument(
        "--gain",
        type=int,
        default=None,
        help="SpyServer RF/IF gain index. The usable range is per-device and "
        "reported once I connect. Default: the stored spyserver.gain "
        "setting, or three-quarters of the device's own gain range.",
    )
    decode_parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout in seconds (default: 300)",
    )
    decode_parser.add_argument(
        "--monitor-stream",
        type=int,
        default=None,
        metavar="PORT",
        help="Serve the demodulated audio live on this TCP port while "
        "decoding, so you can hear the band the decoder is hearing. "
        "Raw 48 kHz signed 16-bit mono PCM, loopback only. Use 0 to let "
        "the OS pick a port (reported once bound). SpyServer only.",
    )
    decode_parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output image path (default: auto-generated timestamp)",
    )

    # Encode command
    encode_parser = subparsers.add_parser("encode", help="Encode image and transmit as SSTV")
    _add_global_flags(encode_parser)
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
        default=None,
        help="Audio output device ID to transmit through (use list-devices to see options)",
    )
    encode_parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Write the encoded audio to this WAV file instead of transmitting",
    )
    encode_parser.add_argument(
        "--callsign",
        type=str,
        default=None,
        help="Callsign to overlay on image",
    )

    # List devices command
    _add_global_flags(
        subparsers.add_parser("list-devices", help="List available audio devices")
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Command-line arguments (None = use sys.argv)

    Returns:
        Exit code

    """
    parser = create_parser()
    args = parser.parse_args(argv)

    # Collapse the before- and after-subcommand copies of each global flag
    # into the plain name, so everything downstream (cmd_list_devices reads
    # args.json) sees one merged value however the operator typed it.
    args.verbose = bool(args.verbose or args.verbose_global)
    args.json = bool(args.json or args.json_global)

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
