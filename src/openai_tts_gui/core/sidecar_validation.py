from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from ..errors import ValidationError

_ENVIRONMENT_FIELDS: Final[frozenset[str]] = frozenset(
    {"app_name", "app_version", "python", "platform", "openai", "pyqt6"}
)
_RETRY_HEADERS: Final[frozenset[str]] = frozenset({"retry-after-ms", "retry-after"})
_WINDOWS_DEVICE_NAMES: Final[frozenset[str]] = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
)


@dataclass(frozen=True, slots=True)
class SidecarParseError(ValidationError):
    reason: str

    def __str__(self) -> str:
        return f"Invalid sidecar metadata: {self.reason}."


def safe_environment(environment: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    entries = tuple(sorted(environment.items()))
    if not set(environment).issubset(_ENVIRONMENT_FIELDS):
        raise SidecarParseError("environment fields are not approved")
    for _, value in entries:
        if basename(value) != value:
            raise SidecarParseError("environment field must not be an absolute path")
    return entries


def safe_retry_headers(headers: Mapping[str, str] | None) -> tuple[tuple[str, str], ...] | None:
    if headers is None:
        return None
    if not set(headers).issubset(_RETRY_HEADERS):
        raise SidecarParseError("retry headers are not approved")
    return tuple(sorted(headers.items()))


def basename(path: str | Path) -> str:
    name = str(path).replace("\\", "/").rsplit("/", 1)[-1]
    _validate_portable_name(name)
    return name


def _validate_portable_name(name: str) -> None:
    device_name = name.split(".", 1)[0].upper()
    if (
        not name
        or name in {".", ".."}
        or ":" in name
        or name.rstrip(". ") != name
        or device_name in _WINDOWS_DEVICE_NAMES
    ):
        raise SidecarParseError("path must have a portable basename")
