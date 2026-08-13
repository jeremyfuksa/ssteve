"""SpyServer settings live in the JSON tier -- no migration."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sstv_core.config.manager import AdvancedSettings, SpyServerSettings


def test_defaults_are_sane():
    s = SpyServerSettings()
    assert s.port == 5555
    assert s.stall_timeout_sec == 5.0
    # None, not 0: 0 is a legal gain AND a deaf one on the Airspy HF+
    # (issue #90), so "unset" needs its own value. The source derives a
    # gain from the device's maximum_gain_index when nobody chose.
    assert s.gain is None


def test_gain_zero_is_still_storable_and_distinct_from_unset():
    """An operator who really wants 0 must be able to say so."""
    assert SpyServerSettings(gain=0).gain == 0


def test_registered_on_advanced_settings():
    assert isinstance(AdvancedSettings().spyserver, SpyServerSettings)


def test_port_is_range_checked():
    with pytest.raises(ValidationError):
        SpyServerSettings(port=70000)


def test_frequency_is_uint32_bounded():
    """The protocol carries frequency as a uint32 in Hz."""
    with pytest.raises(ValidationError):
        SpyServerSettings(frequency_hz=5_000_000_000)


def test_round_trips_through_advanced_settings_json():
    settings = AdvancedSettings(
        spyserver=SpyServerSettings(host="sdr.example.test", frequency_hz=14_230_000)
    )
    restored = AdvancedSettings.model_validate(settings.model_dump())
    assert restored.spyserver.host == "sdr.example.test"
    assert restored.spyserver.frequency_hz == 14_230_000
