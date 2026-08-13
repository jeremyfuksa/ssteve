"""SpyServer settings live in the JSON tier -- no migration."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sstv_core.config.manager import AdvancedSettings, SpyServerSettings


def test_defaults_are_sane():
    s = SpyServerSettings()
    assert s.port == 5555
    assert s.stall_timeout_sec == 5.0
    assert s.gain == 0


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
