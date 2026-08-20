"""Direct USB access to an Airspy HF+, via libairspyhf.

Until now the only IQ source was SpyServer, so a radio plugged into this
machine had to be published over the network before SSTeVe could hear it.
This talks to the device through the same `_Client` protocol
`SpyServerSource` consumes, so the demodulator, the ring buffer and every
decoder are untouched -- a local radio is a different transport, not a
different pipeline.

**Not verified against real hardware.** The Airspy HF+ this project uses
is attached to another machine and reached over SpyServer; nothing on the
machine that runs the test suite has one, and CI has no `libairspyhf`.
The tests cover protocol conformance, the ctypes marshalling and the
error paths. They cannot prove this opens a real radio, and every
hardware defect that mattered in this codebase -- digital gain pinned at
0, a forced UINT8 format, a stale ClientSync -- was invisible until code
ran against the actual device. Treat the first live run as the real test.

`libairspyhf` is loaded lazily and by name. It is not a Python
dependency and must not become one: importing the CLI cannot require a C
library that most installs have no reason to carry, and every CI runner
is such an install. Absence is reported at `connect()` as an error with a
way forward, never as an ImportError at module load.

    brew install airspyhf          # macOS
    apt install libairspyhf-dev    # Debian/Ubuntu
"""

from __future__ import annotations

import ctypes
import ctypes.util
import logging
import threading
from collections.abc import Callable
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

#: Sample rate asked of the device. The HF+ publishes its own list via
#: airspyhf_get_samplerates and 768 kHz is its standard HF rate; the
#: demodulator decimates from whatever it gets, so this is a request
#: rather than a requirement.
DEFAULT_SAMPLE_RATE = 768_000

#: The HF+ attenuator, in 6 dB steps (airspyhf_set_hf_att takes 0-8).
#: There is no gain control on this radio -- there is an attenuator and an
#: AGC -- so the CLI's `--gain 0..8` is mapped onto it inverted: the
#: highest gain is the *least* attenuation. Getting this backwards would
#: deafen the radio at exactly the setting that asks for most sensitivity.
MAX_ATTENUATION_INDEX = 8

#: Names to try, in order, for the shared library.
_LIBRARY_NAMES = ("airspyhf", "libairspyhf.so.0", "libairspyhf.dylib")

#: Absolute paths tried after the bare names and after
#: ctypes.util.find_library, which is not enough on its own.
#: `brew install airspyhf` puts the dylib in /opt/homebrew/lib on Apple
#: Silicon, and find_library() does not look there -- it returned None
#: with the library plainly installed (measured 2026-08-20). Without
#: these, every Apple Silicon user would be told to install a library
#: they already have.
_LIBRARY_PATHS = (
    "/opt/homebrew/lib/libairspyhf.dylib",  # Homebrew, Apple Silicon
    "/usr/local/lib/libairspyhf.dylib",  # Homebrew, Intel
    "/usr/lib/libairspyhf.so.0",
    "/usr/local/lib/libairspyhf.so.0",
)


class AirspyHFError(Exception):
    """A failure talking to a locally attached Airspy HF+.

    Carries `suggested_action` like SpyServerError, so the CLI and API
    report a USB failure in the same voice as a network one.
    """

    def __init__(self, message: str, suggested_action: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.suggested_action = suggested_action


class _ComplexFloat(ctypes.Structure):
    """airspyhf_complex_float_t."""

    _fields_ = [("re", ctypes.c_float), ("im", ctypes.c_float)]  # noqa: RUF012


class _Transfer(ctypes.Structure):
    """airspyhf_transfer_t.

    Field order is load-bearing: ctypes reads the struct by offset, so a
    field out of place silently misreads every sample.
    """

    _fields_ = [  # noqa: RUF012
        ("device", ctypes.c_void_p),
        ("ctx", ctypes.c_void_p),
        ("samples", ctypes.POINTER(_ComplexFloat)),
        ("sample_count", ctypes.c_int),
        ("dropped_samples", ctypes.c_uint64),
    ]


_CALLBACK = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(_Transfer))


def _load_library() -> Any | None:
    """Find libairspyhf, or None. Never raises.

    Returning None rather than raising is what keeps `airspyhf_available()`
    usable as a plain question on a machine that has no SDR at all.
    """
    for name in _LIBRARY_NAMES:
        try:
            return ctypes.CDLL(name)
        except OSError:
            continue
    found = ctypes.util.find_library("airspyhf")
    if found:
        try:
            return ctypes.CDLL(found)
        except OSError:
            pass
    for path in _LIBRARY_PATHS:
        try:
            return ctypes.CDLL(path)
        except OSError:
            continue
    return None


def airspyhf_available() -> bool:
    """Whether a local Airspy HF+ could be opened at all.

    Answers "is the library installed", not "is a radio plugged in" --
    the second question needs an open(), which is `connect()`'s job.
    """
    return _load_library() is not None


def interleaved_to_complex(samples: np.ndarray) -> np.ndarray:
    """Pack [I, Q, I, Q, ...] floats into complex64.

    An odd trailing float is dropped rather than carried: half a sample is
    not a sample, and pairing it with the next block's first float would
    rotate I and Q against each other for the rest of the stream.
    """
    usable = len(samples) - (len(samples) % 2)
    if usable <= 0:
        return np.array([], dtype=np.complex64)
    pairs = samples[:usable].reshape(-1, 2)
    return (pairs[:, 0] + 1j * pairs[:, 1]).astype(np.complex64)


class AirspyHFClient:
    """One locally attached Airspy HF+, shaped like a SpyServer client.

    Deliberately mirrors `SpyServerClient`'s surface -- `sample_rate`,
    `dropped_frames`, `stream_error`, `device_info`, and the connect /
    tune / start_streaming / stop_streaming / close lifecycle -- so
    `SpyServerSource` and everything downstream take it unchanged.
    """

    def __init__(self, sample_rate: int = DEFAULT_SAMPLE_RATE) -> None:
        self._requested_rate = sample_rate
        self._sample_rate = sample_rate
        self._lib: Any | None = None
        self._device = ctypes.c_void_p()
        self._on_iq: Callable[[np.ndarray], None] | None = None
        # Held for the lifetime of the stream: ctypes does not keep a
        # reference to the trampoline, and letting it be collected while
        # the C thread still calls it is a segfault, not an exception.
        self._callback: Any | None = None
        self._lock = threading.Lock()
        self.dropped_frames = 0
        # Typed as AirspyHFError, not Exception: consumers read .message
        # and .suggested_action off it, which a bare Exception has not
        # got -- and the _Client protocol checks for exactly those.
        self.stream_error: AirspyHFError | None = None

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def device_info(self) -> object | None:
        """Nothing to report: USB carries no DeviceInfo message.

        The fields SpyServer sends describe a server rather than a radio,
        and consumers already treat this as optional.
        """
        return None

    def connect(self) -> None:
        lib = _load_library()
        if lib is None:
            raise AirspyHFError(
                "I couldn't find libairspyhf, so I can't reach a USB Airspy HF+.",
                suggested_action=(
                    "Install it -- `brew install airspyhf` on macOS, "
                    "`apt install libairspyhf-dev` on Debian -- or use "
                    "--spyserver to reach a radio over the network instead."
                ),
            )
        self._lib = lib
        result = lib.airspyhf_open(ctypes.byref(self._device))
        if result != 0 or not self._device:
            raise AirspyHFError(
                "I found the Airspy library but no radio answered on USB.",
                suggested_action=(
                    "Check the device is plugged in and not already open in "
                    "another program -- SDR#, SpyServer and gqrx all claim it "
                    "exclusively."
                ),
            )
        self._set_sample_rate()

    def _set_sample_rate(self) -> None:
        if self._lib is None:
            return
        if self._lib.airspyhf_set_samplerate(self._device, self._requested_rate) != 0:
            # Not fatal: the radio keeps whatever rate it had, and the
            # demodulator decimates from whatever arrives. Saying so beats
            # failing a session over a preference.
            logger.warning(
                "Airspy HF+ refused %d Hz; keeping its current rate",
                self._requested_rate,
            )
            return
        self._sample_rate = self._requested_rate

    def tune(self, frequency_hz: int) -> None:
        if self._lib is None or not self._device:
            raise AirspyHFError(
                "I'm not connected to a USB radio yet.",
                suggested_action="Connect first.",
            )
        if self._lib.airspyhf_set_freq(self._device, int(frequency_hz)) != 0:
            raise AirspyHFError(
                f"The radio wouldn't tune to {frequency_hz} Hz.",
                suggested_action=(
                    "The Airspy HF+ covers 0.5-31 MHz and 60-260 MHz; "
                    "frequencies between those ranges have no coverage."
                ),
            )

    def start_streaming(
        self, on_iq: Callable[[np.ndarray], None], gain: int = 0
    ) -> None:
        if self._lib is None or not self._device:
            raise AirspyHFError(
                "I'm not connected to a USB radio yet.",
                suggested_action="Connect first.",
            )
        self._on_iq = on_iq
        self.dropped_frames = 0
        self.stream_error = None

        # Attenuation, inverted from gain. See MAX_ATTENUATION_INDEX: this
        # radio has no gain stage, and the highest gain is the least
        # attenuation.
        attenuation = max(0, MAX_ATTENUATION_INDEX - int(gain))
        self._lib.airspyhf_set_hf_agc(self._device, 0)
        self._lib.airspyhf_set_hf_att(self._device, attenuation)

        self._callback = _CALLBACK(self._on_transfer)
        if self._lib.airspyhf_start(self._device, self._callback, None) != 0:
            self._callback = None
            raise AirspyHFError(
                "The radio wouldn't start streaming.",
                suggested_action="Unplug and replug it, then try again.",
            )

    def _on_transfer(self, transfer_p: Any) -> int:
        """Receive one block from libairspyhf's own thread.

        Must never raise into C.

        An exception crossing back into a C callback is undefined
        behaviour, so everything here is caught and latched into
        `stream_error` for the session to notice -- the same channel a
        dropped SpyServer stream reports through.
        """
        try:
            transfer = transfer_p.contents
            count = int(transfer.sample_count)
            if count <= 0:
                return 0
            if transfer.dropped_samples:
                self.dropped_frames += int(transfer.dropped_samples)
            # Two floats per complex sample, read without copying the C
            # buffer twice.
            raw = np.ctypeslib.as_array(
                ctypes.cast(transfer.samples, ctypes.POINTER(ctypes.c_float)),
                shape=(count * 2,),
            )
            iq = interleaved_to_complex(np.array(raw, dtype=np.float32))
            callback = self._on_iq
            if callback is not None:
                callback(iq)
        except Exception as exc:
            self.stream_error = AirspyHFError(
                f"I couldn't process the samples coming off the radio: {exc}",
                suggested_action="This is a fault on my side, not the radio's.",
            )
        return 0

    def stop_streaming(self) -> None:
        with self._lock:
            if self._lib is None or not self._device:
                return
            self._lib.airspyhf_stop(self._device)
            # Only after stop() returns: the C thread is finished with the
            # trampoline by then, and dropping it earlier is a segfault.
            self._callback = None

    def close(self) -> None:
        with self._lock:
            if self._lib is None or not self._device:
                return
            self._lib.airspyhf_close(self._device)
            self._device = ctypes.c_void_p()
            self._lib = None
