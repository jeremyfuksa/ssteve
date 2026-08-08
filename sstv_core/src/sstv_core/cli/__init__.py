"""Command-line interface for SSTeVe SSTV operations."""

import sys

from .main import main


def decode() -> None:
    """Console-script entry point: `sstv-decode` == `sstv-cli decode`."""
    sys.exit(main(["decode", *sys.argv[1:]]))


def encode() -> None:
    """Console-script entry point: `sstv-encode` == `sstv-cli encode`."""
    sys.exit(main(["encode", *sys.argv[1:]]))


__all__ = ["decode", "encode", "main"]
