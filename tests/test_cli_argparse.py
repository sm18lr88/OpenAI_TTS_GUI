import pytest

from openai_tts_gui import config
from openai_tts_gui.cli import main as cli_main


def test_cli_version_exits_zero():
    assert cli_main(["--version"]) == 0


def test_cli_missing_key_returns_1(monkeypatch, tmp_path):
    # Force missing key
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("openai_tts_gui.cli.read_api_key", lambda: None)
    infile = tmp_path / "in.txt"
    infile.write_text("hello", encoding="utf-8")
    outfile = tmp_path / "out.mp3"
    rc = cli_main(["--in", str(infile), "--out", str(outfile)])
    assert rc == 1


def test_cli_invalid_speed_returns_2(monkeypatch, tmp_path):
    infile = tmp_path / "in.txt"
    infile.write_text("hello", encoding="utf-8")
    outfile = tmp_path / "out.mp3"
    monkeypatch.setattr("openai_tts_gui.cli.read_api_key", lambda: "sk-test")
    rc = cli_main(["--in", str(infile), "--out", str(outfile), "--speed", "99"])
    assert rc == 2


def test_cli_help_documents_tts_option_sections(capsys):
    with pytest.raises(SystemExit) as exc_info:
        cli_main(["--help"])

    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    normalized_out = " ".join(out.split())
    assert "Input/output:" in out
    assert "TTS options:" in out
    assert "Runtime options:" in out
    assert "--model" in out
    assert ", ".join(config.TTS_MODELS) in normalized_out
    assert "--voice" in out
    assert ", ".join(config.TTS_VOICES) in normalized_out
    assert "--format" in out
    assert ", ".join(config.TTS_FORMATS) in normalized_out
    assert "--speed" in out
    assert "--instructions" in out
    assert f"{config.MIN_SPEED}" in out
    assert f"{config.MAX_SPEED}" in out
