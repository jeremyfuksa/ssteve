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

The logic lives in `sstv_core.propagation` so the API serves the same verdict
this prints. Data: N0NBH's solar XML (hamqsl.com), with NOAA SWPC as a
fallback for the raw indices. Neither needs a key.
"""

from __future__ import annotations

import argparse
import json

from sstv_core.propagation import SpaceWeatherUnavailableError, fetch_report
from sstv_core.propagation.space_weather import WWV_HZ


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--band", default="20m", help="amateur band (default: 20m)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--timeout", type=float, default=15.0)
    args = ap.parse_args()

    try:
        report = fetch_report(band=args.band, timeout=args.timeout)
    except SpaceWeatherUnavailableError as exc:
        msg = str(exc)
        if args.json:
            print(json.dumps({"error": msg, "suggested_action": "Check the network."}))
        else:
            print(msg)
        return 1

    if args.json:
        payload = {
            "band": report.band,
            "band_group": report.band_group,
            "time_of_day": report.time_of_day,
            "condition": report.condition,
            "state": report.state,
            "explanation": report.explanation,
            "solar_flux": report.solar_flux,
            "k_index": report.k_index,
            "a_index": report.a_index,
            "sunspots": report.sunspots,
            "xray": report.xray,
            "updated": report.updated,
            "source_errors": report.source_errors,
            "wwv_frequencies_hz": report.wwv_frequencies_hz,
        }
        print(json.dumps(payload, indent=2))
        return 0

    print(
        f"Propagation for {report.band} ({report.band_group}, "
        f"{report.time_of_day}) -- {report.updated}"
    )
    print(
        f"  SFI {report.solar_flux}   K {report.k_index}   A {report.a_index}   "
        f"SN {report.sunspots}   X-ray {report.xray}"
    )
    print(f"  condition: {report.condition or 'unknown'}")
    print()
    print(f"  {report.state}: {report.explanation}")
    print()
    if report.source_errors:
        for err in report.source_errors:
            print(f"  source error: {err}")
        print()
    print("  Cross-check with WWV before blaming hardware:")
    for hz, label in WWV_HZ.items():
        print(f"    {label:<7} decode --spyserver <host> --frequency {hz} --gain 8 --timeout 15")
    print("  Losing the high frequencies first is the MUF dropping, not a fault.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
