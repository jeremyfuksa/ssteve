import sys
import tempfile
from pathlib import Path
import pytest


# Ensure core/python is importable
ROOT = Path(__file__).resolve().parents[3]
ENGINE_PATH = ROOT / "core" / "python"
if str(ENGINE_PATH) not in sys.path:
    sys.path.insert(0, str(ENGINE_PATH))


def test_encode_smoke_tmp_image():
    from PIL import Image
    from sstv_engine.encoder import SSTVEncoder
    from sstv_engine.types import SSTVEncodeRequest

    encoder = SSTVEncoder(debug=False)
    if not encoder.check_dependencies():
        pytest.skip("Engine dependencies not installed")

    with tempfile.TemporaryDirectory() as td:
        img_path = Path(td) / "in.png"
        wav_path = Path(td) / "out.wav"

        Image.new("RGB", (100, 100), (200, 20, 20)).save(img_path)
        req = SSTVEncodeRequest(
            image_path=str(img_path),
            output_path=str(wav_path),
            mode="ScottieS1",
            sample_rate=22050,
            bits_per_sample=16,
            vox=False,
            fskid=None,
            resize=True,
        )

        result = encoder.encode(req)
        assert result.success, result.message
        assert wav_path.exists()


def test_imports_cli_available():
    # Basic import checks for the CLI module paths
    import sstv_engine.cli as cli  # noqa: F401
    import sstv_engine.decoder as dec  # noqa: F401
    import sstv_engine.enhancer as enh  # noqa: F401
