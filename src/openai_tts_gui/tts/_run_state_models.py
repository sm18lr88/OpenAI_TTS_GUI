from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class ClosableResponse(Protocol):
    def close(self) -> None: ...


class FfmpegStopper(Protocol):
    def request_stop(self) -> None: ...


class RunPhase(StrEnum):
    RUNNING = "running"
    CANCELLING = "cancelling"
    PUBLISHING = "publishing"
    JOINING = "joining"
    TERMINAL = "terminal"


@dataclass(frozen=True, slots=True, order=True)
class AttemptKey:
    chunk_index: int
    attempt: int


@dataclass(frozen=True, slots=True)
class CancelActions:
    futures: tuple[Callable[[], bool], ...]
    responses: tuple[ClosableResponse, ...]
    ffmpeg: FfmpegStopper | None
