"""Entry point for the frozen engine.

A console script (`sstv-server`) is a generated shim that PyInstaller cannot
analyse, so the frozen build gets its own module that calls the same
function. Keep it doing nothing else: anything here runs before the server
can report a problem.
"""

from __future__ import annotations

import multiprocessing
import sys


def main() -> None:
    # Frozen builds that ever spawn a process need this before anything else,
    # or the child re-runs the bootloader and forks forever.
    multiprocessing.freeze_support()

    from sstv_core.api.main import run_server

    run_server()


if __name__ == "__main__":
    sys.exit(main())
