"""Smart-features tests against real DSP, real config DB, real templates.

The 2026-08-07 audit found this layer was largely fiction: the mode
detector's timing table held per-color-channel durations (so Scottie and
Martin could never be detected), Smart Reply shipped zero loadable
templates, applying a detected serial device profile always failed config
validation, and field population discarded even explicit overrides. There
was no tests/smart_features/ directory at all -- every touch point was
mocked.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sstv_core.config.manager import ConfigManager
from sstv_core.database.models import Base, SSTVImage
from sstv_core.smart_features.device_detector import (
    DEVICE_PROFILES,
    detect_hardware_device,
    get_recommended_settings,
)
from sstv_core.smart_features.field_populator import populate_smart_reply_fields
from sstv_core.smart_features.mode_detector import (
    detect_mode_from_sync_timing,
    get_top_mode_candidates,
)
from sstv_core.smart_features.template_engine import TemplateEngine

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates" / "smart_reply"


def synth_sync_audio(line_period_ms: float, sync_ms: float = 9.0,
                     duration_sec: float = 10.0, sample_rate: int = 48000) -> np.ndarray:
    """Textbook SSTV timing: a 1200 Hz sync pulse every line period, mid-grey
    video (1900 Hz) between."""
    n = int(duration_sec * sample_rate)
    t = np.arange(n) / sample_rate
    audio = 0.5 * np.sin(2 * np.pi * 1900.0 * t)
    period = int(line_period_ms * sample_rate / 1000)
    sync_len = int(sync_ms * sample_rate / 1000)
    for start in range(0, n - sync_len, period):
        ts = np.arange(sync_len) / sample_rate
        audio[start : start + sync_len] = 0.5 * np.sin(2 * np.pi * 1200.0 * ts)
    return audio.astype(np.float32)


class TestModeDetectionTimingTable:
    """The old table listed per-color-channel durations; a real Scottie S1
    measured ~428 ms and matched nothing."""

    @pytest.mark.parametrize(
        "mode, line_ms, sync_ms",
        [
            ("ScottieS1", 428.22, 9.0),
            ("MartinM1", 446.446, 4.862),
            ("Robot36", 150.0, 9.0),
        ],
    )
    def test_textbook_timing_detects_the_right_mode(self, mode, line_ms, sync_ms):
        audio = synth_sync_audio(line_ms, sync_ms)
        result = detect_mode_from_sync_timing(audio)
        assert result is not None, f"{mode}: detection returned None"
        assert result.mode == mode
        assert result.confidence >= 0.85

    def test_candidates_exist_even_when_primary_gate_rejects(self):
        """Fallback candidates are FOR the low-confidence case; they used to
        be computed only after the primary detection already succeeded."""
        # Slightly off-nominal timing: outside the strict confidence gate,
        # inside the candidate window.
        audio = synth_sync_audio(428.22 * 1.06)
        primary = detect_mode_from_sync_timing(audio)
        candidates = get_top_mode_candidates(audio)
        if primary is None:
            assert candidates, "no candidates exactly when fallbacks are needed"


class TestDeviceProfileApply:
    """get_recommended_settings output must be applyable to the real
    ConfigManager -- the old code put the serial port in an audio field and
    validation rejected every detected serial device."""

    @pytest.fixture
    def config_manager(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path}/config.db")
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        yield ConfigManager(session)
        session.close()

    def test_detected_digirig_settings_apply_cleanly(self, config_manager):
        ports = [{"port": "/dev/ttyUSB0", "description": "CP2102N",
                  "manufacturer": "Silicon Labs", "vid": 0x10C4, "pid": 0xEA60}]
        profile = detect_hardware_device(ports)
        assert profile is not None and profile.name == "Digirig Mobile"
        assert profile.recommended_serial_port == "/dev/ttyUSB0"
        assert profile.recommended_input_device is None

        settings = get_recommended_settings(profile)
        config_manager.update(settings)  # must not raise
        assert config_manager.get("ptt_serial_port") == "/dev/ttyUSB0"
        assert config_manager.get("ptt_method") == "serial"

    def test_every_serial_profile_applies_cleanly(self, config_manager):
        for profile in DEVICE_PROFILES:
            if profile.ptt_method != "serial":
                continue
            profile.recommended_serial_port = "/dev/ttyUSB1"
            config_manager.update(get_recommended_settings(profile))
            profile.recommended_serial_port = None


class TestFieldPopulator:
    @pytest.fixture
    def db_session(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path}/images.db")
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        yield session
        session.close()

    def _image(self, session, **kwargs) -> SSTVImage:
        values = {
            "filename": "rx.png",
            "filepath": "/tmp/rx.png",
            "mode": "ScottieS1",
            "callsign": "K0ABC",
            "timestamp": datetime(2026, 8, 7, 12, 0),
            "is_received": True,
        }
        values.update(kwargs)
        image = SSTVImage(**values)
        session.add(image)
        session.commit()
        return image

    def test_frequency_override_wins(self, db_session):
        image = self._image(db_session, frequency_hz=14230000.0)
        fields = populate_smart_reply_fields(
            db_session, image.id, overrides={"frequency_mhz": 7.171}
        )
        assert fields["frequency_mhz"] == 7.171

    def test_frequency_from_image_metadata(self, db_session):
        image = self._image(db_session, frequency_hz=14230000.0)
        fields = populate_smart_reply_fields(db_session, image.id)
        assert fields["frequency_mhz"] == pytest.approx(14.23)

    def test_snr_reads_the_db_column_not_quality_score(self, db_session):
        image = self._image(db_session, rx_snr_db=18.5, rx_quality_score=0.95)
        fields = populate_smart_reply_fields(db_session, image.id)
        # Display formatting rounds to whole dB; the defect was reading
        # rx_quality_score (0-1), which formatted to 0 dB.
        assert fields["snr_db"] == 18


class TestTemplateEngine:
    def test_all_three_bundled_templates_load(self):
        engine = TemplateEngine(TEMPLATES_DIR)
        names = {t.name for t in engine.list_templates()}
        assert names == {"QSL Card", "Monitor Frame", "Minimal Badge"}

    def test_qsl_card_renders_to_a_real_image(self, tmp_path):
        engine = TemplateEngine(TEMPLATES_DIR)
        output = engine.render_template(
            "qsl_card",
            {
                "callsign_received": "K0ABC",
                "callsign_operator": "W1XYZ",
                "frequency_mhz": 14.230,
                "timestamp_utc": datetime(2026, 8, 7, 12, 0),
                "snr_db": 18.5,
                "mode": "ScottieS1",
            },
            output_path=str(tmp_path / "reply.png"),
        )
        from PIL import Image

        with Image.open(output) as rendered:
            assert rendered.size == (320, 256)
