"""PTT (Push-To-Talk) controller for SSTeVe."""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class PTTMethod(Enum):
    """PTT control method."""
    NONE = "none"
    SERIAL = "serial"
    VOX = "vox"


class PTTError(Exception):
    """Raised when PTT operations fail."""
    pass


class PTTController:
    """Controls PTT (Push-To-Talk) for radio transmission."""

    DEFAULT_PRE_DELAY_MS = 500
    DEFAULT_POST_DELAY_MS = 200
    DEFAULT_VOX_PREAMBLE_MS = 500
    DEFAULT_BAUD_RATE = 9600

    def __init__(
        self,
        method: PTTMethod = PTTMethod.NONE,
        serial_port: Optional[str] = None,
        serial_baud: int = DEFAULT_BAUD_RATE,
        serial_signal: str = "RTS",
        pre_delay_ms: int = DEFAULT_PRE_DELAY_MS,
        post_delay_ms: int = DEFAULT_POST_DELAY_MS,
        vox_preamble_ms: int = DEFAULT_VOX_PREAMBLE_MS,
        sample_rate: int = 48000,
    ) -> None:
        self._method = method
        self._serial_port = serial_port
        self._serial_baud = serial_baud
        self._serial_signal = serial_signal.upper()
        self._pre_delay_ms = pre_delay_ms
        self._post_delay_ms = post_delay_ms
        self._vox_preamble_ms = vox_preamble_ms
        self._sample_rate = sample_rate
        self._serial_connection = None
        self._is_keyed = False
        if self._serial_signal not in ("RTS", "DTR"):
            raise ValueError(f"Invalid serial signal: {serial_signal}. Must be RTS or DTR.")

    @property
    def method(self) -> PTTMethod:
        return self._method

    @property
    def is_keyed(self) -> bool:
        return self._is_keyed

    @property
    def pre_delay_ms(self) -> int:
        return self._pre_delay_ms

    @property
    def post_delay_ms(self) -> int:
        return self._post_delay_ms

    @property
    def vox_preamble_ms(self) -> int:
        return self._vox_preamble_ms

    def _open_serial(self) -> None:
        if self._serial_connection is not None:
            return
        if self._serial_port is None:
            raise PTTError("Can't open serial PTT - no port configured")
        try:
            import serial
            self._serial_connection = serial.Serial(
                port=self._serial_port,
                baudrate=self._serial_baud,
                timeout=1.0,
            )
            self._serial_connection.rts = False
            self._serial_connection.dtr = False
            logger.info("Opened serial port %s for PTT", self._serial_port)
        except ImportError:
            raise PTTError("Can't use serial PTT - pyserial not installed")
        except Exception as e:
            raise PTTError(f"Can't open serial port {self._serial_port}: {e}") from e

    def _close_serial(self) -> None:
        if self._serial_connection is not None:
            try:
                self._serial_connection.rts = False
                self._serial_connection.dtr = False
                self._serial_connection.close()
            except Exception as e:
                logger.warning("Error closing serial port: %s", e)
            finally:
                self._serial_connection = None
            logger.info("Closed serial port")

    def _set_serial_signal(self, state: bool) -> None:
        if self._serial_connection is None:
            self._open_serial()
        try:
            if self._serial_signal == "RTS":
                self._serial_connection.rts = state
            else:
                self._serial_connection.dtr = state
            logger.debug("Set %s to %s", self._serial_signal, state)
        except Exception as e:
            raise PTTError(f"Can't set {self._serial_signal} signal: {e}") from e

    async def key_radio(self) -> None:
        if self._is_keyed:
            logger.warning("Radio already keyed")
            return
        if self._method == PTTMethod.SERIAL:
            self._set_serial_signal(True)
            self._is_keyed = True
            logger.info("Keyed radio via %s", self._serial_signal)
            await asyncio.sleep(self._pre_delay_ms / 1000.0)
        elif self._method == PTTMethod.VOX:
            self._is_keyed = True
            logger.info("VOX mode - preamble will activate PTT")
        else:
            self._is_keyed = True
            logger.debug("PTT method is NONE - no keying action")

    async def unkey_radio(self) -> None:
        if not self._is_keyed:
            logger.warning("Radio not keyed")
            return
        if self._method == PTTMethod.SERIAL:
            await asyncio.sleep(self._post_delay_ms / 1000.0)
            self._set_serial_signal(False)
            self._is_keyed = False
            logger.info("Unkeyed radio via %s", self._serial_signal)
        elif self._method == PTTMethod.VOX:
            self._is_keyed = False
            logger.info("VOX mode - PTT will deactivate after audio")
        else:
            self._is_keyed = False
            logger.debug("PTT method is NONE - no unkeying action")

    def generate_vox_preamble(self) -> np.ndarray:
        num_samples = int(self._vox_preamble_ms * self._sample_rate / 1000)
        return np.zeros(num_samples, dtype=np.float32)

    def generate_vox_postamble(self) -> np.ndarray:
        num_samples = int(self._post_delay_ms * self._sample_rate / 1000)
        return np.zeros(num_samples, dtype=np.float32)

    def connect(self) -> None:
        if self._method == PTTMethod.SERIAL:
            self._open_serial()

    def disconnect(self) -> None:
        if self._is_keyed:
            if self._method == PTTMethod.SERIAL:
                try:
                    self._set_serial_signal(False)
                except PTTError:
                    pass
            self._is_keyed = False
        if self._method == PTTMethod.SERIAL:
            self._close_serial()

    def to_dict(self) -> dict:
        return {
            "method": self._method.value,
            "serial_port": self._serial_port,
            "serial_signal": self._serial_signal,
            "pre_delay_ms": self._pre_delay_ms,
            "post_delay_ms": self._post_delay_ms,
            "vox_preamble_ms": self._vox_preamble_ms,
            "is_keyed": self._is_keyed,
        }

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    async def __aenter__(self):
        self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
