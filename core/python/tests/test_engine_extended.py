import sys
import wave
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
ENGINE_PATH = ROOT / "core" / "python"
if str(ENGINE_PATH) not in sys.path:
    sys.path.insert(0, str(ENGINE_PATH))

from sstv_engine.decoder import SSTVDecoder  # noqa: E402
from sstv_engine.encoder import SSTVEncoder  # noqa: E402
from sstv_engine.enhancer import SSTVEnhancer  # noqa: E402
from sstv_engine.types import (  # noqa: E402
    EnhancementOptions,
    SSTVDecodeRequest,
    SSTVEncodeRequest,
)


def _make_decoder():
    decoder = SSTVDecoder(debug=False)
    decoder.set_progress_callback(lambda _: None)
    decoder.set_mode_callback(lambda _: None)
    if not decoder.check_dependencies():
        pytest.skip("Engine dependencies not installed")
    return decoder


def _make_encoder():
    encoder = SSTVEncoder(debug=False)
    if not encoder.check_dependencies():
        pytest.skip("Engine dependencies not installed")
    return encoder


def test_decode_martin_m2_reference(tmp_path: Path):
    decoder = _make_decoder()
    audio_path = ROOT / "core" / "shared" / "testing" / "reference" / "audio" / "essexham" / "essexham_01_martin2.wav"
    out_path = tmp_path / "martin_m2.png"

    req = SSTVDecodeRequest(audio_path=str(audio_path), output_path=str(out_path))
    result = decoder.decode(req)

    assert result.success, result.message
    assert out_path.exists()


def test_decode_handles_corrupt_audio(tmp_path: Path):
    decoder = _make_decoder()
    bad_audio = tmp_path / "corrupt.wav"
    bad_audio.write_text("this is not a wav file", encoding="utf-8")
    out_path = tmp_path / "corrupt.png"

    req = SSTVDecodeRequest(audio_path=str(bad_audio), output_path=str(out_path))
    result = decoder.decode(req)

    assert result.success is False
    assert "not found" in (result.message or "").lower() or "sstv" in (result.message or "").lower()


def test_decode_handles_no_sstv_signal(tmp_path: Path):
    decoder = _make_decoder()
    silence = tmp_path / "silence.wav"

    with wave.open(str(silence), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        wf.writeframes(b"\x00\x00" * 22050)  # 1 second of silence

    out_path = tmp_path / "no_signal.png"
    req = SSTVDecodeRequest(audio_path=str(silence), output_path=str(out_path))
    result = decoder.decode(req)

    assert result.success is False
    assert out_path.exists() is False or out_path.stat().st_size == 0


@pytest.mark.parametrize("mode", ["ScottieS1", "ScottieS2", "ScottieDX", "MartinM1", "MartinM2", "Robot36"])
def test_encode_all_modes(tmp_path: Path, mode: str):
    encoder = _make_encoder()
    img_path = tmp_path / "input.png"
    out_path = tmp_path / f"{mode}.wav"

    Image.new("RGB", (160, 120), (20, 140, 220)).save(img_path)

    req = SSTVEncodeRequest(
        image_path=str(img_path),
        output_path=str(out_path),
        mode=mode,
        sample_rate=22050,
        bits_per_sample=16,
        vox=False,
        fskid=None,
        resize=True,
    )

    result = encoder.encode(req)
    assert result.success, result.message
    assert out_path.exists()


def test_encode_handles_invalid_image(tmp_path: Path):
    encoder = _make_encoder()
    img_path = tmp_path / "invalid.png"
    img_path.write_text("not an image", encoding="utf-8")
    out_path = tmp_path / "invalid.wav"

    req = SSTVEncodeRequest(
        image_path=str(img_path),
        output_path=str(out_path),
        mode="ScottieS1",
        sample_rate=22050,
        bits_per_sample=16,
        vox=False,
        fskid=None,
        resize=True,
    )

    result = encoder.encode(req)
    assert result.success is False
    assert "failed" in (result.message or "").lower() or "not a" in (result.message or "").lower()


def test_roundtrip_scottie_s1(tmp_path: Path):
    encoder = _make_encoder()
    decoder = _make_decoder()

    img_path = tmp_path / "roundtrip.png"
    wav_path = tmp_path / "roundtrip.wav"
    decoded_path = tmp_path / "roundtrip_out.png"

    Image.new("RGB", (200, 150), (180, 60, 60)).save(img_path)

    encode_req = SSTVEncodeRequest(
        image_path=str(img_path),
        output_path=str(wav_path),
        mode="ScottieS1",
        sample_rate=22050,
        bits_per_sample=16,
        vox=False,
        fskid=None,
        resize=True,
    )

    encode_result = encoder.encode(encode_req)
    assert encode_result.success, encode_result.message
    assert wav_path.exists()

    decode_req = SSTVDecodeRequest(audio_path=str(wav_path), output_path=str(decoded_path))
    decode_result = decoder.decode(decode_req)
    assert decode_result.success, decode_result.message
    assert decoded_path.exists()


def test_enhance_handles_grayscale(tmp_path: Path):
    enhancer = SSTVEnhancer(debug=False)
    if not enhancer.check_dependencies():
        pytest.skip("Enhancer dependencies not installed")

    src = tmp_path / "gray.png"
    out = tmp_path / "gray_out.png"

    Image.new("L", (64, 64), 128).save(src)

    options = EnhancementOptions(
        contrast=1.1,
        brightness=1.0,
        saturation=1.0,
        auto_level=True,
        gamma=1.0,
        sharpen=False,
        white_balance=True,
    )

    result = enhancer.enhance_image(str(src), str(out), options)
    assert result.success, result.message
    assert out.exists()
    assert result.metadata["width"] == 64
    assert result.metadata["height"] == 64
