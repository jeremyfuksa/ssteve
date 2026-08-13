"""The console-script entry points, exercised as entry points.

Every other CLI test calls main(["decode", ...]) with a hand-built argv,
which is exactly why issue #91 survived to a live session: the wrappers in
cli/__init__.py prepend the subcommand to sys.argv, so a global flag the
operator typed always landed AFTER it, where argparse would not take it.
A test that builds its own argv never goes through that wrapper and never
sees the bug.

So these drive `decode()` and `encode()` themselves, with sys.argv patched
the way a shell would leave it.
"""

from __future__ import annotations

import pytest

from sstv_core.cli import decode, encode


def run_entry_point(entry, monkeypatch, argv: list[str]) -> int:
    """Call a console-script entry point and return its exit code.

    The entry points call sys.exit(), so the SystemExit is the result.
    sys.argv[0] is the script name a shell would pass.
    """
    monkeypatch.setattr("sys.argv", ["sstv-test", *argv])
    with pytest.raises(SystemExit) as excinfo:
        entry()
    return excinfo.value.code


class TestGlobalFlagsReachTheConsoleScripts:
    """--verbose and --json must work through the wrappers (issue #91)."""

    @pytest.mark.parametrize("flag", ["--verbose", "--json"])
    def test_decode_accepts_the_global_flags(self, flag, monkeypatch, caplog):
        """These both exited 2 with "unrecognized arguments" before the fix.

        A missing file is the cheapest way to reach a real exit code: the
        flag has to parse before the decode can fail on its own terms.
        """
        with caplog.at_level("INFO"):
            code = run_entry_point(
                decode, monkeypatch, [flag, "--file", "definitely-absent.wav"]
            )
        assert code == 1, "should fail on the missing file, not on the flag"
        assert "definitely-absent.wav" in caplog.text

    @pytest.mark.parametrize("flag", ["--verbose", "--json"])
    def test_encode_accepts_the_global_flags(self, flag, monkeypatch, caplog):
        with caplog.at_level("INFO"):
            code = run_entry_point(
                encode, monkeypatch, [flag, "--image", "definitely-absent.png"]
            )
        assert code == 1
        assert "definitely-absent.png" in caplog.text

    def test_decode_accepts_both_global_flags_together(self, monkeypatch):
        code = run_entry_point(
            decode, monkeypatch, ["--verbose", "--json", "--file", "absent.wav"]
        )
        assert code == 1

    def test_json_flag_actually_produces_json(self, monkeypatch, capsys):
        """--json is the screen-reader path, so it has to do more than parse.

        Logging is configured per-run and handlers accumulate on the root
        logger, so this reads stderr rather than caplog: the question is
        what a screen reader would actually receive.
        """
        import json
        import logging

        for handler in logging.getLogger().handlers[:]:
            logging.getLogger().removeHandler(handler)

        run_entry_point(decode, monkeypatch, ["--json", "--file", "absent.wav"])

        stderr = capsys.readouterr().err
        lines = [ln for ln in stderr.splitlines() if ln.startswith("{")]
        assert lines, f"expected JSON on stderr, got: {stderr!r}"
        payload = json.loads(lines[-1])
        assert payload["event"] == "error"
        assert "absent.wav" in payload["message"]

    def test_a_flag_after_the_subcommand_still_works_through_main(self):
        """The module form the issue named as the workaround must not regress."""
        from sstv_core.cli.main import main

        assert main(["--verbose", "decode", "--file", "absent.wav"]) == 1


class TestConsoleScriptsStillRejectRealErrors:
    def test_an_unknown_flag_is_still_an_error(self, monkeypatch):
        """Hoisting the globals must not turn the parser permissive."""
        code = run_entry_point(decode, monkeypatch, ["--not-a-real-flag"])
        assert code == 2, "argparse should still reject unknown flags"
