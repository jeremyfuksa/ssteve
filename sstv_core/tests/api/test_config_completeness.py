"""Every stored setting must be reachable over /config.

Before 2026-08-09 the route hand-wrote two mappings -- an `if key in values`
chain for writes, a hand-built Configuration(...) for reads -- so adding a
setting meant editing both in opposite directions. Nine AccessibilitySettings
fields were never added to either, including the stereo_guidance_enabled that
PR #44 shipped: the feature worked and no client could switch it on (#60).

The route is now one table consumed both ways. This file is the guard that
keeps it complete: the enumeration test fails when a new AdvancedSettings
leaf is added without a mapping, which is the failure mode that produced the
original gap.
"""

from __future__ import annotations

import pytest

import sstv_core.api.main  # noqa: F401  -- builds the app before routes import it
from sstv_core.api.models import Configuration
from sstv_core.api.routes.config import (
    _CONVERTED_FIELDS,
    _ENUM_CONVERTED_ON_READ,
    _FIELD_TO_MANAGER_KEY,
)
from sstv_core.config.manager import AdvancedSettings

# Sections of AdvancedSettings that are deliberately not operator-facing.
_NOT_EXPOSED = {
    # ExperimentalSettings: ai_captions is deferred by design (PRODUCT.md
    # §Scope), and the other two have no UI contract yet. Listing them here
    # rather than silently skipping keeps the omission a decision.
    "experimental",
}


def _advanced_leaf_keys() -> set[str]:
    """Every 'section.field' leaf in the AdvancedSettings tree."""
    leaves: set[str] = set()
    for section_name, section_field in AdvancedSettings.model_fields.items():
        if section_name in _NOT_EXPOSED:
            continue
        section_model = section_field.annotation
        for field_name in section_model.model_fields:
            leaves.add(f"{section_name}.{field_name}")
    return leaves


class TestMappingCompleteness:
    def test_every_advanced_setting_is_reachable(self):
        """The test that would have caught the accessibility gap."""
        mapped = set(_FIELD_TO_MANAGER_KEY.values())
        missing = sorted(_advanced_leaf_keys() - mapped)
        assert not missing, (
            "these settings are stored but unreachable over /config:\n  "
            + "\n  ".join(missing)
        )

    def test_accessibility_settings_are_all_mapped(self):
        """Called out separately: this is the block that was entirely absent."""
        accessibility = {
            key for key in _advanced_leaf_keys() if key.startswith("accessibility.")
        }
        assert accessibility, "no accessibility settings found -- did the tree move?"
        assert accessibility <= set(_FIELD_TO_MANAGER_KEY.values())

    def test_mvp_guidance_toggle_is_reachable(self):
        """frontend-contract §19.8 marks this MVP; PR #44 shipped the engine."""
        assert (
            _FIELD_TO_MANAGER_KEY.get("stereo_guidance_enabled")
            == "accessibility.stereo_guidance_enabled"
        )
        assert "stereo_guidance_enabled" in Configuration.model_fields

    def test_every_mapped_field_exists_on_the_model(self):
        """A table entry with no model field would be silently dead."""
        unknown = sorted(set(_FIELD_TO_MANAGER_KEY) - set(Configuration.model_fields))
        assert not unknown, f"table maps fields the model does not have: {unknown}"

    def test_every_model_field_is_mapped_or_deliberately_converted(self):
        """The reverse direction: no model field without a home."""
        accounted = set(_FIELD_TO_MANAGER_KEY) | _CONVERTED_FIELDS
        orphans = sorted(set(Configuration.model_fields) - accounted)
        assert not orphans, (
            "model fields that /config would silently ignore on write: "
            f"{orphans}"
        )

    def test_enum_read_conversions_are_also_in_the_write_table(self):
        """A field converted on read still has to be writable."""
        assert _ENUM_CONVERTED_ON_READ <= set(_FIELD_TO_MANAGER_KEY)

    def test_the_guard_can_actually_fail(self):
        """A completeness check that cannot fail proves nothing."""
        pruned = {
            k: v
            for k, v in _FIELD_TO_MANAGER_KEY.items()
            if v != "accessibility.stereo_guidance_enabled"
        }
        missing = _advanced_leaf_keys() - set(pruned.values())
        assert "accessibility.stereo_guidance_enabled" in missing


class TestRoundTrip:
    """A value written through /config must come back changed."""

    @pytest.fixture
    def manager(self, tmp_path):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from sstv_core.config import ConfigManager
        from sstv_core.database.models import Base

        engine = create_engine(f"sqlite:///{tmp_path}/config.db")
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        return ConfigManager(session)

    @pytest.mark.parametrize(
        "field,value",
        [
            ("stereo_guidance_enabled", True),
            ("pilot_tone_freq", 1500.0),
            ("lock_chime_enabled", False),
            ("json_logging_enabled", True),
            ("waterfall_fft_size", 2048),
            ("jpeg_quality", 60),
            ("enable_fskid_tx", False),
            ("slant_auto_correct", False),
            ("vis_detection_threshold", 0.7),
            ("buffer_size_samples", 2048),
            ("input_gain_override", 1.5),
            ("ptt_serial_baud", 19200),
        ],
    )
    def test_setting_survives_write_then_read(self, manager, field, value):
        from sstv_core.api.routes.config import _build_manager_updates, _build_response

        manager.update(_build_manager_updates({field: value}))
        assert getattr(_build_response(manager), field) == value

    def test_explicit_signal_beats_the_one_implied_by_ptt_method(self, manager):
        """serial_dtr implies DTR, but an explicit RTS in the same payload wins."""
        from sstv_core.api.routes.config import _build_manager_updates

        updates = _build_manager_updates(
            {"ptt_method": "serial_dtr", "ptt_serial_signal": "RTS"}
        )
        assert updates["ptt_method"] == "serial"
        assert updates["ptt_serial_signal"] == "RTS"

    def test_ptt_method_alone_still_implies_its_signal(self, manager):
        from sstv_core.api.routes.config import _build_manager_updates

        updates = _build_manager_updates({"ptt_method": "serial_dtr"})
        assert updates["ptt_serial_signal"] == "DTR"

    def test_null_input_gain_means_automatic_not_absent(self, manager):
        """None is a meaningful value here, not a missing one."""
        from sstv_core.api.routes.config import _build_response

        assert _build_response(manager).input_gain_override is None


class TestSchemaEndpoint:
    """GET /config/schema so clients stop hardcoding the field list."""

    def test_schema_describes_every_configuration_field(self):
        from fastapi.testclient import TestClient

        from sstv_core.api.main import app

        response = TestClient(app).get("/api/v1/config/schema")
        assert response.status_code == 200
        properties = response.json()["properties"]
        assert set(Configuration.model_fields) == set(properties), (
            "schema and model disagree about which fields exist"
        )

    def test_schema_carries_ranges_and_descriptions(self):
        """A hardcoded field list can't tell a client 0.0-2.0; this can."""
        from fastapi.testclient import TestClient

        from sstv_core.api.main import app

        properties = TestClient(app).get("/api/v1/config/schema").json()["properties"]
        assert properties["stereo_guidance_enabled"]["description"]
        # Nullable fields arrive as anyOf; the constraint lives on the branch.
        gain = properties["input_gain_override"]
        branches = gain.get("anyOf", [gain])
        numeric = [b for b in branches if b.get("type") == "number"]
        assert numeric and numeric[0]["maximum"] == 2.0
