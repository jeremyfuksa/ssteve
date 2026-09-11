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


async def test_saved_squelch_and_afc_reach_the_engine(tmp_path) -> None:
    """Every decode setting /config saves is the one the decode uses.

    Until 2026-09-11 the engine asked config for "auto_squelch" while
    /config stored "audio.auto_squelch", so the lookup missed and the
    hardcoded default won: squelch saved off still ran on at -40 dB, and
    AFC saved off still ran on. Saving the non-default value of each is
    the only way a test can tell a read from a fallback.
    """
    # The app first: importing the routes module alone is circular.
    import sstv_core.api.main  # noqa: F401
    from sstv_core.api.routes.config import _FIELD_TO_MANAGER_KEY
    from sstv_core.config.manager import ConfigManager
    from sstv_core.database.models import init_database

    _, session_factory = init_database(db_path=tmp_path / "keys.db")
    saved = {
        "auto_afc": False,
        "afc_range_hz": 200,
        "auto_squelch": False,
        "squelch_threshold_db": -60.0,
        "slant_auto_correct": True,
    }
    with session_factory() as session:
        ConfigManager(session).update(
            {_FIELD_TO_MANAGER_KEY[name]: value for name, value in saved.items()}
        )

    engine = await DSPManager(db_session_factory=session_factory)._read_decode_config()

    assert engine["auto_afc"] is False
    assert engine["afc_range_hz"] == 200
    assert engine["auto_squelch"] is False
    assert engine["squelch_threshold_db"] == -60.0
    assert engine["decoder.slant_auto_correct"] is True
