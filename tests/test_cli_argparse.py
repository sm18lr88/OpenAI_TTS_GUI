from cli import main as cli_main


def test_cli_version_exits_zero():
    assert cli_main(["--version"]) == 0


def test_cli_missing_key_returns_1(monkeypatch, tmp_path):
    # Force missing key
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("utils.read_api_key", lambda: None)
    infile = tmp_path / "in.txt"
    infile.write_text("hello", encoding="utf-8")
    outfile = tmp_path / "out.mp3"
    rc = cli_main(["--in", str(infile), "--out", str(outfile)])
    assert rc == 1
