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


def test_cli_version_early_parse_ok(capsys):
    rc = cli_main(["--version"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "OpenAI TTS" in out
