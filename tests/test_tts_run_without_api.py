from pathlib import Path

from tts import TTSProcessor


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

    # Concatenation -> just write the output file
    monkeypatch.setattr(
        "tts.concatenate_audio_files", lambda files, outp: Path(outp).write_bytes(b"\x00")
    )
    monkeypatch.setattr(TTSProcessor, "_save_chunk_with_retries", fake_save, raising=True)

    tp = TTSProcessor(params)
    # Run synchronously (no need to start the QThread)
    tp.run()
    assert out.exists()
    assert Path(str(out) + ".json").exists()


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
