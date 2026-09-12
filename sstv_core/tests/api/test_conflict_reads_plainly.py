"""A half-duplex conflict must read plainly, and stay a 409 when reworded.

The operator meets this error more than any other: it is what a second
click produces. It said

    Decode session 4c5ce24f-6543-47b3-8961-dbce6326a75e already active.
    Stop it before starting a new one.

-- legible, but leading with a UUID the operator never sees anywhere else
in the product. It is already in the 409 body as active_session_id, where
a client can use it to offer "stop that one and retry"; in the sentence it
is only noise.

Rewriting it turned every 409 into a 500. Three routes decided the status
code by matching "already active" in the message, so the copy written for
an operator and the control flow were the same string, and improving one
broke the other. The type is now what means 409, which is what these tests
pin: the sentence is free to change, and the status code is not.
"""

from __future__ import annotations

import re

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from sstv_core.api.main import app
from sstv_core.api.session_manager import (
    ConcurrentOperationError,
    concurrent_operation_detail,
    session_manager,
)

client = TestClient(app)

UUID_ANYWHERE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I
)


class TestTheSentence:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "second",
        ["decode", "transmit"],
    )
    async def test_a_second_start_says_so_without_a_uuid(self, second):
        try:
            await session_manager.create_decode_session()
            if second == "transmit":
                with pytest.raises(ConcurrentOperationError) as caught:
                    await session_manager.create_transmit_session()
            else:
                with pytest.raises(ConcurrentOperationError) as caught:
                    await session_manager.create_decode_session()
        finally:
            session_manager.reset()

        message = str(caught.value)
        assert not UUID_ANYWHERE.search(message), (
            f"the operator was shown a session id: {message}"
        )
        assert "one thing at a time" in message, message

    @pytest.mark.asyncio
    async def test_the_id_is_still_there_for_a_client_that_wants_it(self):
        try:
            session = await session_manager.create_decode_session()
            detail = concurrent_operation_detail("anything at all")
            assert detail["active_session_id"] == str(session.session_id)
            assert detail["session_type"] == "decode"
        finally:
            session_manager.reset()


class TestTheStatusCode:
    """The type decides the status, so rewording cannot change it."""

    @pytest.mark.parametrize(
        ("path", "payload"),
        [
            ("/api/v1/decode/start", {}),
            (
                "/api/v1/transmit",
                {"image_path": "/home/admin/test.png", "mode": "MartinM1"},
            ),
        ],
        ids=["decode", "transmit"],
    )
    def test_a_conflict_is_409_whatever_it_says(self, monkeypatch, path, payload):
        """Wording the routes have never seen still comes back 409.

        The words below are deliberately nothing like the real copy: if the
        route were reading the message again, this is what would catch it.
        """
        creator = "create_decode_session" if "decode" in path else "create_transmit_session"

        async def busy(*args, **kwargs):
            raise ConcurrentOperationError("Wholly unfamiliar phrasing.")

        monkeypatch.setattr(type(session_manager), creator, busy)

        response = client.post(path, json=payload)

        assert response.status_code == status.HTTP_409_CONFLICT, response.text
        body = response.json()["detail"]
        assert body["error"] == "CONCURRENT_OPERATION"
        assert body["message"] == "Wholly unfamiliar phrasing."
        assert body["recoverable"] is True

    def test_the_real_conflict_carries_the_id_it_no_longer_says(self):
        client.post("/api/v1/decode/start", json={})
        try:
            response = client.post("/api/v1/decode/start", json={})
            assert response.status_code == status.HTTP_409_CONFLICT, response.text
            body = response.json()["detail"]
            assert not UUID_ANYWHERE.search(body["message"]), body["message"]
            assert body["active_session_id"], "the id has to survive somewhere"
        finally:
            session_manager.reset()
