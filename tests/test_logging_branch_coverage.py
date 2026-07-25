from __future__ import annotations

import json
import logging
import subprocess
import sys
from datetime import UTC, datetime, tzinfo
from pathlib import Path

import pytest

from openai_tts_gui.config import LoggingConfigurationError
from openai_tts_gui.config import logging as logging_module
from openai_tts_gui.config.logging import BoundedRotatingFileHandler, RedactingFormatter


def _logger(handler: logging.Handler) -> logging.Logger:
    logger = logging.getLogger(f"task20.branch.{id(handler)}")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    return logger


def test_logging_configuration_rejects_invalid_bounded_limits() -> None:
    with pytest.raises(LoggingConfigurationError):
        RedactingFormatter(max_record_bytes=127)
    with pytest.raises(LoggingConfigurationError):
        BoundedRotatingFileHandler("gui.log", max_bytes=199, max_record_bytes=200)


@pytest.mark.parametrize(
    ("content", "managed"),
    [
        (b"", True),
        (b"\n", True),
        (b'{"schema":"openai_tts_gui.log.v1"}\n\n', True),
        (b"[]\n", False),
        (b'{"schema":"other"}\n', False),
        (b"{\n", False),
    ],
)
def test_handler_classifies_managed_log_bytes(
    content: bytes, managed: bool, tmp_path: Path
) -> None:
    path = tmp_path / "gui.log"
    path.write_bytes(content)

    assert BoundedRotatingFileHandler._is_managed(path) is managed


def test_formatter_preserves_only_typed_approved_fields() -> None:
    formatter = RedactingFormatter(max_record_bytes=256)
    record = logging.LogRecord("task20", logging.INFO, "logging.py", 1, "ignored", (), None)
    record.outcome = "accepted"
    record.chunk = "not-an-integer"

    rendered = formatter.format(record)

    assert json.loads(rendered)["fields"] == {"outcome": "accepted"}


def test_formatter_discards_untyped_fields_when_shrinking_a_minimum_record() -> None:
    formatter = RedactingFormatter(max_record_bytes=128)
    record = logging.LogRecord("x" * 500, logging.INFO, "logging.py", 1, "ignored", (), None)
    record.chunk = "not-an-integer"

    rendered = formatter.format(record)

    assert len(rendered.encode("utf-8")) <= 128
    assert json.loads(rendered)["fields"] == {}


def test_handler_retries_a_transient_lock_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler = BoundedRotatingFileHandler(
        tmp_path / "retry.log", max_bytes=400, max_record_bytes=240
    )
    attempts = 0

    def lock_after_one_conflict(_stream) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("transient lock conflict")

    monkeypatch.setattr(handler, "_try_lock", lock_after_one_conflict)
    monkeypatch.setattr(handler, "_unlock", lambda _stream: None)

    with handler._exclusive_lock():
        pass

    assert attempts == 2


def test_handler_disables_when_stderr_cannot_report_lock_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailingStderr:
        def write(self, _message: str) -> None:
            raise OSError("stderr unavailable")

    handler = BoundedRotatingFileHandler(
        tmp_path / "stderr.log", max_bytes=400, max_record_bytes=240
    )
    monkeypatch.setattr(logging_module.sys, "stderr", FailingStderr())

    handler._disable()

    assert handler._is_disabled()


def test_handler_preserves_a_second_collision_with_an_incremented_suffix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FixedDatetime:
        @staticmethod
        def now(_timezone: tzinfo | None) -> datetime:
            return datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)

    path = tmp_path / "gui.log"
    path.write_bytes(b"x")
    preserved = tmp_path / "gui.log.legacy-20260102T030405000000Z-2d711642b726b044.preserved"
    preserved.write_bytes(b"existing")
    monkeypatch.setattr(logging_module, "datetime", FixedDatetime)
    handler = BoundedRotatingFileHandler(path, max_bytes=400, max_record_bytes=240)

    handler._preserve(path)

    assert not path.exists()
    assert (
        tmp_path / f"{preserved.name.removesuffix('.preserved')}-1.preserved"
    ).read_bytes() == b"x"


def test_locked_handler_disables_without_managed_write_and_warns_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "locked.log"
    handler = BoundedRotatingFileHandler(
        path, max_bytes=400, max_record_bytes=240, lock_timeout=0.01
    )
    code = """
import os
import sys
import time
from pathlib import Path
stream = Path(sys.argv[1]).open('a+b')
stream.write(b'\\0')
stream.flush()
stream.seek(0)
if os.name == 'nt':
    import msvcrt
    msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
else:
    import fcntl
    fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
print('locked', flush=True)
time.sleep(1)
"""
    with subprocess.Popen(
        [sys.executable, "-c", code, str(Path(f"{path}.lock"))],
        stdout=subprocess.PIPE,
        text=True,
    ) as holder:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "locked"
        logger = _logger(handler)
        logger.info("ignored", extra={"event": "gui.write"})
        logger.info("ignored", extra={"event": "gui.write"})
        assert holder.wait(timeout=5) == 0
    handler._disable()
    handler._disable()
    handler.close()

    captured = capsys.readouterr().err
    assert not path.exists()
    assert captured.count("file logging disabled") == 1
    assert "Traceback" not in captured
