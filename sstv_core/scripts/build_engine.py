"""Freeze the engine and name it the way Tauri's bundler expects (#143).

Tauri resolves an `externalBin` entry by appending the **target triple** to
the name it is given, so a binary called `sstv-server` is looked up as
`sstv-server-aarch64-apple-darwin`. Get that wrong and the build fails with
a message about a missing sidecar rather than about the name.

Run from sstv_core/:

    uv run python scripts/build_engine.py

The result lands in ../sstv_desktop/src-tauri/binaries/, which is what
tauri.conf.json points at.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
SPEC = PROJECT / "packaging" / "sstv-server.spec"
DESTINATION = PROJECT.parent / "sstv_desktop" / "src-tauri" / "binaries"


def target_triple() -> str:
    """Ask rustc, rather than guessing from platform.machine().

    The triple has to match what Tauri asks for exactly, and only the
    toolchain that will do the bundling knows it.
    """
    result = subprocess.run(
        ["rustc", "-vV"], capture_output=True, text=True, check=True
    )
    for line in result.stdout.splitlines():
        if line.startswith("host:"):
            return line.split(":", 1)[1].strip()
    raise RuntimeError("rustc -vV reported no host triple")


def build(clean: bool) -> Path:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(SPEC),
        "--distpath",
        str(PROJECT / "dist"),
        "--workpath",
        str(PROJECT / "build"),
        "--noconfirm",
    ]
    if clean:
        command.append("--clean")
    subprocess.run(command, check=True, cwd=PROJECT)
    return PROJECT / "dist" / "sstv-server"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean", action="store_true", help="Discard PyInstaller caches")
    parser.add_argument(
        "--keep-in-place",
        action="store_true",
        help="Build but do not copy into the desktop app",
    )
    arguments = parser.parse_args()

    folder = build(arguments.clean)
    binary = folder / "sstv-server"
    if not binary.exists():
        print(f"build produced no binary at {binary}", file=sys.stderr)
        return 1

    if arguments.keep_in_place:
        print(f"built {folder}")
        return 0

    triple = target_triple()
    DESTINATION.mkdir(parents=True, exist_ok=True)

    # The whole folder, plus the binary under its triple name beside it. The
    # one-folder layout means the executable needs its siblings: copying only
    # the executable produces something that starts and immediately dies
    # looking for Python.
    payload = DESTINATION / "engine"
    if payload.exists():
        shutil.rmtree(payload)
    shutil.copytree(folder, payload)

    launcher = DESTINATION / f"sstv-server-{triple}"
    shutil.copy2(binary, launcher)
    launcher.chmod(0o755)

    print(f"engine  -> {payload}")
    print(f"sidecar -> {launcher}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
