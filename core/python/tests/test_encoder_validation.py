import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ENGINE_PATH = ROOT / "core" / "python"
if str(ENGINE_PATH) not in sys.path:
    sys.path.insert(0, str(ENGINE_PATH))

from sstv_engine.encoder import SSTVEncoder  # noqa: E402
from sstv_engine.types import SSTVEncodeRequest  # noqa: E402


def test_encode_fails_for_missing_image_path():
    encoder = SSTVEncoder(debug=False)
    req = SSTVEncodeRequest(
        image_path="/nonexistent/path/in.png",
        output_path="/tmp/out.wav",
        mode="ScottieS1",
        sample_rate=22050,
        bits_per_sample=16,
        vox=False,
        fskid=None,
        resize=True,
    )

    result = encoder.encode(req)

    assert result.success is False
    assert "not found" in (result.message or "").lower()


def test_encode_rejects_invalid_mode_before_encoding():
    encoder = SSTVEncoder(debug=False)
    with tempfile.TemporaryDirectory() as td:
        img_path = Path(td) / "in.png"
        out_path = Path(td) / "out.wav"
        img_path.write_text("stub", encoding="utf-8")

        req = SSTVEncodeRequest(
            image_path=str(img_path),
            output_path=str(out_path),
            mode="BadMode",
            sample_rate=22050,
            bits_per_sample=16,
            vox=False,
            fskid=None,
            resize=True,
        )

        result = encoder.encode(req)

        assert result.success is False
        assert "unsupported mode" in (result.message or "").lower()
