#!/usr/bin/env python3
"""Colour bars for a band recording: sweep WWV, then say what was heard.

A recording that begins with WWV carries its own proof. Every frequency
below is captured through the same antenna, feedline, SDR and gain as the
band that follows, so a silent capture can still be told apart from a
broken one -- months later, with no radio to hand.

    uv run python scripts/calibrate_receiver.py --spyserver airspy.local:5555
    uv run python scripts/calibrate_receiver.py --spyserver 192.168.1.30:5555 \
        --json calibration.json

Reading the result. WWV runs the same transmitters at the same power all
day, so what changes between them is the ionosphere and our own receive
chain -- nothing else:

    high frequencies present, low weak    normal daytime absorption
    low present, high gone                MUF has dropped; 20m likely shut
    all present                           receiver healthy, band open
    all absent                            now, and only now, suspect the
                                          antenna, feedline or SDR

Measured against a live Airspy HF+ on 2026-08-19 at 21:04 GMT, gain 8:
2.5 MHz 30.9 dB, 5 MHz 13.1, 10 MHz 48.6, 15 MHz 40.9, and 14.230 MHz
(20m SSTV) 1.3 dB. The band was genuinely empty and the receiver was
fine -- which is exactly the pair of facts a bare recording cannot
distinguish and this ladder can.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

import numpy as np

from sstv_core.sdr.calibration import (
    CARRIER_SNR_DB,
    carrier_snr_db,
    has_carrier,
)
from sstv_core.sdr.spyserver.client import SpyServerClient, SpyServerError

#: The ladder, low to high. WWV runs 2.5/5/10/15/20/25 MHz; 20 and 25 read
#: as noise from Kansas City (3.8 dB measured at 20 MHz) and only lengthen
#: the sweep, so they are left out. 2.5 MHz is the floor -- it survives
#: when everything above it has closed, which makes it the honest "is
#: anything connected at all" check.
WWV_LADDER: tuple[tuple[str, int], ...] = (
    ("WWV 2.5", 2_500_000),
    ("WWV 5", 5_000_000),
    ("WWV 10", 10_000_000),
    ("WWV 15", 15_000_000),
)

#: Seconds per frequency. Measured by computing SNR from growing prefixes
#: of one 30 s capture: 10 MHz settled in 1 s, 2.5 in 2 s, a weak 5 MHz in
#: 3 s. Only 15 MHz kept climbing, and that was the signal itself fading
#: up rather than the measurement converging -- a longer dwell there
#: averages over fading instead of answering "was it working at 06:00".
#: 5 s is the slowest real convergence plus margin for a worse morning.
DWELL_SEC = 5.0

#: Discarded after each retune before measuring. The radio moves quickly,
#: but the first samples after a retune can still be from the old centre.
SETTLE_SEC = 1.0

#: Seconds allowed for the stream to establish before the sweep starts.
STREAM_START_SEC = 2.0


@dataclass
class Reading:
    """One frequency's answer."""

    name: str
    frequency_hz: int
    snr_db: float
    mean_abs_iq: float
    samples: int
    carrier: bool


def sweep(
    client: SpyServerClient,
    ladder: tuple[tuple[str, int], ...],
    gain: int,
    dwell_sec: float = DWELL_SEC,
) -> list[Reading]:
    """Tune each frequency in turn on one already-open stream.

    Retuning mid-stream really moves this radio -- proven on 2026-08-19 by
    running the ladder forward and then reversed: WWV 5 read 0.01212 and
    0.01218, 20m 0.01005 and 0.01053. Levels followed the frequency, not
    the position, so no reconnect is needed between steps.

    Note that ``client.client_sync`` cannot confirm any of this. This
    firmware sends a sync only when streaming starts (issue #89), so after
    that the field is frozen at the frequency we began on -- during that
    same sweep it reported 5 MHz at every step while the radio was plainly
    moving. Tuning is verified by the signal, never by the server's report.
    """
    lock = threading.Lock()
    buffered: list[np.ndarray] = []

    def on_iq(iq: np.ndarray) -> None:
        with lock:
            buffered.append(iq)

    def drain() -> list[np.ndarray]:
        with lock:
            taken, buffered[:] = list(buffered), []
        return taken

    client.tune(ladder[0][1])
    client.start_streaming(on_iq, gain=gain)
    time.sleep(STREAM_START_SEC)

    readings: list[Reading] = []
    try:
        for name, hz in ladder:
            client.tune(hz)
            drain()
            time.sleep(SETTLE_SEC)
            drain()  # anything from the old centre goes here
            time.sleep(dwell_sec)
            chunks = drain()
            if not chunks:
                readings.append(Reading(name, hz, float("nan"), 0.0, 0, False))
                continue
            iq = np.concatenate(chunks)
            snr = carrier_snr_db(iq, client.sample_rate)
            readings.append(
                Reading(
                    name=name,
                    frequency_hz=hz,
                    snr_db=round(snr, 1),
                    mean_abs_iq=round(float(np.abs(iq).mean()), 6),
                    samples=len(iq),
                    carrier=has_carrier(snr),
                )
            )
    finally:
        client.stop_streaming()

    return readings


def verdict(readings: list[Reading]) -> str:
    """One line an operator can act on, months later."""
    heard = [r for r in readings if r.carrier]
    if not heard:
        return (
            "NOTHING HEARD -- every WWV frequency was silent. This is the one "
            "result that points at the receive chain: check antenna, feedline "
            "and SDR."
        )
    if len(heard) == len(readings):
        return (
            "ALL CLEAR -- every WWV frequency carried a signal. The receiver "
            "was working; anything missing from the band recording was absent "
            "from the air, not from the radio."
        )
    highest = max(heard, key=lambda r: r.frequency_hz)
    lost = [r.name for r in readings if not r.carrier]
    return (
        f"PARTIAL -- heard up to {highest.name} "
        f"({highest.snr_db:.1f} dB); missing {', '.join(lost)}. Losing the "
        "high frequencies is the MUF dropping, not a fault."
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sweep WWV to prove the receive chain before a recording.",
    )
    parser.add_argument(
        "--spyserver",
        required=True,
        help="SpyServer as host:port, for example airspy.local:5555.",
    )
    parser.add_argument(
        "--gain",
        type=int,
        default=8,
        help="Must match the recording's gain, or this proves nothing about "
        "the path the recording actually used (default: 8).",
    )
    parser.add_argument(
        "--dwell",
        type=float,
        default=DWELL_SEC,
        help=f"Seconds per frequency (default: {DWELL_SEC}).",
    )
    parser.add_argument(
        "--json",
        metavar="PATH",
        help="Also write the readings here, as a sidecar for the recording.",
    )
    args = parser.parse_args()

    host, _, port = args.spyserver.partition(":")
    client = SpyServerClient(host, int(port or 5555))

    started = datetime.now(timezone.utc)
    try:
        client.connect()
        readings = sweep(client, WWV_LADDER, gain=args.gain, dwell_sec=args.dwell)
    except SpyServerError as exc:
        print(f"calibration failed: {exc.message}", file=sys.stderr)
        if exc.suggested_action:
            print(f"  {exc.suggested_action}", file=sys.stderr)
        return 1
    finally:
        client.close()

    print(f"WWV ladder at gain {args.gain}, {args.dwell:.0f}s each "
          f"-- {started.strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"{'freq':10s} {'SNR dB':>8s} {'mean|IQ|':>10s}  carrier")
    for r in readings:
        snr = "  n/a" if np.isnan(r.snr_db) else f"{r.snr_db:8.1f}"
        mark = "yes" if r.carrier else "no"
        print(f"{r.name:10s} {snr} {r.mean_abs_iq:10.5f}  {mark}")
    print()
    print(verdict(readings))

    if args.json:
        payload = {
            "timestamp_utc": started.isoformat(),
            "spyserver": args.spyserver,
            "gain": args.gain,
            "dwell_sec": args.dwell,
            "carrier_threshold_db": CARRIER_SNR_DB,
            "readings": [asdict(r) for r in readings],
            "verdict": verdict(readings),
        }
        with open(args.json, "w") as handle:
            json.dump(payload, handle, indent=2)
        print(f"\nwrote {args.json}")

    # A sweep that heard nothing is a real failure worth a non-zero exit,
    # so a scheduled run can react. Anything heard is a success: a closed
    # band is not a fault.
    return 0 if any(r.carrier for r in readings) else 2


if __name__ == "__main__":
    raise SystemExit(main())
