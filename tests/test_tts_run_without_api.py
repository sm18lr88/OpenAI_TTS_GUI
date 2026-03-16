import json
from pathlib import Path

from openai_tts_gui.config import settings
from openai_tts_gui.tts import TTSService


def test_tts_service_happy_no_network(monkeypatch, tmp_path):
    out = tmp_path / "out.wav"

    captured_kwargs = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)
            self.audio = type(
                "A", (), {"speech": type("S", (), {"with_streaming_response": self})()}
            )()

        def create(self, **api_params):
            return self

        def __enter__(self):
            self.request_id = None
            return self

        def __exit__(self, *args):
            pass

        def stream_to_file(self, filename):
            Path(filename).parent.mkdir(parents=True, exist_ok=True)
            Path(filename).write_bytes(b"\x00")

    monkeypatch.setattr("openai_tts_gui.tts._service.OpenAI", FakeOpenAI)
    monkeypatch.setattr(
        "openai_tts_gui.tts._service.concatenate_audio_files",
        lambda files, outp: Path(outp).write_bytes(b"\x00"),
    )

    svc = TTSService(api_key="sk-test")
    svc.generate(
        text="Hello world.",
        output_path=str(out),
        model="tts-1",
        voice="alloy",
        response_format="wav",
        speed=1.0,
        instructions="",
        retain_files=False,
    )
    assert out.exists()
    sidecar = Path(str(out) + ".json")
    assert sidecar.exists()
    meta = json.loads(sidecar.read_text(encoding="utf-8"))
    assert meta.get("stream_format") == getattr(settings, "STREAM_FORMAT", None)
    assert captured_kwargs.get("api_key") == "sk-test"
    assert captured_kwargs.get("timeout") == getattr(settings, "OPENAI_TIMEOUT", 60.0)
    assert captured_kwargs.get("base_url") is None


def test_tts_error_on_empty_text(tmp_path):
    import pytest

    from openai_tts_gui.errors import TTSChunkError

    svc = TTSService(api_key="sk-test")
    with pytest.raises(TTSChunkError):
        svc.generate(
            text="   ",
            output_path=str(tmp_path / "out.mp3"),
        )
