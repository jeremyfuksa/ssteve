"""Direct USB access to an Airspy HF+ via libairspyhf.

Until now the only IQ source was SpyServer, so a locally-attached radio
had to be published over the network before SSTeVe could hear it. This
speaks to the device through the same `_Client` protocol
`SpyServerSource` uses, so the demodulator, the ring buffer, and every
decoder are unchanged.

**These tests do not prove the driver opens a real radio.** The Airspy HF+
this project uses lives on another machine (192.168.1.30) and is reached
over SpyServer; there is no device on the machine that runs this suite,
and `libairspyhf` is not installed on CI. What is tested here is
everything that does not need the hardware: protocol conformance, the
ctypes marshalling, error paths, and -- most importantly -- that absence
of the library degrades to a clear error rather than an import crash.

The gap is real and is stated in the module docstring of the source too.
Every hardware defect that mattered this week (digital gain pinned at 0,
a forced UINT8 format, a stale client_sync) was invisible until code ran
against the actual radio.
"""

from __future__ import annotations

import numpy as np
import pytest

from sstv_core.sdr.airspyhf import (
    AirspyHFClient,
    AirspyHFError,
    airspyhf_available,
)


class TestItDegradesWithoutTheLibrary:
    """Absence of the library is the common case.

    CI has no libairspyhf and neither will most installs, so the failure
    has to be a legible error at open() time, never an
    ImportError at module load -- importing the CLI must not depend on a
    C library that most users have no reason to install.
    """

    def test_the_module_imports_without_the_library(self) -> None:
        """Already proven by this file importing at all, asserted so the
        intent survives a refactor.
        """
        from sstv_core.sdr import airspyhf

        assert airspyhf is not None

    def test_availability_is_reportable_without_raising(self) -> None:
        assert isinstance(airspyhf_available(), bool)

    def test_connect_without_the_library_explains_itself(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from sstv_core.sdr import airspyhf as mod

        monkeypatch.setattr(mod, "_load_library", lambda: None)
        client = AirspyHFClient()

        with pytest.raises(AirspyHFError) as caught:
            client.connect()

        assert "libairspyhf" in caught.value.message
        assert caught.value.suggested_action, "an error with no way forward"


class TestTheLibraryIsFoundWhereItIsInstalled:
    """`ctypes.util.find_library` is not enough on its own.

    Measured 2026-08-20 on Apple Silicon: `brew install airspyhf` puts the
    dylib in /opt/homebrew/lib, find_library() returned None, and the
    client told an operator to install a library that was plainly already
    there. Every Apple Silicon user would have hit that.
    """

    def test_homebrew_prefixes_are_searched(self) -> None:
        from sstv_core.sdr.airspyhf import _LIBRARY_PATHS

        assert any("/opt/homebrew/lib" in p for p in _LIBRARY_PATHS), (
            "Homebrew's Apple Silicon prefix is not searched, so an "
            "installed library reads as missing"
        )
        assert any("/usr/local/lib" in p for p in _LIBRARY_PATHS)

    def test_a_missing_library_still_reports_false_not_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The absent case has to stay a plain answer, not an exception."""
        import ctypes

        from sstv_core.sdr import airspyhf as mod

        def always_missing(name: str) -> None:
            raise OSError("not here")

        monkeypatch.setattr(ctypes, "CDLL", always_missing)
        monkeypatch.setattr(mod.ctypes.util, "find_library", lambda _n: None)

        assert mod._load_library() is None


class _FakeLib:
    """Stands in for libairspyhf. Records what the client asked for."""

    def __init__(self, *, open_result: int = 0, streaming: int = 1) -> None:
        self.calls: list[tuple] = []
        self._open_result = open_result
        self._streaming = streaming

    def airspyhf_open(self, device_pp):
        self.calls.append(("open",))
        if self._open_result == 0:
            # The real library writes a device handle through the
            # pointer. A fake that returns success without one would let
            # a null-handle bug pass.
            device_pp._obj.value = 0xA1B2C3D4
        return self._open_result

    def airspyhf_close(self, device):
        self.calls.append(("close",))
        return 0

    def airspyhf_set_samplerate(self, device, rate):
        self.calls.append(("samplerate", rate))
        return 0

    def airspyhf_set_freq(self, device, hz):
        self.calls.append(("freq", hz))
        return 0

    def airspyhf_set_hf_agc(self, device, flag):
        self.calls.append(("agc", flag))
        return 0

    def airspyhf_set_hf_att(self, device, index):
        self.calls.append(("att", index))
        return 0

    def airspyhf_start(self, device, cb, ctx):
        self.calls.append(("start",))
        return 0

    def airspyhf_stop(self, device):
        self.calls.append(("stop",))
        return 0

    def airspyhf_is_streaming(self, device):
        return self._streaming

    def airspyhf_get_samplerates(self, device, buf, count):
        if count == 0:
            buf[0] = 1
        else:
            buf[0] = 768_000
        return 0


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> AirspyHFClient:
    from sstv_core.sdr import airspyhf as mod

    lib = _FakeLib()
    monkeypatch.setattr(mod, "_load_library", lambda: lib)
    made = AirspyHFClient()
    made._test_lib = lib  # type: ignore[attr-defined]
    return made


class TestItSatisfiesTheClientProtocol:
    """`SpyServerSource` consumes `_Client`. A local radio has to present
    the same surface or every consumer needs a second code path.
    """

    @pytest.mark.parametrize(
        "name",
        [
            "connect",
            "tune",
            "start_streaming",
            "stop_streaming",
            "close",
            "sample_rate",
            "dropped_frames",
            "stream_error",
            "device_info",
        ],
    )
    def test_the_surface_matches(self, name: str, client: AirspyHFClient) -> None:
        assert hasattr(client, name)

    def test_it_is_accepted_where_a_spyserver_client_goes(
        self, client: AirspyHFClient
    ) -> None:
        """The point of the protocol: SpyServerSource must take it."""
        from sstv_core.sdr.source import SpyServerSource

        client.connect()
        source = SpyServerSource(client=client)  # type: ignore[call-arg]

        assert source is not None


class TestTuningAndGain:
    def test_connect_opens_the_device(self, client: AirspyHFClient) -> None:
        client.connect()
        assert ("open",) in client._test_lib.calls  # type: ignore[attr-defined]

    def test_tune_reaches_the_radio(self, client: AirspyHFClient) -> None:
        client.connect()
        client.tune(14_230_000)

        assert ("freq", 14_230_000) in client._test_lib.calls  # type: ignore[attr-defined]

    def test_tuning_before_connect_is_an_error_not_a_crash(self) -> None:
        with pytest.raises(AirspyHFError):
            AirspyHFClient().tune(14_230_000)

    def test_gain_maps_to_attenuation_not_amplification(
        self, client: AirspyHFClient
    ) -> None:
        """The HF+ has no gain control -- it has an attenuator and an AGC.

        `--gain 8` meaning "as sensitive as possible" therefore means zero
        attenuation, which is the opposite number. Getting this backwards
        would quietly deafen the radio at the setting that asks for the
        most sensitivity, which is exactly the shape of the digital-gain
        defect fixed on 2026-08-19.
        """
        client.connect()
        client.start_streaming(lambda iq: None, gain=8)

        att = [c for c in client._test_lib.calls if c[0] == "att"]  # type: ignore[attr-defined]
        assert att, "no attenuator setting was sent"
        assert att[-1][1] == 0, "max gain must mean zero attenuation"

    def test_low_gain_attenuates(self, client: AirspyHFClient) -> None:
        client.connect()
        client.start_streaming(lambda iq: None, gain=0)

        att = [c for c in client._test_lib.calls if c[0] == "att"]  # type: ignore[attr-defined]
        assert att[-1][1] > 0, "gain 0 must attenuate"


class TestSamples:
    def test_interleaved_floats_become_complex_iq(self) -> None:
        """Libairspyhf hands over airspyhf_complex_float_t, which is a
        bare pair of floats -- the demodulator wants complex64.
        """
        from sstv_core.sdr.airspyhf import interleaved_to_complex

        raw = np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float32)
        iq = interleaved_to_complex(raw)

        assert iq.dtype == np.complex64
        assert len(iq) == 2
        assert iq[0] == pytest.approx(1.0 + 2.0j)
        assert iq[1] == pytest.approx(3.0 + 4.0j)

    def test_an_odd_tail_is_dropped_rather_than_misread(self) -> None:
        """Half a sample is not a sample. Pairing it with the next block's
        first float would rotate every subsequent I and Q.
        """
        from sstv_core.sdr.airspyhf import interleaved_to_complex

        raw = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        assert len(interleaved_to_complex(raw)) == 1

    def test_empty_input_is_empty_output(self) -> None:
        from sstv_core.sdr.airspyhf import interleaved_to_complex

        assert len(interleaved_to_complex(np.array([], dtype=np.float32))) == 0
