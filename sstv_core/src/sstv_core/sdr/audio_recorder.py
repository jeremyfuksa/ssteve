"""Write received audio to a WAV file while decoding continues.

An overnight listen is worth more than the images that came out of it: a
recording can be re-decoded when a decoder improves, and it is the only way
to find out what a decoder missed. This existed only as a separate SDR
program pointed at the same radio, which meant the recording and the decode
saw different audio.

Like `AudioMonitorServer`, this takes audio from the SpyServer receive
thread and must never make that thread wait. Disk I/O happens on a writer
thread; the receive thread only appends to a bounded queue and returns. A
disk that cannot keep up loses audio, never time.
"""

from __future__ import annotations

import logging
import queue
import threading
import wave
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

#: Blocks held for the writer before the oldest is dropped. At the SpyServer's
#: block size this is a couple of seconds of slack -- enough to ride out a
#: filesystem hiccup, small enough that a genuinely stuck disk is visible in
#: `dropped_blocks` rather than eating memory all night.
_QUEUE_BLOCKS = 64


class AudioRecorder:
    """Append received audio to a 16-bit mono WAV on a writer thread."""

    def __init__(self, path: Path | str, sample_rate: int) -> None:
        """Prepare to record to `path`; nothing is opened until start()."""
        self._path = Path(path)
        self._sample_rate = sample_rate
        self._queue: queue.Queue[bytes | None] = queue.Queue(maxsize=_QUEUE_BLOCKS)
        self._thread: threading.Thread | None = None
        self._handle: wave.Wave_write | None = None
        self._running = False
        self._dropped_blocks = 0
        self._frames_written = 0
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def dropped_blocks(self) -> int:
        """Blocks discarded because the writer fell behind.

        Non-zero means the recording has gaps. It never means the decode was
        affected -- dropping here is what protects it.
        """
        return self._dropped_blocks

    @property
    def frames_written(self) -> int:
        with self._lock:
            return self._frames_written

    @property
    def duration_sec(self) -> float:
        return self.frames_written / self._sample_rate if self._sample_rate else 0.0

    def start(self) -> None:
        """Open the file and start the writer thread."""
        if self._running:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        handle = wave.open(str(self._path), "wb")
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(self._sample_rate)
        self._handle = handle
        self._running = True
        self._thread = threading.Thread(
            target=self._write_loop, name="audio-recorder", daemon=True
        )
        self._thread.start()
        logger.info("Recording to %s at %d Hz", self._path, self._sample_rate)

    def write(self, audio: np.ndarray) -> None:
        """Queue one block of float32 audio.

        Called from the SpyServer receive thread. Converts and appends --
        no file I/O, no blocking, and no exception ever escapes. When the
        queue is full the block is dropped.
        """
        try:
            if not self._running or len(audio) == 0:
                return
            pcm = self._to_pcm16(audio)
            try:
                self._queue.put_nowait(pcm)
            except queue.Full:
                self._dropped_blocks += 1
        except Exception:
            # Deliberately swallowing: this runs on the thread that keeps
            # the SpyServer stream alive. A recording bug must never
            # surface there and cost an image.
            logger.debug("Audio recorder write failed", exc_info=True)

    def stop(self) -> None:
        """Drain what is queued, close the file, and join the writer.

        Closing matters more here than for a monitor: `wave` writes its
        length fields on close, so a file abandoned without this reports a
        wrong duration to anything that reads it.
        """
        if not self._running:
            return
        self._running = False
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            # Full queue and a sentinel that cannot fit: drop a block so
            # the writer still learns to stop.
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(None)
            except (queue.Empty, queue.Full):
                pass
        thread = self._thread
        if thread is not None:
            thread.join(timeout=5.0)
        self._close_handle()
        logger.info(
            "Recorded %.1fs to %s (%d blocks dropped)",
            self.duration_sec,
            self._path,
            self._dropped_blocks,
        )

    def _write_loop(self) -> None:
        while True:
            try:
                block = self._queue.get(timeout=0.5)
            except queue.Empty:
                if not self._running:
                    return
                continue
            if block is None:
                return
            handle = self._handle
            if handle is None:
                return
            try:
                handle.writeframes(block)
                with self._lock:
                    self._frames_written += len(block) // 2
            except Exception:
                # A failed write is worth knowing about, but not worth
                # taking the decode down for.
                logger.warning("Recording write failed", exc_info=True)
                return

    def _close_handle(self) -> None:
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        try:
            handle.close()
        except Exception:
            logger.debug("Closing the recording failed", exc_info=True)

    @staticmethod
    def _to_pcm16(audio: np.ndarray) -> bytes:
        """float32 in [-1, 1] to little-endian int16 bytes."""
        clipped = np.clip(audio, -1.0, 1.0)
        return bytes((clipped * 32767.0).astype("<i2").tobytes())
