"""The shell's band table and the engine's are the same table.

`sdr/bands.py` says why in its own docstring: "an operator who presses
'20m' in the app and types `--band 20m` at the terminal must land on the
same frequency." That was one table when only Python read it. The desktop
shell now needs it too -- `decode/start` takes a band by name, but
`config` stores a frequency, so remembering which band the operator was on
means knowing which frequency that is.

Two copies drift silently, and the drift is invisible until someone is
tuned 3 kHz off and hearing nothing. This reads the TypeScript and
compares, so the copy cannot move alone.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from sstv_core.sdr.bands import BAND_PRESETS

SHELL_CLIENT = Path(__file__).resolve().parents[2] / "sstv_desktop" / "src" / "core.ts"


def shell_band_table() -> dict[str, int]:
    """Read BAND_FREQUENCIES out of the shell's API client."""
    source = SHELL_CLIENT.read_text()
    block = re.search(
        r"export const BAND_FREQUENCIES: Record<Band, number> = \{(.*?)\};",
        source,
        re.S,
    )
    if block is None:
        raise AssertionError(
            f"no BAND_FREQUENCIES table in {SHELL_CLIENT}; if it moved, move "
            "this test with it rather than deleting it"
        )
    # Entries look like: "20m": 14_230_000,
    return {
        name: int(value.replace("_", ""))
        for name, value in re.findall(r'"([^"]+)":\s*([\d_]+)', block.group(1))
    }


@pytest.mark.skipif(
    not SHELL_CLIENT.exists(), reason="desktop shell not present in this checkout"
)
def test_the_shell_tunes_where_the_cli_tunes():
    assert shell_band_table() == BAND_PRESETS, (
        "the desktop shell and the engine disagree about band frequencies; "
        "sdr/bands.py is the source, sstv_desktop/src/core.ts is the copy"
    )
