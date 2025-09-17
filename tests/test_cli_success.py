from pathlib import Path

from cli import main as cli_main


def test_cli_happy_path(monkeypatch, tmp_path):
    infile = tmp_path / "in.txt"
    outfile = tmp_path / "out.mp3"
    infile.write_text("hello world", encoding="utf-8")

    # Pretend we have a valid API key
    monkeypatch.setattr("utils.read_api_key", lambda: "sk-test-123")

    # Stub the TTSProcessor to avoid network and to create an output file
    class DummyTP:
        def __init__(self, params):
            self.params = params

        def run(self):
            Path(self.params["output_path"]).parent.mkdir(parents=True, exist_ok=True)
            Path(self.params["output_path"]).write_bytes(b"fake-audio")

    monkeypatch.setattr("cli.TTSProcessor", DummyTP)

    rc = cli_main(["--in", str(infile), "--out", str(outfile)])
    assert rc == 0
    assert outfile.exists()


def test_cli_version_early_parse_ok(capsys):
    # Ensure --version path is handled even without --in/--out
    rc = cli_main(["--version"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "OpenAI TTS" in out
