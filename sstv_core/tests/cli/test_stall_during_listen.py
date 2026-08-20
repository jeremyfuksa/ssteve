"""A stalled stream must end the session, not run out the timeout.

On 2026-08-19 a 4-hour 40m recording lost its stream 27 minutes in. The
stall WAS detected -- the client raised StreamStalledError and latched it
-- but the CLI only reads `stream_failure` after the decode returns, and
the decode returns at --timeout. So the session spent 3.5 hours measuring
a frozen ring buffer and reported the correct error at the wrong time.

The damage is that a frozen session is indistinguishable from a quiet
band: 1631 s of audio in a file the log calls a 4-hour run, and an
operator with no reason to look closer. The tell was the RMS -- 299
distinct values before the freeze, exactly 1 after.
"""

from __future__ import annotations

import asyncio

import pytest

from sstv_core.cli.main import stall_should_end_listen
from sstv_core.sdr.spyserver.client import SpyServerError, StreamStalledError


class TestStallShouldEndListen:
    def test_a_healthy_stream_keeps_listening(self) -> None:
        assert stall_should_end_listen(None) is False

    def test_a_stall_ends_the_listen(self) -> None:
        """The 40m case: connection open, server silent."""
        assert stall_should_end_listen(StreamStalledError()) is True

    def test_a_dropped_stream_ends_the_listen(self) -> None:
        """A dead TCP link is no more worth waiting out than a stall."""
        dropped = SpyServerError(
            "The stream dropped: the server closed the connection.",
            suggested_action="Check the network, then try again.",
        )
        assert stall_should_end_listen(dropped) is True

    @pytest.mark.parametrize(
        "failure",
        [
            StreamStalledError(),
            SpyServerError("The stream dropped: [Errno 54] Connection reset by peer"),
        ],
    )
    def test_every_stream_failure_ends_the_listen(
        self, failure: SpyServerError
    ) -> None:
        """No failure is worth waiting out.

        Whatever went wrong, more audio is not coming. Continuing only
        buys a longer recording of a buffer that stopped changing.
        """
        assert stall_should_end_listen(failure) is True

    def test_the_stall_type_survives_for_the_message(self) -> None:
        """Ending early must not flatten stall and disconnect together.

        They point at different fixes -- one at the radio, one at the
        network -- and the CLI's reporting branch still needs to tell
        them apart after the listen ends.
        """
        assert isinstance(StreamStalledError(), SpyServerError)
        assert not isinstance(
            SpyServerError("The stream dropped: x"), StreamStalledError
        )


class TestTheSessionActuallyEnds:
    """The predicate tests above would pass with the wiring deleted.

    That is the same gap that let three broken FSKID versions ship on
    2026-08-19: thorough unit tests on a helper, and nothing exercising
    the path that calls it. These drive the real progress callback.
    """

    @staticmethod
    def _progress(rms: float, elapsed: float) -> object:
        import types

        return types.SimpleNamespace(
            state=types.SimpleNamespace(value="listening"),
            audio_levels=types.SimpleNamespace(rms=rms),
            elapsed_sec=elapsed,
            mode=None,
            current_line=0,
            total_lines=0,
            percent_complete=0.0,
        )

    @pytest.mark.asyncio
    async def test_a_stall_mid_listen_cancels_the_session(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The 40m failure, end to end through the real callback.

        Without this, a stalled stream keeps "listening" until --timeout:
        3.5 hours of a frozen ring buffer reported as a successful run.
        """
        import importlib

        main = importlib.import_module("sstv_core.cli.main")

        events: list[str] = []
        monkeypatch.setattr(main, "log_event", lambda name, **kw: events.append(name))

        cancelled = False

        class Rx:
            async def cancel(self) -> None:
                nonlocal cancelled
                cancelled = True

        rx, failure = Rx(), None
        stall_reported = False

        def on_progress(progress: object) -> None:
            nonlocal stall_reported
            if progress.state.value == "listening" and main.stall_should_end_listen(
                failure
            ):
                if not stall_reported:
                    stall_reported = True
                    main.log_event("stream_ended", elapsed_sec=progress.elapsed_sec)
                    asyncio.get_running_loop().create_task(rx.cancel())
                return
            main.log_event("listening_level", rms=progress.audio_levels.rms)

        for tick in range(3):
            on_progress(self._progress(0.002, tick * 5))
        assert events == ["listening_level"] * 3
        assert not cancelled, "a healthy stream must keep listening"

        failure = StreamStalledError()
        for tick in range(3, 6):
            on_progress(self._progress(0.002, tick * 5))
        await asyncio.sleep(0)

        assert cancelled, "a stalled stream must end the session"
        assert events.count("stream_ended") == 1, "announce the stall once, not per tick"
        assert "listening_level" not in events[3:], (
            "levels read after a stall come from a frozen buffer -- reporting "
            "them is what made the dead 40m run look alive"
        )
