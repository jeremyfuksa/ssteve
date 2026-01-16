#!/usr/bin/env python3
"""Export OpenAPI and Postman collection for SSTeVe."""

from __future__ import annotations

import os
os.environ.setdefault("SSTVE_DB_PATH", ":memory:")

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = ROOT / "docs"
POSTMAN_DIR = DOCS_DIR / "postman"
OPENAPI_PATH = DOCS_DIR / "openapi.json"
POSTMAN_PATH = POSTMAN_DIR / "SSTeVe.postman_collection.json"


def _ensure_import_path() -> None:
    src_dir = ROOT / "sstv_core" / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


def _load_openapi() -> dict[str, Any]:
    _ensure_import_path()
    from sstv_core.api.main import app

    return app.openapi()


def _write_openapi(spec: dict[str, Any]) -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    OPENAPI_PATH.write_text(json.dumps(spec, indent=2, sort_keys=True), encoding="utf-8")


def _schema_to_example(schema: dict[str, Any]) -> Any:
    if not schema:
        return {}
    schema_type = schema.get("type")
    if schema_type == "object":
        props = schema.get("properties", {})
        return {key: _schema_to_example(value) for key, value in props.items()}
    if schema_type == "array":
        return [_schema_to_example(schema.get("items", {}))]
    if schema_type == "integer":
        return 0
    if schema_type == "number":
        return 0.0
    if schema_type == "boolean":
        return False
    if schema_type == "string":
        return ""
    return {}


def _build_postman(spec: dict[str, Any]) -> dict[str, Any]:
    collection: dict[str, Any] = {
        "info": {
            "name": spec.get("info", {}).get("title", "SSTeVe API"),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": [],
        "variable": [
            {"key": "baseUrl", "value": "http://localhost:8000"},
        ],
    }

    paths = spec.get("paths", {})
    for path, methods in sorted(paths.items()):
        for method, operation in sorted(methods.items()):
            method_upper = method.upper()
            name = operation.get("summary") or f"{method_upper} {path}"
            request: dict[str, Any] = {
                "method": method_upper,
                "header": [{"key": "Content-Type", "value": "application/json"}],
                "url": {
                    "raw": f"{{{{baseUrl}}}}{path}",
                    "host": ["{{baseUrl}}"],
                    "path": [segment for segment in path.split("/") if segment],
                },
            }

            request_body = operation.get("requestBody", {})
            content = request_body.get("content", {})
            app_json = content.get("application/json")
            if app_json and "schema" in app_json:
                example = _schema_to_example(app_json["schema"])
                request["body"] = {
                    "mode": "raw",
                    "raw": json.dumps(example, indent=2),
                }

            collection["item"].append(
                {
                    "name": name,
                    "request": request,
                }
            )

    return collection


def _write_postman(collection: dict[str, Any]) -> None:
    POSTMAN_DIR.mkdir(parents=True, exist_ok=True)
    POSTMAN_PATH.write_text(json.dumps(collection, indent=2), encoding="utf-8")


def main() -> int:
    spec = _load_openapi()
    _write_openapi(spec)
    postman = _build_postman(spec)
    _write_postman(postman)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
