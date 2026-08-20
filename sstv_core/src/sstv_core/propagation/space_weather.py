"""Read current space weather and say whether the band should carry signal.

The verdict sentence is the deliverable. Everything else here exists to
produce it honestly, which mostly means refusing to produce it at all when
the sources are unreachable: a check that silently degrades to "no data" is
how a quiet band gets mistaken for a fault.

Fetching is deliberately separated from assembly. `build_report` is pure, so
the rules that matter -- storm beats a stale Good, missing data is UNKNOWN
rather than OPEN -- are testable without a network or a pile of mocks.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

HAMQSL = "https://www.hamqsl.com/solarxml.php"
SWPC_KP = "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"
SWPC_FLUX = "https://services.swpc.noaa.gov/json/f107_cm_flux.json"

#: A solar feed is a few KB. Cap it rather than hand an unbounded remote
#: document to the XML parser.
_MAX_FEED_BYTES = 256_000

#: Which hamqsl band group covers each amateur band we tune.
BAND_GROUP = {
    "80m": "80m-40m",
    "40m": "80m-40m",
    "30m": "30m-20m",
    "20m": "30m-20m",
    "17m": "17m-15m",
    "15m": "17m-15m",
    "12m": "12m-10m",
    "10m": "12m-10m",
}

#: WWV runs continuously on these. Which ones you can hear is itself a
#: propagation measurement: losing 15 MHz while 5 MHz holds means the MUF
#: dropped, not that the receiver broke.
WWV_HZ = {5_000_000: "5 MHz", 10_000_000: "10 MHz", 15_000_000: "15 MHz"}


class SpaceWeatherUnavailableError(RuntimeError):
    """Neither source answered, so there is no verdict to give.

    Raised rather than returning a blank report: an empty propagation panel
    reads as "nothing to report", which is the opposite of the truth.
    """


@dataclass(frozen=True)
class PropagationReport:
    """One band, one moment, one sentence."""

    band: str
    band_group: str
    time_of_day: str
    condition: str
    state: str
    explanation: str
    solar_flux: str
    k_index: str
    a_index: str = ""
    sunspots: str = ""
    xray: str = ""
    updated: str = ""
    #: Source failures worth surfacing even though a report was still built.
    source_errors: list[str] = field(default_factory=list)

    @property
    def wwv_frequencies_hz(self) -> list[int]:
        return list(WWV_HZ)


def band_group(band: str) -> str:
    """Return the hamqsl group covering `band`, or "" if we do not tune it."""
    return BAND_GROUP.get(band.lower(), "")


def time_of_day(now: datetime | None = None) -> str:
    """Day or night in local time, matching hamqsl's two condition columns."""
    moment = now or datetime.now(timezone.utc).astimezone()
    return "day" if 6 <= moment.hour < 18 else "night"


def verdict(k_index: str, condition: str) -> tuple[str, str]:
    """Turn the numbers into the sentence a fault report actually needs."""
    try:
        k = float(k_index)
    except (TypeError, ValueError):
        k = -1.0

    if k >= 5:
        return (
            "STORM",
            f"K={k:.0f} is a geomagnetic storm. HF will be degraded or blacked "
            "out; a quiet band is expected and proves nothing about the radio.",
        )
    if condition.lower() == "poor":
        return (
            "CLOSED",
            f"Conditions read {condition}. Hearing nothing is the correct "
            "answer right now -- do not diagnose hardware from it.",
        )
    if condition.lower() in {"good", "fair"}:
        return (
            "OPEN",
            f"Conditions read {condition} with K={k:.0f}. The band should carry "
            "signal, so silence points at the receive chain, not propagation.",
        )
    return ("UNKNOWN", "No band condition reported; treat silence as inconclusive.")


def build_report(
    band: str,
    when: str,
    ham: dict,
    swpc: dict,
) -> PropagationReport:
    """Assemble a report from already-fetched payloads.

    hamqsl wins where both have a value: it carries the band condition table,
    so taking its indices too keeps the verdict internally consistent rather
    than mixing one source's K with another's conditions.
    """
    k_index = ham.get("k_index") or swpc.get("k_index", "")
    flux = ham.get("solar_flux") or swpc.get("solar_flux", "")
    if not k_index and not flux:
        raise SpaceWeatherUnavailableError(
            "I couldn't reach either space weather source."
        )

    group = band_group(band)
    condition = ham.get("bands", {}).get(group, {}).get(when, "")
    state, explanation = verdict(k_index, condition)

    errors = [v for key, v in swpc.items() if key.endswith("_error")]

    return PropagationReport(
        band=band,
        band_group=group,
        time_of_day=when,
        condition=condition,
        state=state,
        explanation=explanation,
        solar_flux=flux,
        k_index=k_index,
        a_index=ham.get("a_index", ""),
        sunspots=ham.get("sunspots", ""),
        xray=ham.get("xray", ""),
        updated=ham.get("updated", ""),
        source_errors=errors,
    )


def fetch_hamqsl(timeout: float = 15.0) -> dict | None:
    """N0NBH's solar XML, or None if it did not answer usably."""
    try:
        response = httpx.get(HAMQSL, timeout=timeout)
        response.raise_for_status()
        if len(response.text) > _MAX_FEED_BYTES:
            return None
        root = ET.fromstring(response.text)  # noqa: S314 - size-capped, non-secret feed
    except (httpx.HTTPError, ET.ParseError):
        return None

    data = root.find("solardata")
    if data is None:
        return None

    def text(tag: str) -> str:
        element = data.find(tag)
        return (element.text or "").strip() if element is not None else ""

    bands: dict[str, dict[str, str]] = {}
    conditions = data.find("calculatedconditions")
    if conditions is not None:
        for band in conditions.findall("band"):
            name = band.get("name") or ""
            when = band.get("time") or ""
            bands.setdefault(name, {})[when] = (band.text or "").strip()

    return {
        "updated": text("updated"),
        "solar_flux": text("solarflux"),
        "a_index": text("aindex"),
        "k_index": text("kindex"),
        "sunspots": text("sunspots"),
        "xray": text("xray"),
        "bands": bands,
    }


def fetch_swpc(timeout: float = 15.0) -> dict:
    """NOAA fallback for the raw indices.

    Failures land in the payload as `*_error` keys rather than being
    swallowed, so a partial answer is visibly partial.
    """
    out: dict[str, str] = {}
    try:
        response = httpx.get(SWPC_KP, timeout=timeout)
        response.raise_for_status()
        rows = response.json()
        if rows:
            out["k_index"] = str(rows[-1].get("kp_index", ""))
            out["k_time"] = str(rows[-1].get("time_tag", ""))
    except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
        out["k_error"] = f"{type(exc).__name__}: {exc}"
    try:
        response = httpx.get(SWPC_FLUX, timeout=timeout)
        response.raise_for_status()
        rows = response.json()
        if rows:
            out["solar_flux"] = str(int(float(rows[0].get("flux", 0))))
    except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
        out["flux_error"] = f"{type(exc).__name__}: {exc}"
    return out


def fetch_report(band: str = "20m", timeout: float = 15.0) -> PropagationReport:
    """Fetch both sources and build the report. Raises if neither answers."""
    ham = fetch_hamqsl(timeout) or {}
    swpc = fetch_swpc(timeout)
    return build_report(band=band, when=time_of_day(), ham=ham, swpc=swpc)
