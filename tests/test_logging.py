from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

from openai_tts_gui import main
from openai_tts_gui.config.logging import (
    BoundedRotatingFileHandler,
    RedactingFormatter,
)


def _logger(handler: logging.Handler) -> logging.Logger:
    logger = logging.getLogger(f"task20.{id(handler)}")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    return logger


type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


class SyntheticTraceError(Exception):
    pass


def _records(path: Path) -> list[dict[str, JsonValue]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize("detail", ["ascii-" * 200, "雪" * 300])
def test_formatter_emits_bounded_parseable_redacted_records(detail: str) -> None:
    # Given: an oversized message, trace, and detail containing sensitive values.
    formatter = RedactingFormatter(max_record_bytes=360)
    record = logging.LogRecord(
        "task20",
        logging.ERROR,
        "D:/private/input.txt",
        1,
        "sk-task20-secret",
        (),
        None,
    )
    record.detail = detail
    record.message = "Bearer task20-token D:/private/input.txt"
    try:
        raise SyntheticTraceError("Traceback /private/input.txt sk-task20-secret")
    except SyntheticTraceError:
        record.exc_info = sys.exc_info()

    # When: the record is formatted.
    rendered = formatter.format(record)

    # Then: it remains valid UTF-8 JSON under the requested byte cap without secrets.
    parsed = json.loads(rendered)
    assert len(rendered.encode("utf-8")) <= 360
    assert parsed["schema"] == "openai_tts_gui.log.v1"
    assert parsed["truncated"] is True
    assert "sk-task20-secret" not in rendered
    assert "private/input.txt" not in rendered


def test_real_application_events_and_interpolation_remain_distinct_safe_and_bounded(
    tmp_path: Path, monkeypatch
) -> None:
    # Given: a real main entry-point run and a production-namespaced logger.
    path = tmp_path / "real-calls.log"
    handler = BoundedRotatingFileHandler(path, max_bytes=32_768, max_record_bytes=8_192)

    class Signal:
        def connect(self, _slot) -> None:
            return None

    class App:
        def __init__(self, _argv) -> None:
            self._ffmpeg_preflight_worker = None

        def exec(self) -> int:
            return 0

    class Window:
        def show(self) -> None:
            return None

    class MessageBox:
        @staticmethod
        def critical(*_args) -> None:
            return None

    class Worker:
        def __init__(self, _parent) -> None:
            self.preflight_finished = Signal()
            self.finished = Signal()

        def deleteLater(self) -> None:
            return None

        def start(self) -> None:
            return None

    monkeypatch.setattr(main, "configure_logging", lambda: None)
    monkeypatch.setattr(
        main,
        "_load_gui_symbols",
        lambda: (App, MessageBox, lambda _app: None, Window, Worker),
    )
    monkeypatch.setattr(main.logger, "handlers", [handler])
    monkeypatch.setattr(main.logger, "propagate", False)
    monkeypatch.setattr(main.logger, "level", logging.DEBUG)
    production_logger = logging.getLogger("openai_tts_gui.core.audio")
    monkeypatch.setattr(production_logger, "handlers", [handler])
    monkeypatch.setattr(production_logger, "propagate", False)
    production_logger.setLevel(logging.DEBUG)

    # When: production decision points and interpolated warning/error calls execute.
    assert main.run(["task20"]) == 0
    production_logger.warning(
        "retry %s at %s with %s",
        "雪" * 10_000,
        "D:/private/input.txt",
        "sk-task20-secret",
    )
    try:
        raise SyntheticTraceError("Bearer task20-token /private/input.txt")
    except SyntheticTraceError:
        production_logger.exception("request failure for %s", "D:/private/input.txt")
    handler.close()

    # Then: actual entry-point events are distinct while rendered records stay safe and bounded.
    records = _records(path)
    events = {record["event"] for record in records}
    rendered = path.read_text(encoding="utf-8")
    assert {"gui.application.start", "gui.window.displayed", "gui.application.exit"} <= events
    assert all(len(line.encode("utf-8")) <= 8_192 for line in rendered.splitlines())
    assert "sk-task20-secret" not in rendered
    assert "private/input.txt" not in rendered
    messages = [value for record in records if isinstance(value := record.get("message"), str)]
    traces = [value for record in records if isinstance(value := record.get("trace"), str)]
    assert any(message.startswith("retry ") for message in messages)
    assert any("SyntheticTraceError" in trace for trace in traces)


def test_handler_rotates_before_overflow_and_only_persists_safe_fields(tmp_path: Path) -> None:
    # Given: a tiny bounded log with a secret and an absolute path in optional detail.
    path = tmp_path / "gui.log"
    handler = BoundedRotatingFileHandler(path, max_bytes=500, max_record_bytes=240)
    logger = _logger(handler)

    # When: enough records are emitted to force rotation.
    for count in range(12):
        logger.info(
            "untrusted %s",
            "sk-task20-secret",
            extra={
                "event": "gui.generate.completed",
                "count": count,
                "detail": "D:/private/input.txt " + ("雪" * 100),
                "basename": "D:/private/output.mp3",
            },
        )
    handler.close()

    # Then: current and backup are bounded JSON records without unsafe fields.
    backup = Path(f"{path}.1")
    assert path.stat().st_size <= 500
    assert not backup.exists() or backup.stat().st_size <= 500
    assert path.stat().st_size + (backup.stat().st_size if backup.exists() else 0) <= 1000
    rendered = "\n".join(
        path.read_text(encoding="utf-8")
        + (backup.read_text(encoding="utf-8") if backup.exists() else "")
    )
    assert "sk-task20-secret" not in rendered
    assert "D:/private/input.txt" not in rendered
    assert _records(path)
    assert all(record["schema"] == "openai_tts_gui.log.v1" for record in _records(path))


@pytest.mark.parametrize("name", ["gui.log", "gui.log.1"])
def test_handler_preserves_legacy_and_oversized_managed_bytes_before_writing(
    tmp_path: Path, name: str
) -> None:
    # Given: a legacy current/backup or oversized schema-marked log.
    path = tmp_path / "gui.log"
    source = tmp_path / name
    contents = (
        b"legacy-bytes\xff" if name == "gui.log.1" else b'{"schema":"openai_tts_gui.log.v1"}\n' * 30
    )
    source.write_bytes(contents)
    original_hash = hashlib.sha256(contents).hexdigest()

    # When: bounded logging starts and writes its first record.
    handler = BoundedRotatingFileHandler(path, max_bytes=300, max_record_bytes=200)
    _logger(handler).info("ignored", extra={"event": "gui.started"})
    handler.close()

    # Then: original bytes are preserved exactly under a unique legacy name.
    preserved = list(tmp_path.glob(f"{name}.legacy-*.preserved"))
    assert len(preserved) == 1
    assert hashlib.sha256(preserved[0].read_bytes()).hexdigest() == original_hash
    assert _records(path)


def test_handler_migrates_both_unmarked_current_and_backup_on_first_start(tmp_path: Path) -> None:
    # Given: legacy bytes in both managed locations.
    path = tmp_path / "gui.log"
    path.write_bytes(b"old-current")
    backup = Path(f"{path}.1")
    backup.write_bytes(b"old-backup")

    # When: bounded logging initializes.
    handler = BoundedRotatingFileHandler(path, max_bytes=400, max_record_bytes=240)
    _logger(handler).info("ignored", extra={"event": "gui.started"})
    handler.close()

    # Then: both legacy streams survive byte-for-byte and a fresh schema log is created.
    preserved = list(tmp_path.glob("gui.log*.legacy-*.preserved"))
    assert {item.read_bytes() for item in preserved} == {b"old-current", b"old-backup"}
    assert _records(path)


def test_two_subprocess_writers_keep_cooperating_pair_bounded_and_parseable(tmp_path: Path) -> None:
    # Given: two real Python processes using the same handler path.
    path = tmp_path / "shared.log"
    root = Path(__file__).resolve().parents[1]
    code = """
import logging
import sys
from openai_tts_gui.config.logging import BoundedRotatingFileHandler
path = sys.argv[1]
handler = BoundedRotatingFileHandler(path, max_bytes=700, max_record_bytes=240)
logger = logging.getLogger('task20.subprocess')
logger.handlers.clear()
logger.propagate = False
logger.addHandler(handler)
logger.setLevel(logging.INFO)
for index in range(30):
    logger.info(
        'ignored',
        extra={'event': 'gui.writer.record', 'count': index, 'detail': '雪' * 80},
    )
handler.close()
"""
    environment = os.environ | {"PYTHONPATH": str(root / "src")}

    # When: both writers run concurrently and exit.
    first = subprocess.Popen([sys.executable, "-c", code, str(path)], env=environment)
    second = subprocess.Popen([sys.executable, "-c", code, str(path)], env=environment)
    assert first.wait(timeout=20) == 0
    assert second.wait(timeout=20) == 0

    # Then: all surviving cooperating records parse and the pair remains bounded.
    backup = Path(f"{path}.1")
    assert path.stat().st_size <= 700
    assert not backup.exists() or backup.stat().st_size <= 700
    assert path.stat().st_size + (backup.stat().st_size if backup.exists() else 0) <= 1400
    assert _records(path)
    assert all(record["schema"] == "openai_tts_gui.log.v1" for record in _records(path))


def test_noncooperating_writes_do_not_create_a_false_global_bound_claim(tmp_path: Path) -> None:
    # Given: a valid bounded log owned by this handler.
    path = tmp_path / "foreign.log"
    handler = BoundedRotatingFileHandler(path, max_bytes=300, max_record_bytes=200)
    _logger(handler).info("ignored", extra={"event": "gui.write"})
    handler.close()

    # When: an uncooperating writer appends outside the handler protocol.
    with path.open("ab") as stream:
        stream.write(b"foreign" * 100)

    # Then: the filesystem can exceed the cooperative bound; no global invariant is asserted.
    assert path.stat().st_size > 300


def test_cli_failure_stays_on_stderr_without_traceback(tmp_path: Path) -> None:
    # Given: a CLI input that cannot be decoded as UTF-8.
    source = tmp_path / "invalid.txt"
    source.write_bytes(b"\xff")
    environment = os.environ | {"OPENAI_API_KEY": "sk-task20-secret"}

    # When: the public CLI module is driven through a subprocess.
    completed = subprocess.run(
        [sys.executable, "-m", "openai_tts_gui.cli", "--in", str(source), "--out", "out.mp3"],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: diagnostics are stderr-only and never include a traceback or the key.
    assert completed.returncode == 1
    assert completed.stdout == ""
    assert "Failed to read input file:" in completed.stderr
    assert "Traceback" not in completed.stderr
    assert "sk-task20-secret" not in completed.stderr
