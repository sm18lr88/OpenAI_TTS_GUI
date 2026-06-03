from pathlib import Path

from openai_tts_gui.cli import main as cli_main


def test_cli_happy_path(monkeypatch, tmp_path):
    infile = tmp_path / "in.txt"
    outfile = tmp_path / "out.mp3"
    infile.write_text("hello world", encoding="utf-8")

    monkeypatch.setattr("openai_tts_gui.cli.read_api_key", lambda: "sk-test-123")

    class DummyService:
        def __init__(self, **kwargs):
            pass

        def generate(self, **kwargs):
            Path(kwargs["output_path"]).parent.mkdir(parents=True, exist_ok=True)
            Path(kwargs["output_path"]).write_bytes(b"fake-audio")
            return "ok"

    monkeypatch.setattr("openai_tts_gui.cli.TTSService", DummyService)

    rc = cli_main(["--in", str(infile), "--out", str(outfile)])
    assert rc == 0
    assert outfile.exists()


def test_cli_forwards_tts_options(monkeypatch, tmp_path):
    infile = tmp_path / "in.txt"
    outfile = tmp_path / "out.wav"
    infile.write_text("hello world", encoding="utf-8")
    captured: dict[str, object] = {}

    monkeypatch.setattr("openai_tts_gui.cli.read_api_key", lambda: "sk-test-123")

    class DummyService:
        def __init__(self, **kwargs):
            pass

        def generate(self, **kwargs):
            captured.update(kwargs)
            Path(kwargs["output_path"]).write_bytes(b"fake-audio")
            return "ok"

    monkeypatch.setattr("openai_tts_gui.cli.TTSService", DummyService)

    rc = cli_main(
        [
            "--in",
            str(infile),
            "--out",
            str(outfile),
            "--model",
            "gpt-4o-mini-tts",
            "--voice",
            "nova",
            "--format",
            "wav",
            "--speed",
            "1.25",
            "--instructions",
            "speak warmly",
            "--retain-files",
        ]
    )

    assert rc == 0
    assert captured["model"] == "gpt-4o-mini-tts"
    assert captured["voice"] == "nova"
    assert captured["response_format"] == "wav"
    assert captured["speed"] == 1.25
    assert captured["instructions"] == "speak warmly"
    assert captured["retain_files"] is True


def test_cli_version_early_parse_ok(capsys):
    rc = cli_main(["--version"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "OpenAI TTS" in out
