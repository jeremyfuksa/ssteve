"""Every HTTPException detail must be the structured object, not a string.

The frontend renders errors from one component. If some routes return
`detail="Directory not found: /x"` and others return
`{"error": ..., "message": ..., "suggested_action": ...}`, that component
special-cases stragglers forever. #74 normalized the last 20 bare strings
(import_routes, qso, smart_reply) on 2026-08-09.

The source scan is the point: per-endpoint assertions only cover endpoints
someone remembered to test, while this fails on a bare string added to any
route module later.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROUTES_DIR = Path(__file__).resolve().parents[2] / "src" / "sstv_core" / "api" / "routes"


def _route_modules() -> list[Path]:
    return sorted(p for p in ROUTES_DIR.glob("*.py") if p.name != "__init__.py")


#: Helpers that build and return the structured detail object. A call to one
#: of these is the structured shape, not a bare value -- `session_manager`
#: exists precisely so decode, transmit and smart_reply stop hand-rolling
#: three slightly different 409 bodies. Named explicitly rather than allowing
#: every call: `detail=f"..."` and `detail=str(e)` are the shapes this test
#: is for, and a blanket allowance for Call would let both through.
DETAIL_BUILDERS = frozenset({"concurrent_operation_detail"})


def _bare_detail_sites(path: Path) -> list[tuple[int, str]]:
    """Line numbers where `detail=` is passed something that isn't a dict."""
    tree = ast.parse(path.read_text())
    offenders: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg != "detail":
                continue
            # A dict literal is the structured shape. A Name may be a dict
            # built just above the raise, so allow it and let the runtime
            # tests below cover those; everything else is a bare value.
            if isinstance(kw.value, ast.Dict | ast.Name):
                continue
            if (
                isinstance(kw.value, ast.Call)
                and isinstance(kw.value.func, ast.Name)
                and kw.value.func.id in DETAIL_BUILDERS
            ):
                continue
            offenders.append((kw.lineno, ast.unparse(kw.value)[:70]))
    return offenders


@pytest.mark.parametrize("module", _route_modules(), ids=lambda p: p.name)
def test_no_bare_string_error_details(module: Path):
    offenders = _bare_detail_sites(module)
    assert not offenders, "\n".join(
        f"{module.name}:{line} detail={src}" for line, src in offenders
    )


def test_the_scan_can_actually_find_a_bare_string(tmp_path):
    """Guard the guard: a scanner that never fails proves nothing."""
    sample = tmp_path / "bad_route.py"
    sample.write_text(
        "from fastapi import HTTPException\n"
        "def f():\n"
        "    raise HTTPException(status_code=404, detail='nope')\n"
    )
    assert _bare_detail_sites(sample), "scanner missed an obvious bare string"

    good = tmp_path / "good_route.py"
    good.write_text(
        "from fastapi import HTTPException\n"
        "def f():\n"
        "    raise HTTPException(status_code=404, detail={'error': 'E', 'message': 'm'})\n"
    )
    assert not _bare_detail_sites(good), "scanner flagged a structured detail"


def test_every_structured_detail_has_error_and_message():
    """The two fields the client always reads must both be present."""
    missing: list[str] = []
    for module in _route_modules():
        tree = ast.parse(module.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if kw.arg != "detail" or not isinstance(kw.value, ast.Dict):
                    continue
                keys = {
                    k.value
                    for k in kw.value.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)
                }
                if not {"error", "message"} <= keys:
                    missing.append(
                        f"{module.name}:{kw.lineno} has {sorted(keys)}"
                    )
    assert not missing, "\n".join(missing)
