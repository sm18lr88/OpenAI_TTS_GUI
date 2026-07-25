from __future__ import annotations

import hashlib
import importlib
import json
import logging
import os
import re
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, Final

from ..errors import LoggingConfigurationError

if sys.platform == "win32":
    import msvcrt

LOG_SCHEMA: Final[str] = "openai_tts_gui.log.v1"
GUI_LOG_MAX_BYTES: Final[int] = 262_144
GUI_LOG_MAX_RECORD_BYTES: Final[int] = 8_192
_SECRET_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?ix)\b(?:sk-[a-z0-9_-]{6,}|bearer\s+\S+|(?:api[-_ ]?key|authorization|cookie)\s*[:=]\s*\S+)"
)
_PATH_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?:(?:[a-z]:[\\/]|/)[^\s\"']+)", re.IGNORECASE)
_SAFE_EVENT_PATTERN: Final[re.Pattern[str]] = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}")
_WARNING_LOCK = threading.Lock()
_DISABLED_PATHS: set[str] = set()
_WARNED_PATHS: set[str] = set()
type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


def _truncate_utf8(value: str, byte_limit: int) -> tuple[str, bool]:
    encoded = value.encode("utf-8")
    if len(encoded) <= byte_limit:
        return value, False
    return encoded[: max(0, byte_limit)].decode("utf-8", errors="ignore"), True


def _redact(value: str) -> str:
    return _PATH_PATTERN.sub("<path>", _SECRET_PATTERN.sub("<redacted>", value))


def _record_string(record: logging.LogRecord, name: str) -> str | None:
    value = record.__dict__.get(name)
    return value if isinstance(value, str) else None


class RedactingFormatter(logging.Formatter):
    """Render only schema-approved logging fields as a bounded JSON record."""

    def __init__(self, max_record_bytes: int, *, include_trace: bool = True) -> None:
        super().__init__()
        if max_record_bytes < 128:
            raise LoggingConfigurationError("max_record_bytes must be at least 128")
        self._max_record_bytes = max_record_bytes
        self._include_trace = include_trace

    def format(self, record: logging.LogRecord) -> str:
        fields = self._safe_fields(record)
        payload: dict[str, JsonValue] = {
            "schema": LOG_SCHEMA,
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": _truncate_utf8(_redact(record.name), 64)[0],
            "event": self._event(record),
            "fields": fields,
            "truncated": False,
        }
        message = self._message(record)
        if message:
            payload["message"] = _redact(message)
        for name in ("detail",):
            value = _record_string(record, name)
            if value is not None:
                payload[name] = _redact(value)
        if self._include_trace and record.exc_info:
            payload["trace"] = _redact(self.formatException(record.exc_info))
        return self._fit(payload)

    @staticmethod
    def _message(record: logging.LogRecord) -> str:
        try:
            return record.getMessage()
        except (KeyError, TypeError, ValueError):
            return "<message-format-error>"

    def _event(self, record: logging.LogRecord) -> str:
        event = _record_string(record, "event")
        if event is not None and _SAFE_EVENT_PATTERN.fullmatch(event):
            return event
        return "application.log"

    def _safe_fields(self, record: logging.LogRecord) -> dict[str, JsonValue]:
        fields: dict[str, JsonValue] = {}
        for name in ("outcome", "request_id", "model", "path_role"):
            value = _record_string(record, name)
            if value is not None:
                fields[name] = _truncate_utf8(_redact(value), 64)[0]
        for name in ("chunk", "count", "client_attempt"):
            value = record.__dict__.get(name)
            if type(value) is int and value >= 0:
                fields[name] = value
        basename = _record_string(record, "basename")
        if basename is not None:
            fields["basename"] = _truncate_utf8(
                _redact(basename.replace("\\", "/").rsplit("/", 1)[-1]), 96
            )[0]
        return fields

    def _fit(self, payload: dict[str, JsonValue]) -> str:
        rendered = self._render(payload)
        while len(rendered.encode("utf-8")) > self._max_record_bytes:
            payload["truncated"] = True
            for name in ("trace", "detail", "message", "logger", "event"):
                value = payload.get(name)
                if isinstance(value, str) and value:
                    excess = len(rendered.encode("utf-8")) - self._max_record_bytes
                    limited, _ = _truncate_utf8(value, len(value.encode("utf-8")) - excess - 1)
                    if limited:
                        payload[name] = limited
                    else:
                        payload.pop(name)
                    break
            else:
                payload["fields"] = {}
            rendered = self._render(payload)
        return rendered

    @staticmethod
    def _render(payload: dict[str, JsonValue]) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


class BoundedRotatingFileHandler(logging.Handler):
    """Write schema records with a short cross-process lock for each operation."""

    def __init__(
        self,
        filename: str | Path,
        max_bytes: int = GUI_LOG_MAX_BYTES,
        max_record_bytes: int = GUI_LOG_MAX_RECORD_BYTES,
        lock_timeout: float = 0.5,
    ) -> None:
        super().__init__()
        if max_record_bytes > max_bytes or max_record_bytes < 200 or lock_timeout <= 0:
            raise LoggingConfigurationError("invalid bounded logging limits")
        self._path = Path(filename)
        self._backup_path = Path(f"{self._path}.1")
        self._lock_path = Path(f"{self._path}.lock")
        self._max_bytes = max_bytes
        self._lock_timeout = lock_timeout
        self._initialized = False
        self._formatter = RedactingFormatter(max_record_bytes - 1)
        self.setFormatter(self._formatter)

    def emit(self, record: logging.LogRecord) -> None:
        if self._is_disabled():
            return
        encoded = (self._formatter.format(record) + "\n").encode("utf-8")
        try:
            with self._exclusive_lock():
                if not self._initialized:
                    self._prepare_files()
                    self._initialized = True
                self._rotate_before_write(len(encoded))
                with self._path.open("ab") as stream:
                    stream.write(encoded)
        except (OSError, TimeoutError):
            self._disable()

    def _is_disabled(self) -> bool:
        with _WARNING_LOCK:
            return str(self._path) in _DISABLED_PATHS

    def _disable(self) -> None:
        path_key = str(self._path)
        with _WARNING_LOCK:
            _DISABLED_PATHS.add(path_key)
            if path_key in _WARNED_PATHS:
                return
            _WARNED_PATHS.add(path_key)
        try:
            sys.stderr.write("openai_tts_gui: file logging disabled (lock unavailable)\n")
        except OSError:
            return

    @contextmanager
    def _exclusive_lock(self) -> Iterator[None]:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock_path.open("a+b") as stream:
            stream.seek(0)
            if stream.read(1) == b"":
                stream.write(b"\0")
                stream.flush()
            deadline = time.monotonic() + self._lock_timeout
            while True:
                try:
                    self._try_lock(stream)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError from None
                    time.sleep(0.01)
            try:
                yield
            finally:
                self._unlock(stream)

    @staticmethod
    def _try_lock(stream: BinaryIO) -> None:
        stream.seek(0)
        if sys.platform == "win32":
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            _fcntl_lock(stream, "LOCK_EX", "LOCK_NB")

    @staticmethod
    def _unlock(stream: BinaryIO) -> None:
        stream.seek(0)
        if sys.platform == "win32":
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            _fcntl_lock(stream, "LOCK_UN")

    def _prepare_files(self) -> None:
        for path in (self._path, self._backup_path):
            if path.exists() and (
                path.stat().st_size > self._max_bytes or not self._is_managed(path)
            ):
                self._preserve(path)

    @staticmethod
    def _is_managed(path: Path) -> bool:
        try:
            for line in path.read_bytes().splitlines():
                if not line:
                    continue
                item = json.loads(line)
                if not isinstance(item, dict) or item.get("schema") != LOG_SCHEMA:
                    return False
        except (json.JSONDecodeError, UnicodeDecodeError):
            return False
        return True

    def _preserve(self, path: Path) -> None:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        candidate = path.with_name(f"{path.name}.legacy-{stamp}-{digest}.preserved")
        index = 1
        while candidate.exists():
            candidate = path.with_name(f"{path.name}.legacy-{stamp}-{digest}-{index}.preserved")
            index += 1
        os.replace(path, candidate)

    def _rotate_before_write(self, record_size: int) -> None:
        current_size = self._path.stat().st_size if self._path.exists() else 0
        if current_size + record_size > self._max_bytes and self._path.exists():
            os.replace(self._path, self._backup_path)


def configure_cli_logging(level: int) -> logging.Handler:
    """Route sanitized CLI diagnostics to stderr without exception traces."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(RedactingFormatter(GUI_LOG_MAX_RECORD_BYTES, include_trace=False))
    logging.basicConfig(level=level, handlers=[handler], force=True)
    return handler


def _fcntl_lock(stream: BinaryIO, *commands: str) -> None:
    fcntl = importlib.import_module("fcntl")
    command = 0
    for name in commands:
        command |= int(getattr(fcntl, name))
    getattr(fcntl, "".join(("f", "lock")))(stream.fileno(), command)
