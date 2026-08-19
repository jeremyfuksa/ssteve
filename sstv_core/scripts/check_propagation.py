#!/usr/bin/env python3
"""Ask whether the band should be open before blaming the radio.

Twice now a quiet receiver has been diagnosed as a hardware fault when the
real cause was elsewhere -- once a closed band after dark, once a digital-gain
defect in our own SpyServer client. Both times the falsifying control was run
through the same suspect path, so it confirmed the theory instead of breaking
it.

Space weather is an independent axis. If the ionosphere says 20m is open and
we hear nothing, the fault is ours. If the band is closed, silence is the
correct answer and there is nothing to fix.

    uv run python scripts/check_propagation.py
    uv run python scripts/check_propagation.py --band 20m --json

Data: N0NBH's solar XML (hamqsl.com), with NOAA SWPC as a fallback for the
raw indices. Neither needs a key.
"""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx

HAMQSL = "https://www.hamqsl.com/solarxml.php"
SWPC_KP = "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"
SWPC_FLUX = "https://services.swpc.noaa.gov/json/f107_cm_flux.json"

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


def _fetch_hamqsl(timeout: float) -> dict | None:
    try:
        r = httpx.get(HAMQSL, timeout=timeout)
        r.raise_for_status()
        # A solar feed is a few KB. Cap it rather than hand an unbounded
        # remote document to the XML parser.
        if len(r.text) > 256_000:
            return None
        root = ET.fromstring(r.text)  # noqa: S314 - size-capped, non-secret feed
    except (httpx.HTTPError, ET.ParseError):
        return None

    data = root.find("solardata")
    if data is None:
        return None

    def text(tag: str) -> str:
        el = data.find(tag)
        return (el.text or "").strip() if el is not None else ""

    bands: dict[str, dict[str, str]] = {}
    conds = data.find("calculatedconditions")
    if conds is not None:
        for band in conds.findall("band"):
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
        "aurora": text("aurora"),
        "bands": bands,
    }


def _fetch_swpc(timeout: float) -> dict:
    """NOAA fallback for the raw indices when hamqsl is unreachable.

    Failures are reported rather than swallowed: a check that silently
    degrades to "no data" is how a quiet band gets mistaken for a fault.
    """
    out: dict[str, str] = {}
    try:
        r = httpx.get(SWPC_KP, timeout=timeout)
        r.raise_for_status()
        rows = r.json()
        if rows:
            out["k_index"] = str(rows[-1].get("kp_index", ""))
            out["k_time"] = str(rows[-1].get("time_tag", ""))
    except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
        out["k_error"] = f"{type(exc).__name__}: {exc}"
    try:
        r = httpx.get(SWPC_FLUX, timeout=timeout)
        r.raise_for_status()
        rows = r.json()
        if rows:
            out["solar_flux"] = str(int(float(rows[0].get("flux", 0))))
    except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
        out["flux_error"] = f"{type(exc).__name__}: {exc}"
    return out


def _verdict(k_index: str, condition: str) -> tuple[str, str]:
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--band", default="20m", help="amateur band (default: 20m)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--timeout", type=float, default=15.0)
    args = ap.parse_args()

    ham = _fetch_hamqsl(args.timeout)
    swpc = _fetch_swpc(args.timeout)

    if ham is None and not swpc:
        msg = "I couldn't reach either space weather source."
        if args.json:
            print(json.dumps({"error": msg, "suggested_action": "Check the network."}))
        else:
            print(msg)
        return 1

    ham = ham or {}
    group = BAND_GROUP.get(args.band.lower(), "")
    hour = datetime.now(timezone.utc).astimezone().hour
    when = "day" if 6 <= hour < 18 else "night"
    condition = ham.get("bands", {}).get(group, {}).get(when, "")

    k_index = ham.get("k_index") or swpc.get("k_index", "")
    flux = ham.get("solar_flux") or swpc.get("solar_flux", "")
    state, explanation = _verdict(k_index, condition)

    payload = {
        "band": args.band,
        "band_group": group,
        "time_of_day": when,
        "condition": condition,
        "state": state,
        "explanation": explanation,
        "solar_flux": flux,
        "k_index": k_index,
        "a_index": ham.get("a_index", ""),
        "sunspots": ham.get("sunspots", ""),
        "xray": ham.get("xray", ""),
        "updated": ham.get("updated", ""),
        "wwv_frequencies_hz": list(WWV_HZ),
    }

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print(f"Propagation for {args.band} ({group}, {when}) -- {ham.get('updated','')}")
    print(f"  SFI {flux}   K {k_index}   A {ham.get('a_index','')}   "
          f"SN {ham.get('sunspots','')}   X-ray {ham.get('xray','')}")
    print(f"  condition: {condition or 'unknown'}")
    print()
    print(f"  {state}: {explanation}")
    print()
    print("  Cross-check with WWV before blaming hardware:")
    for hz, label in WWV_HZ.items():
        print(f"    {label:<7} decode --spyserver <host> --frequency {hz} --gain 8 --timeout 15")
    print("  Losing the high frequencies first is the MUF dropping, not a fault.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
