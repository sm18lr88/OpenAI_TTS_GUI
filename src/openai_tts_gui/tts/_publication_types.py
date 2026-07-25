from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..errors import CanonicalState, FinalizationReport, PublicationFailureReason
from ._publication_plan import ChunkRequestMeta, PublicationPlan

if TYPE_CHECKING:
    from ._outcomes import CancellationStage, PublicationInProgress


@dataclass(frozen=True, slots=True)
class PublicationRequest:
    text: str
    model: str
    voice: str
    response_format: str
    speed: float
    instructions: str


@dataclass(frozen=True, slots=True)
class PublicationPayload:
    plan: PublicationPlan
    request: PublicationRequest
    metadata: list[ChunkRequestMeta]
    begin_publication: Callable[[], CancellationStage | PublicationInProgress]
    on_publication_started: Callable[[], None]


@dataclass(frozen=True, slots=True)
class PublicationDependencies:
    concatenate: Callable[[list[str], str], str | None]
    write_sidecar: Callable[..., str | None]


@dataclass(frozen=True, slots=True)
class PublicationCommit:
    message: str
    finalization: FinalizationReport


__all__ = [
    "CanonicalState",
    "FinalizationReport",
    "PublicationCommit",
    "PublicationDependencies",
    "PublicationFailureReason",
    "PublicationPayload",
    "PublicationRequest",
]
