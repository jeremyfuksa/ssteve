"""What a propagation verdict must never do.

Twice a healthy receiver was called broken because a control agreed with the
wrong theory. These tests pin the two properties that make this module a
usable control: it never silently reports "fine" when it knows nothing, and
it never converts one geomagnetic index into another behind the operator's
back.
"""

from __future__ import annotations

import pytest

from sstv_core.propagation.space_weather import (
    SpaceWeatherUnavailableError,
    band_group,
    build_report,
    verdict,
)


class TestVerdict:
    """The sentence a fault report actually needs."""

    def test_storm_wins_over_a_good_condition_string(self):
        """K>=5 is a storm even when the feed still says Good.

        The band table and the K index update on different cadences. If they
        disagree, the storm is the safe reading: silence during a storm is
        expected and proves nothing about the radio.
        """
        state, _ = verdict(k_index="6", condition="Good")
        assert state == "STORM"

    def test_poor_conditions_are_closed(self):
        state, explanation = verdict(k_index="2", condition="Poor")
        assert state == "CLOSED"
        assert "do not diagnose hardware" in explanation.lower()

    def test_open_points_the_finger_at_the_receive_chain(self):
        """The whole deliverable: open band + silence means look at our code."""
        state, explanation = verdict(k_index="2", condition="Good")
        assert state == "OPEN"
        assert "receive chain" in explanation

    def test_missing_condition_is_unknown_not_open(self):
        """No data must never read as good news."""
        state, _ = verdict(k_index="2", condition="")
        assert state == "UNKNOWN"

    def test_unparseable_k_does_not_crash_or_imply_calm(self):
        state, _ = verdict(k_index="", condition="")
        assert state == "UNKNOWN"


class TestBandGroup:
    def test_20m_maps_to_its_hamqsl_group(self):
        assert band_group("20m") == "30m-20m"

    def test_case_insensitive(self):
        assert band_group("20M") == "30m-20m"

    def test_unknown_band_returns_empty(self):
        assert band_group("6m") == ""


class TestBuildReport:
    """Assembly from already-fetched payloads. No network in these tests."""

    def test_prefers_hamqsl_indices_over_swpc_fallback(self):
        report = build_report(
            band="20m",
            when="day",
            ham={"k_index": "2", "solar_flux": "125", "bands": {"30m-20m": {"day": "Good"}}},
            swpc={"k_index": "9", "solar_flux": "999"},
        )
        assert report.k_index == "2"
        assert report.solar_flux == "125"
        assert report.state == "OPEN"

    def test_falls_back_to_swpc_when_hamqsl_is_missing(self):
        report = build_report(band="20m", when="day", ham={}, swpc={"k_index": "1", "solar_flux": "120"})
        assert report.k_index == "1"
        assert report.solar_flux == "120"

    def test_both_sources_empty_raises_rather_than_reporting_nothing(self):
        """A check that degrades to "no data" is how a quiet band became a
        hardware verdict. Refuse to produce a report instead."""
        with pytest.raises(SpaceWeatherUnavailableError):
            build_report(band="20m", when="day", ham={}, swpc={})

    def test_source_errors_are_carried_not_swallowed(self):
        report = build_report(
            band="20m",
            when="day",
            ham={},
            swpc={"k_index": "3", "solar_flux": "120", "k_error": "HTTPError: timeout"},
        )
        assert "HTTPError: timeout" in report.source_errors

    def test_night_selects_the_night_condition(self):
        report = build_report(
            band="20m",
            when="night",
            ham={"k_index": "2", "bands": {"30m-20m": {"day": "Good", "night": "Poor"}}},
            swpc={},
        )
        assert report.condition == "Poor"
        assert report.state == "CLOSED"
