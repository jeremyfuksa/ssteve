"""`decoder.slant_auto_correct` has to reach the decoder.

The setting existed in ConfigManager and over the API, defaulted to True, and
was read by nothing: turning it on or off changed no behaviour anywhere. It
also contradicted the engine, where RXManager defaults slant correction off
because it measured worse -- so the config advertised a feature that was both
unwired and pointing the wrong way.
"""

from __future__ import annotations

import inspect

from sstv_core.api.dsp_manager import DSPManager
from sstv_core.api.models import Configuration
from sstv_core.config.manager import DecoderSettings
from sstv_core.decode.rx_manager import RXManager


def test_config_default_matches_the_engine_default() -> None:
    """The stored default cannot disagree with what the decoder does.

    Both are off. Measured on the reference corpus, Hough correction lowered
    SSIM on 5 of 9 files, so on is the wrong default -- and a config that says
    True while the engine does False is worse than either.
    """
    engine_default = inspect.signature(RXManager.__init__).parameters[
        "slant_correction"
    ].default

    assert DecoderSettings().slant_auto_correct is False
    assert engine_default is False


def test_api_default_matches_the_stored_default() -> None:
    """What the API reports and what the config stores agree."""
    field = Configuration.model_fields["slant_auto_correct"]

    assert field.default is DecoderSettings().slant_auto_correct


def test_decode_config_carries_the_slant_setting() -> None:
    """The read that feeds RXManager includes the slant key.

    Without it the setting is inert no matter what an operator does with it.
    """
    source = inspect.getsource(DSPManager._read_decode_config)

    assert "decoder.slant_auto_correct" in source


def test_rx_manager_is_constructed_with_the_setting() -> None:
    """The value read from config is passed to the decoder, not dropped."""
    source = inspect.getsource(DSPManager)

    assert "slant_correction=bool(decode_config[" in source
