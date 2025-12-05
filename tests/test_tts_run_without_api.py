import json
from pathlib import Path

from openai_tts_gui import config
from openai_tts_gui.tts import TTSProcessor


def test_tts_run_happy_no_network(monkeypatch, tmp_path):
    out = tmp_path / "out.wav"
    params = {
        "api_key": "sk-test",
        "text": "Hello world.",
        "output_path": str(out),
        "model": "tts-1",
        "voice": "alloy",
        "response_format": "wav",
        "speed": 1.0,
        "instructions": "",
        "retain_files": False,
    }

    # Create small dummy chunk files instead of calling the API
    def fake_save(self, text_chunk, filename, *args, **kwargs):
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        Path(filename).write_bytes(b"\x00")
        return True

    captured_kwargs = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)
            # minimal surface; not used because _save_chunk_with_retries is monkeypatched
            self.audio = type("audio", (), {"speech": None})

    # Concatenation -> just write the output file
    monkeypatch.setattr(
        "openai_tts_gui.tts.concatenate_audio_files",
        lambda files, outp: Path(outp).write_bytes(b"\x00"),
    )
    monkeypatch.setattr(TTSProcessor, "_save_chunk_with_retries", fake_save, raising=True)
    monkeypatch.setattr("openai_tts_gui.tts.OpenAI", FakeOpenAI)

    tp = TTSProcessor(params)
    # Run synchronously (no need to start the QThread)
    tp.run()
    assert out.exists()
    sidecar = Path(str(out) + ".json")
    assert sidecar.exists()
    meta = json.loads(sidecar.read_text(encoding="utf-8"))
    assert meta.get("stream_format") == getattr(config, "STREAM_FORMAT", None)
    assert captured_kwargs.get("api_key") == "sk-test"
    assert captured_kwargs.get("timeout") == getattr(config, "OPENAI_TIMEOUT", 60.0)
    assert captured_kwargs.get("base_url") is None


def test_tts_error_on_empty_text(monkeypatch, tmp_path):
    out = tmp_path / "out.mp3"
    params = {
        "api_key": "sk-test",
        "text": "   ",  # empty after strip
        "output_path": str(out),
        "model": "tts-1",
        "voice": "alloy",
        "response_format": "mp3",
        "speed": 1.0,
        "instructions": "",
        "retain_files": False,
    }
    # Should not raise; run() will log and emit error, then finish
    TTSProcessor(params).run()
