"""Background producers for the app-level WebSocket channel (#57).

The session WebSockets only exist while something is decoding or
transmitting, so four documented needs had no channel at all: idle audio
metering, device hot-plug notification, library pushes to an idle gallery,
and global errors outside any session.

Two producers live here:

- **Device watcher.** `AudioDeviceManager.refresh()` is pull-only, so a
  client had to poll to notice a plugged-in interface. This diffs the device
  list on an interval and emits `device_changed`. It runs only while at
  least one app client is connected -- enumeration calls into PortAudio,
  and an idle headless server should do no work.

- **Input monitor.** Client-requested, never automatic: opening an input
  stream claims the audio device, which would collide with a decode
  session's own capture. Half-duplex applies to the microphone too.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import numpy as np

from sstv_core.api.models import (
    AudioLevelsEvent,
    DeviceChangedEvent,
    MonitorStateEvent,
)
from sstv_core.api.websocket_manager import websocket_manager

logger = logging.getLogger(__name__)

DEVICE_POLL_SECONDS = 3.0
LEVEL_EMIT_HZ = 10.0


def _to_db(value: float) -> float:
    """Linear amplitude to dBFS, floored so silence is a number not -inf."""
    return 20.0 * float(np.log10(value)) if value > 0 else -120.0


class AppChannel:
    """Owns the producers that only make sense while a client is watching."""

    def __init__(self) -> None:
        self._device_task: asyncio.Task | None = None
        self._monitor_task: asyncio.Task | None = None
        self._monitor_device_id: str | None = None
        self._known_devices: set[str] = set()
        self._lock = asyncio.Lock()

    # ---- Device hot-plug -------------------------------------------------

    async def ensure_device_watch(self) -> None:
        """Start the device poller if it is not already running."""
        async with self._lock:
            if self._device_task is None or self._device_task.done():
                self._known_devices = set()
                self._device_task = asyncio.create_task(self._watch_devices())
                logger.info("App channel: device watch started")

    async def stop_device_watch(self) -> None:
        """Stop polling once the last app client has gone."""
        async with self._lock:
            task, self._device_task = self._device_task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.info("App channel: device watch stopped")

    def _enumerate(self) -> set[str]:
        from sstv_core.audio.device_manager import AudioDeviceManager

        manager = AudioDeviceManager()
        return {str(device.id) for device in manager.list_all_devices()}

    async def _watch_devices(self) -> None:
        """Diff the device list on an interval; emit only on change."""
        loop = asyncio.get_running_loop()
        while True:
            try:
                # PortAudio enumeration is blocking and can be slow enough to
                # stutter the event loop on some hosts.
                current = await loop.run_in_executor(None, self._enumerate)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # A transient enumeration failure must not kill the watcher;
                # the next tick may succeed (that is the hot-plug case).
                logger.warning("App channel: device enumeration failed: %s", exc)
                await asyncio.sleep(DEVICE_POLL_SECONDS)
                continue

            if not self._known_devices:
                # First tick establishes the baseline. Emitting here would
                # report every existing device as newly "added".
                self._known_devices = current
            elif current != self._known_devices:
                added = sorted(current - self._known_devices)
                removed = sorted(self._known_devices - current)
                self._known_devices = current
                logger.info(
                    "App channel: devices changed (+%d/-%d)", len(added), len(removed)
                )
                await websocket_manager.broadcast_app(
                    DeviceChangedEvent(
                        added=added, removed=removed, total=len(current)
                    ).model_dump(mode="json")
                )

            await asyncio.sleep(DEVICE_POLL_SECONDS)

    # ---- Input monitoring ------------------------------------------------

    @property
    def is_monitoring(self) -> bool:
        return self._monitor_task is not None and not self._monitor_task.done()

    async def start_monitor(self, device_id: str | None) -> dict[str, Any]:
        """Open an input stream and stream levels until stopped.

        Refused while a decode session holds the input: two streams on one
        device is the audio equivalent of the half-duplex violation the
        session manager already prevents.
        """
        from sstv_core.api.dsp_manager import dsp_manager

        if dsp_manager._decode_tasks:
            return {
                "error": "INPUT_BUSY",
                "message": "I'm already listening on that input for a decode.",
                "suggested_action": "Stop the decode session first, then monitor.",
            }

        await self.stop_monitor(quiet=True)
        self._monitor_device_id = device_id
        self._monitor_task = asyncio.create_task(self._stream_levels(device_id))
        await websocket_manager.broadcast_app(
            MonitorStateEvent(monitoring=True, device_id=device_id).model_dump(
                mode="json"
            )
        )
        return {}

    async def stop_monitor(self, quiet: bool = False) -> None:
        """Close the monitoring stream if one is open."""
        task, self._monitor_task = self._monitor_task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if not quiet:
            await websocket_manager.broadcast_app(
                MonitorStateEvent(
                    monitoring=False, device_id=self._monitor_device_id
                ).model_dump(mode="json")
            )
        self._monitor_device_id = None

    async def _stream_levels(self, device_id: str | None) -> None:
        from sstv_core.api.dsp_manager import dsp_manager
        from sstv_core.audio.stream_manager import AudioStreamManager

        stream = AudioStreamManager()
        index = None
        try:
            index = dsp_manager._resolve_device_index(device_id)
        except ValueError as exc:
            await websocket_manager.broadcast_app(
                {
                    "event_type": "error",
                    "error_code": "DEVICE_NOT_FOUND",
                    "message": str(exc),
                    "recoverable": True,
                }
            )
            return

        try:
            stream.start_input(device_index=index)
        except Exception as exc:
            logger.warning("App channel: could not open input for monitoring: %s", exc)
            await websocket_manager.broadcast_app(
                {
                    "event_type": "error",
                    "error_code": "MONITOR_FAILED",
                    "message": f"I couldn't open that input: {exc}",
                    "recoverable": True,
                    "suggested_action": "Check the device is present and not in use.",
                }
            )
            return

        try:
            while True:
                levels = stream.get_input_levels()
                rms_db = _to_db(levels.rms)
                await websocket_manager.broadcast_app(
                    AudioLevelsEvent(
                        left_db=rms_db,
                        right_db=rms_db,  # mono source
                        peak_db=_to_db(levels.peak),
                        is_clipping=bool(levels.is_clipping),
                    ).model_dump(mode="json")
                )
                await asyncio.sleep(1.0 / LEVEL_EMIT_HZ)
        except asyncio.CancelledError:
            raise
        finally:
            # The device must be released whichever way this ends -- a
            # monitor left holding the input blocks the next decode.
            stream.stop_input()

    async def shutdown(self) -> None:
        """Stop both producers (server shutdown)."""
        await self.stop_monitor(quiet=True)
        await self.stop_device_watch()


app_channel = AppChannel()
