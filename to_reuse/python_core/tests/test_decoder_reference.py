import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
ENGINE_PATH = ROOT / "core" / "python"
if str(ENGINE_PATH) not in sys.path:
    sys.path.insert(0, str(ENGINE_PATH))

from sstv_engine.decoder import SSTVDecoder  # noqa: E402
from sstv_engine.types import SSTVDecodeRequest  # noqa: E402


def test_decode_scottie_s1_reference_roundtrip(tmp_path: Path):
    decoder = SSTVDecoder(debug=False)
    decoder.set_progress_callback(lambda _: None)
    decoder.set_mode_callback(lambda _: None)
    if not decoder.check_dependencies():
        pytest.skip("Engine dependencies not installed")

    audio_path = (
        ROOT
        / "core"
        / "shared"
        / "testing"
        / "reference"
        / "audio"
        / "mmsstv"
        / "scottie_s1_elk_forest.wav"
    )
    out_path = tmp_path / "scottie_s1.png"

    req = SSTVDecodeRequest(
        audio_path=str(audio_path),
        output_path=str(out_path),
        enhance=None,
    )

    result = decoder.decode(req)

    assert result.success, result.message
    assert out_path.exists()

    # Avoid noisy unraisable warning from upstream decoder destructor by deleting explicitly
    del decoder
