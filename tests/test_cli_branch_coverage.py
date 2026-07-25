from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

from openai_tts_gui import cli
from openai_tts_gui.errors import ConfigError, TTSError
from openai_tts_gui.keystore import (
    KeyringCredential,
    MissingCredential,
    StaleLegacyCredentialWarning,
)


class UnexpectedCliServiceFailure(Exception):
    pass


@pytest.mark.parametrize(
    ("arguments", "expected_exit", "output_name"),
    [
        (["--help"], 0, "stdout"),
        (["--version"], 0, "stdout"),
        ([], 2, "stderr"),
        (["--speed", "not-a-number"], 2, "stderr"),
    ],
)
def test_cli_subprocess_handles_public_parser_paths(arguments, expected_exit, output_name):
    given_environment = os.environ.copy()
    given_environment.pop("OPENAI_API_KEY", None)

    when_completed = subprocess.run(
        [sys.executable, "-m", "openai_tts_gui.cli", *arguments],
        capture_output=True,
        check=False,
        cwd=Path(__file__).resolve().parents[1],
        env=given_environment,
        text=True,
    )

    then_output = getattr(when_completed, output_name)
    assert when_completed.returncode == expected_exit
    assert "usage:" in then_output.lower() or expected_exit == 0


def test_cli_in_process_version_uses_early_exit(monkeypatch, capsys):
    monkeypatch.setattr(cli.settings, "ensure_directories", lambda: None)

    when_result = cli.main(["--version"])

    assert when_result == 0
    assert cli.settings.APP_NAME in capsys.readouterr().out


def test_cli_in_process_missing_paths_prints_usage(monkeypatch, capsys):
    monkeypatch.setattr(cli.settings, "ensure_directories", lambda: None)

    when_result = cli.main([])

    assert when_result == 2
    assert "usage:" in capsys.readouterr().err.lower()


@pytest.mark.parametrize(
    ("filename", "contents"),
    [("missing.txt", None), ("invalid-utf8.txt", b"\xff")],
)
def test_cli_subprocess_reports_bad_text_input(filename, contents, tmp_path):
    given_input = tmp_path / filename
    if contents is not None:
        given_input.write_bytes(contents)
    given_environment = os.environ | {"OPENAI_API_KEY": "sk-local-test"}

    when_completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "openai_tts_gui.cli",
            "--in",
            str(given_input),
            "--out",
            str(tmp_path / "output.mp3"),
        ],
        capture_output=True,
        check=False,
        cwd=Path(__file__).resolve().parents[1],
        env=given_environment,
        text=True,
        errors="replace",
    )

    assert when_completed.returncode == 1
    assert "Failed to read input file:" in when_completed.stderr


@pytest.mark.parametrize(
    "speed_arguments",
    [
        ("--speed", "nan"),
        ("--speed", "inf"),
        ("--speed=-inf",),
        ("--speed", "0.24"),
        ("--speed", "4.01"),
    ],
)
def test_cli_rejects_nonfinite_and_out_of_range_speed(
    speed_arguments, tmp_path, monkeypatch, capsys
):
    given_input = tmp_path / "input.txt"
    given_input.write_text("text", encoding="utf-8")
    monkeypatch.setattr(cli.settings, "ensure_directories", lambda: None)

    when_result = cli.main(
        ["--in", str(given_input), "--out", str(tmp_path / "out.mp3"), *speed_arguments]
    )

    assert when_result == 2
    assert "Invalid speed:" in capsys.readouterr().err


def test_cli_translates_missing_key_and_unreadable_input(tmp_path, monkeypatch, capsys):
    given_input = tmp_path / "input.txt"
    given_input.write_text("text", encoding="utf-8")
    monkeypatch.setattr(cli.settings, "ensure_directories", lambda: None)
    monkeypatch.setattr(cli, "read_api_key_outcome", MissingCredential)

    when_missing_key = cli.main(["--in", str(given_input), "--out", str(tmp_path / "out.mp3")])

    assert when_missing_key == 1
    assert "Missing OPENAI API key." in capsys.readouterr().err

    def reject_read(*_arguments, **_keywords):
        raise OSError("access denied")

    monkeypatch.setattr(cli, "read_api_key_outcome", lambda: KeyringCredential("sk-local-test"))
    monkeypatch.setattr(cli.Path, "read_text", reject_read)

    when_unreadable = cli.main(["--in", str(given_input), "--out", str(tmp_path / "out.mp3")])

    assert when_unreadable == 1
    assert "Failed to read input file:" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("failure", "expected_exit", "error_category"),
    [(ConfigError("invalid"), 2, "Invalid configuration:"), (TTSError("failed"), 1, "TTS failed:")],
)
def test_cli_translates_domain_service_failures(
    failure, expected_exit, error_category, tmp_path, monkeypatch, capsys
):
    given_input = tmp_path / "input.txt"
    given_input.write_text("text", encoding="utf-8")

    class FailingService:
        def __init__(self, **_kwargs):
            pass

        def generate(self, **_kwargs):
            raise failure

    monkeypatch.setattr(cli.settings, "ensure_directories", lambda: None)
    monkeypatch.setattr(cli, "read_api_key_outcome", lambda: KeyringCredential("sk-local-test"))
    monkeypatch.setattr(cli, "_load_tts_service", lambda: FailingService)

    when_result = cli.main(["--in", str(given_input), "--out", str(tmp_path / "out.mp3")])

    assert when_result == expected_exit
    assert error_category in capsys.readouterr().err


def test_cli_preserves_unexpected_service_failures(tmp_path, monkeypatch):
    given_input = tmp_path / "input.txt"
    given_input.write_text("text", encoding="utf-8")

    class UnexpectedService:
        def __init__(self, **_kwargs):
            pass

        def generate(self, **_kwargs):
            raise UnexpectedCliServiceFailure

    monkeypatch.setattr(cli.settings, "ensure_directories", lambda: None)
    monkeypatch.setattr(cli, "read_api_key_outcome", lambda: KeyringCredential("sk-local-test"))
    monkeypatch.setattr(cli, "_load_tts_service", lambda: UnexpectedService)

    with pytest.raises(UnexpectedCliServiceFailure):
        cli.main(["--in", str(given_input), "--out", str(tmp_path / "out.mp3")])


def test_cli_writes_output_for_retain_files_and_emits_service_log(tmp_path, monkeypatch, capsys):
    given_input = tmp_path / "input.txt"
    given_output = tmp_path / "nested" / "output.wav"
    given_input.write_text("text", encoding="utf-8")
    captured = {}

    class WritingService:
        def __init__(self, **_kwargs):
            pass

        def generate(self, **kwargs):
            captured.update(kwargs)
            Path(str(kwargs["output_path"])).parent.mkdir(parents=True, exist_ok=True)
            Path(str(kwargs["output_path"])).write_bytes(b"audio")
            logging.getLogger("cli-coverage").warning("service-log")

    monkeypatch.setattr(cli.settings, "ensure_directories", lambda: None)
    monkeypatch.setattr(cli, "read_api_key_outcome", lambda: KeyringCredential("sk-local-test"))
    monkeypatch.setattr(cli, "_load_tts_service", lambda: WritingService)

    when_result = cli.main(
        [
            "--in",
            str(given_input),
            "--out",
            str(given_output),
            "--retain-files",
            "--log-level",
            "DEBUG",
        ]
    )

    assert when_result == 0
    assert given_output.read_bytes() == b"audio"
    assert captured["retain_files"] is True
    diagnostic = json.loads(capsys.readouterr().err)
    assert diagnostic["event"] == "application.log"
    assert diagnostic["message"] == "service-log"


def test_cli_releases_its_configured_root_handler_after_completion(tmp_path, monkeypatch) -> None:
    given_input = tmp_path / "input.txt"
    given_output = tmp_path / "output.mp3"
    given_input.write_text("text", encoding="utf-8")

    class WritingService:
        def __init__(self, **_kwargs) -> None:
            pass

        def generate(self, **_kwargs) -> str:
            given_output.write_bytes(b"audio")
            return "saved"

    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    root_logger.handlers.clear()
    monkeypatch.setattr(cli.settings, "ensure_directories", lambda: None)
    monkeypatch.setattr(cli, "read_api_key_outcome", lambda: KeyringCredential("sk-local-test"))
    monkeypatch.setattr(cli, "_load_tts_service", lambda: WritingService)
    try:
        when_result = cli.main(["--in", str(given_input), "--out", str(given_output)])

        assert when_result == 0
        assert root_logger.handlers == []
    finally:
        for handler in root_logger.handlers:
            handler.close()
        root_logger.handlers[:] = original_handlers


def test_cli_reports_stale_legacy_credential_cleanup_once_without_sensitive_data(
    tmp_path, monkeypatch, capsys
) -> None:
    given_input = tmp_path / "input.txt"
    given_output = tmp_path / "output.mp3"
    given_input.write_text("text", encoding="utf-8")

    class WritingService:
        def __init__(self, **_kwargs) -> None:
            pass

        def generate(self, **_kwargs) -> str:
            given_output.write_bytes(b"audio")
            return "saved"

    monkeypatch.setattr(cli.settings, "ensure_directories", lambda: None)
    monkeypatch.setattr(
        cli,
        "read_api_key_outcome",
        lambda: KeyringCredential(
            "synthetic-credential",
            (StaleLegacyCredentialWarning(),),
        ),
    )
    monkeypatch.setattr(cli, "_load_tts_service", lambda: WritingService)

    when_result = cli.main(["--in", str(given_input), "--out", str(given_output)])

    then_records = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    cleanup_records = [
        record for record in then_records if record["event"] == "credential.legacy_cleanup_required"
    ]
    assert when_result == 0
    assert len(cleanup_records) == 1
    assert cleanup_records[0]["fields"] == {"outcome": "stale_legacy_credential"}
    assert "synthetic-credential" not in json.dumps(cleanup_records)
    assert str(tmp_path) not in json.dumps(cleanup_records)
