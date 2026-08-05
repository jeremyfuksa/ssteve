#!/usr/bin/env python3
"""Export the OpenAPI schema for SSTeVe."""

from __future__ import annotations

import os

os.environ.setdefault("SSTVE_DB_PATH", ":memory:")

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = ROOT / "docs"
OPENAPI_PATH = DOCS_DIR / "core" / "openapi.json"


def _ensure_import_path() -> None:
    src_dir = ROOT / "sstv_core" / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


def _load_openapi() -> dict[str, Any]:
    _ensure_import_path()
    from sstv_core.api.main import app

    return app.openapi()


def _write_openapi(spec: dict[str, Any]) -> None:
    OPENAPI_PATH.parent.mkdir(parents=True, exist_ok=True)
    OPENAPI_PATH.write_text(json.dumps(spec, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    _write_openapi(_load_openapi())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
