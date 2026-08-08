"""One image directory: configured, watched, and written.

Known Gap 7: with image_save_directory unset (old default "") the watcher
never started, while the decode pipeline hardcoded ~/sstv_images -- so
decoded images could land outside the watched library.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sstv_core.api.dsp_manager import DSPManager
from sstv_core.config.manager import ConfigManager
from sstv_core.database.models import Base


def _config_manager(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/config.db")
    Base.metadata.create_all(engine)
    return ConfigManager(sessionmaker(bind=engine)())


class TestDefaultDirectory:
    def test_default_is_the_decode_save_directory(self, tmp_path):
        config = _config_manager(tmp_path)
        assert config.get("image_save_directory") == str(Path.home() / ".ssteve" / "images")

    def test_empty_string_remains_the_explicit_opt_out(self, tmp_path):
        config = _config_manager(tmp_path)
        config.update({"image_save_directory": ""})
        assert config.get("image_save_directory") == ""


class TestDecoderUsesConfiguredDirectory:
    def test_dsp_manager_reads_configured_save_directory(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path}/app.db")
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine)
        custom = str(tmp_path / "library")
        ConfigManager(factory()).update({"image_save_directory": custom})

        manager = DSPManager(db_session_factory=factory)
        decode_config = asyncio.run(manager._read_decode_config())
        assert decode_config["image_save_directory"] == custom

    def test_no_database_falls_back_to_app_data_home(self):
        manager = DSPManager()
        decode_config = asyncio.run(manager._read_decode_config())
        assert decode_config["image_save_directory"] == str(
            Path.home() / ".ssteve" / "images"
        )
