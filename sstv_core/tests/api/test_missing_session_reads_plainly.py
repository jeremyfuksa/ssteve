"""A session the engine has lost must say so without quoting its id.

Found by using the app. Kill the engine mid-listen, press Stop, bring the
engine back, press Stop again:

    I couldn't stop the decode. Can't find decode session
    d46a3e88-60b5-46ea-9f13-5a2228464d61 -- Check the session ID

Three things wrong in one sentence. It leads with a UUID the operator sees
nowhere else in the product; it tells them to check an id they never typed
and cannot see; and for *stop* it is not an error at all -- a session the
engine does not have is a session that is not running, which is what
stopping it was for. The shell was left with a Stop button that could never
succeed.

The real fact is the same at all five sites and was stated at none of them:
sessions live in the engine's memory, so the id a caller holds outlives the
thing it names.

The sibling of #175. There the status code was coupled to the copy; here
the copy was coupled to an implementation detail.
"""

from __future__ import annotations

import re
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from sstv_core.api.main import app
from sstv_core.api.session_manager import session_manager

client = TestClient(app)

UUID_ANYWHERE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I
)

#: Every route that answers for a session the engine does not have.
MISSING_SESSION_ROUTES = [
    ("GET", "/api/v1/decode/status/{id}", None),
    ("POST", "/api/v1/decode/stop/{id}", None),
    ("PATCH", "/api/v1/decode/{id}", {"input_gain": 2.0}),
    ("GET", "/api/v1/transmit/status/{id}", None),
    ("POST", "/api/v1/transmit/cancel/{id}", None),
]


@pytest.fixture(autouse=True)
def _no_leftover_sessions():
    yield
    session_manager.reset()


@pytest.mark.parametrize(
    ("method", "template", "body"),
    MISSING_SESSION_ROUTES,
    ids=[f"{m} {t}" for m, t, _ in MISSING_SESSION_ROUTES],
)
def test_it_says_what_happened_without_quoting_the_id(method, template, body):
    missing = uuid4()
    response = client.request(
        method, template.format(id=missing), json=body if body else None
    )

    assert response.status_code == 404, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "SESSION_NOT_FOUND"

    message = detail["message"]
    assert not UUID_ANYWHERE.search(message), (
        f"the operator was shown a session id: {message}"
    )

    # Say why, not just that. "I don't have it" leaves the operator deciding
    # between a bug and a restart; the reason is the difference.
    assert "finished" in message or "restarted" in message, message

    # And something to do, which is never "check the id" -- they never saw one.
    action = detail["suggested_action"]
    assert action
    assert "id" not in action.lower().split(), action


def test_stopping_something_that_is_not_running_is_not_the_callers_mistake():
    """Stop is the one where 404 means the goal is already met.

    The shell treats SESSION_NOT_FOUND from this route as stopped, so the
    copy must not imply the operator did something wrong or that a retry
    would help. It used to say "Check the session ID", which is how a
    Stop button came to be unclickable-but-stuck.
    """
    response = client.post(f"/api/v1/decode/stop/{uuid4()}")

    detail = response.json()["detail"]
    assert "isn't running" in detail["message"], detail["message"]
    assert "Nothing to stop" in detail["suggested_action"]
    assert "check" not in detail["suggested_action"].lower()
