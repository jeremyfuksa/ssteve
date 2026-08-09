#!/usr/bin/env python3
"""Check DEVICE_PROFILES' USB VID/PIDs against hardware that is plugged in.

The Digirig Mobile profile claims Silicon Labs CP2102N 0x10C4/0xEA60 on the
strength of digirig.net documentation alone -- no one has held the unit next
to the code (issue #73). Same for any other profile carrying a VID/PID.

Run this with the interface connected:

    cd sstv_core && uv run python scripts/verify_device_profiles.py

It enumerates serial ports through pyserial (already a dependency, and it
works the same on Darwin and Linux, so there is no lsusb-vs-system_profiler
branch to get wrong), then reports three things per profile: matched,
mismatched, or absent. Values are read from DEVICE_PROFILES at runtime rather
than restated here, so this cannot drift from the code it checks.

Exit codes: 0 = every profile with a VID/PID was matched by an attached
device, 1 = something attached contradicts a profile, 2 = nothing to compare
against (no device attached, or pyserial missing).
"""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_import_path() -> None:
    src = Path(__file__).resolve().parents[1] / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


def main() -> int:
    _ensure_import_path()

    try:
        from serial.tools import list_ports
    except ImportError:
        print("pyserial is not installed; run `uv sync --extra dev` first.")
        return 2

    from sstv_core.smart_features.device_detector import DEVICE_PROFILES

    ports = list(list_ports.comports())
    print(f"Attached serial ports: {len(ports)}\n")
    for port in ports:
        vid = f"0x{port.vid:04X}" if port.vid is not None else "----"
        pid = f"0x{port.pid:04X}" if port.pid is not None else "----"
        print(f"  {port.device}  VID={vid} PID={pid}  {port.description}")
        if port.manufacturer:
            print(f"      manufacturer: {port.manufacturer}")
    print()

    attached = {
        (p.vid, p.pid) for p in ports if p.vid is not None and p.pid is not None
    }
    by_vid = {p.vid: p for p in ports if p.vid is not None}

    profiles = [p for p in DEVICE_PROFILES if p.usb_vid and p.usb_pid]
    if not profiles:
        print("No profile declares a USB VID/PID; nothing to verify.")
        return 0

    matched = 0
    mismatched = 0
    for profile in profiles:
        claim = f"0x{profile.usb_vid:04X}/0x{profile.usb_pid:04X}"
        if (profile.usb_vid, profile.usb_pid) in attached:
            print(f"MATCH     {profile.name}: {claim} is attached. Profile confirmed.")
            matched += 1
        elif profile.usb_vid in by_vid:
            # Same vendor, different product: the likeliest real-world error,
            # and the one that silently misidentifies a device.
            found = by_vid[profile.usb_vid]
            print(
                f"MISMATCH  {profile.name}: profile claims {claim}, but the "
                f"attached device from that vendor reports "
                f"0x{found.vid:04X}/0x{found.pid:04X} ({found.description}). "
                f"Update the profile."
            )
            mismatched += 1
        else:
            print(f"ABSENT    {profile.name}: {claim} not attached; unverified.")

    print()
    if mismatched:
        print("At least one profile contradicts attached hardware. Fix it, then rerun.")
        return 1
    if matched:
        print(f"{matched} profile(s) confirmed against real hardware.")
        return 0
    print(
        "Nothing to compare against -- plug the interface in and rerun. "
        "(A Digirig enumerates as a USB-serial port; issue #73 wants that "
        "VID/PID confirmed.)"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
