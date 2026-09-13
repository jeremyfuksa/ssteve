"""The shell calls endpoints the engine actually serves.

`sstv_desktop/src/core.ts` is hand-written. Its own header says the shapes
follow `docs/core/openapi.json`, which is a promise nothing kept: a route
could be renamed in the engine and the window would go on calling the old
one until somebody clicked the right button.

Generating the client instead was the other option. It was not taken: the
client carries the reasons for its own decisions -- why a 204 short-
circuits, why `detail.error` becomes a code, why the band is omitted when
a frequency is saved -- and a generator would replace all of that with
shapes. So the hand-written version stays and is checked, which is the
same choice made for the band table in
tests/test_band_table_matches_the_shell.py.

Two things are checked: that every endpoint the window calls is one the
engine serves, and that every field the window declares on a response
exists in that response's schema. The second is what catches a field
renamed in the engine -- the window would otherwise read `undefined` and
render an empty space.

What is still not checked is the *type* of each field: a string that
becomes a number passes this. That needs real codegen, and #145 records
it rather than this pretending otherwise.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SHELL_CLIENT = REPO / "sstv_desktop" / "src" / "core.ts"
CONTRACT = REPO / "docs" / "core" / "openapi.json"

#: The client's own prefix. Paths in the export carry it; the client adds
#: it in BASE(), so the two have to be compared with it stripped.
PREFIX = "/api/v1"

pytestmark = pytest.mark.skipif(
    not SHELL_CLIENT.exists(), reason="desktop shell not present in this checkout"
)


def shell_calls() -> set[tuple[str, str]]:
    """Every (method, path) the client asks for, as OpenAPI writes them.

    Template literals become `{}` placeholders: the client interpolates an
    id where the contract names a parameter, and which name it gives the
    variable is not the contract's business.
    """
    source = SHELL_CLIENT.read_text()
    calls: set[tuple[str, str]] = set()

    for match in re.finditer(
        r"request<[^>]*>\(\s*[`\"']([^`\"']+)[`\"']\s*(?:,\s*\{(.*?)\})?\s*\)",
        source,
        re.S,
    ):
        path, options = match.group(1), match.group(2) or ""
        method = re.search(r'method:\s*"(\w+)"', options)
        # A path with a query string is still the same endpoint.
        path = path.split("?")[0]
        # `${anything}` is a path parameter.
        path = re.sub(r"\$\{[^}]+\}", "{}", path)
        calls.add(((method.group(1) if method else "GET").lower(), path))

    return calls


def contract_paths() -> set[tuple[str, str]]:
    """Every (method, path) the engine serves, with names made anonymous."""
    document = json.loads(CONTRACT.read_text())
    served: set[tuple[str, str]] = set()
    for path, operations in document["paths"].items():
        if not path.startswith(PREFIX):
            continue
        anonymous = re.sub(r"\{[^}]+\}", "{}", path[len(PREFIX) :])
        for method in operations:
            if method in {"get", "post", "patch", "put", "delete"}:
                served.add((method, anonymous))
    return served


def test_every_call_the_window_makes_is_served():
    missing = sorted(shell_calls() - contract_paths())

    assert not missing, (
        "the shell calls endpoints the engine does not serve: "
        + ", ".join(f"{method.upper()} {path}" for method, path in missing)
        + ". Regenerate docs/core/openapi.json if the engine changed, or fix "
        "sstv_desktop/src/core.ts if the window did."
    )


def test_the_check_can_actually_see_the_calls():
    """A parser that found nothing would pass the test above forever."""
    calls = shell_calls()

    assert len(calls) >= 8, f"only found {calls}; the parser has stopped working"
    # A few by name, so a regex change that silently narrows what it
    # matches shows up here rather than as a quietly shrinking set.
    assert ("get", "/config") in calls
    assert ("patch", "/config") in calls
    assert ("post", "/decode/start") in calls
    assert ("get", "/decode/status/{}") in calls
    assert ("patch", "/decode/{}") in calls


#: Which hand-written interface answers which schema. Written out rather
#: than guessed from the names, because the names deliberately differ: the
#: window calls it a Config because that is what an operator would, and the
#: engine calls it a Configuration because that is its model.
#:
#: Only response shapes are here. Event interfaces are not in the OpenAPI
#: export at all -- WebSocket frames are not HTTP -- and they have their own
#: check in the shell (src/events.test.ts).
RESPONSE_SHAPES = {
    "Config": "Configuration",
    "ImageRow": "ImageMetadata",
    "StartedSession": "DecodeStartResponse",
    "DecodeStatus": "DecodeStatusResponse",
    "Propagation": "PropagationResponse",
}


def declared_fields(interface: str) -> set[str]:
    """The field names a client interface says it has."""
    source = SHELL_CLIENT.read_text()
    block = re.search(
        rf"export interface {interface} \{{(.*?)\n\}}", source, re.S
    )
    if block is None:
        raise AssertionError(f"no interface {interface} in {SHELL_CLIENT}")
    # `name?: type;` and `name: type;`, skipping comment lines.
    body = re.sub(r"/\*.*?\*/", "", block.group(1), flags=re.S)
    body = re.sub(r"//[^\n]*", "", body)
    return set(re.findall(r"^\s*([a-z_][A-Za-z0-9_]*)\??:", body, re.M))


def schema_fields(schema: str) -> set[str]:
    document = json.loads(CONTRACT.read_text())
    definition = document["components"]["schemas"].get(schema)
    if definition is None:
        raise AssertionError(f"no schema {schema} in {CONTRACT}")
    return set(definition.get("properties", {}))


@pytest.mark.parametrize(
    ("interface", "schema"), sorted(RESPONSE_SHAPES.items())
)
def test_the_window_only_reads_fields_the_engine_sends(interface, schema):
    invented = sorted(declared_fields(interface) - schema_fields(schema))

    assert not invented, (
        f"{interface} declares {invented}, which {schema} does not have. "
        "A field renamed in the engine reads as undefined in the window, "
        "which renders as an empty space rather than an error."
    )


def test_the_field_reader_can_actually_see_fields():
    """Same guard as above: a parser that found nothing would pass."""
    for interface in RESPONSE_SHAPES:
        assert declared_fields(interface), f"read no fields from {interface}"
    assert "spyserver_host" in declared_fields("Config")
    assert "heard_at" in declared_fields("ImageRow")
