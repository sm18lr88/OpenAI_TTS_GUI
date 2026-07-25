from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..errors import CleanupReport


@dataclass(frozen=True, slots=True)
class ExecutionDependencies:
    preflight: Callable[[], str]
    split_text: Callable[[str, int], list[str]]
    concatenate: Callable[[list[str], str], str | None]
    cleanup: Callable[[list[str]], CleanupReport | None]
    write_sidecar: Callable[..., str | None]
    hash_text: Callable[[str], str]
