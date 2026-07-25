from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..errors import ContractError
from ._publication_types import CanonicalState, FinalizationReport, PublicationFailureReason


class CancellationStage(StrEnum):
    NONE = "none"
    BEFORE_REQUEST = "before_request"
    AWAITING_PROVIDER_RESPONSE = "awaiting_provider_response"
    DURING_PROVIDER_STREAM = "during_provider_stream"
    DURING_RETRY_WAIT = "during_retry_wait"
    BETWEEN_CHUNKS = "between_chunks"
    DURING_FFMPEG = "during_ffmpeg"
    BEFORE_PUBLICATION = "before_publication"


@dataclass(frozen=True, slots=True)
class PublicationInProgress:
    pass


@dataclass(frozen=True, slots=True)
class RunAccounting:
    planned_chunks: int
    planned_initial_requests: int
    client_attempts_started: int
    completed_chunks: int
    request_ids: tuple[str, ...]
    uncertain_indexes: tuple[int, ...]
    cancellation_stage: CancellationStage
    completed_indexes: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.planned_chunks < 0 or self.planned_initial_requests != self.planned_chunks:
            raise ContractError("Planned accounting is inconsistent.")
        if not 0 <= self.completed_chunks <= self.planned_chunks:
            raise ContractError("Completed chunk count exceeds the plan.")
        if self.client_attempts_started < self.completed_chunks:
            raise ContractError("Completed chunks require started client attempts.")
        if len(self.request_ids) > self.client_attempts_started:
            raise ContractError("Request IDs cannot exceed started client attempts.")
        if any(not request_id.strip() for request_id in self.request_ids):
            raise ContractError("Request IDs must be non-empty strings.")
        if len(set(self.uncertain_indexes)) != len(self.uncertain_indexes):
            raise ContractError("Uncertain chunk indexes must be unique.")
        completed = self.completed_indexes or tuple(range(1, self.completed_chunks + 1))
        if len(completed) != self.completed_chunks or len(set(completed)) != len(completed):
            raise ContractError("Completed indexes are inconsistent.")
        if any(index < 1 or index > self.planned_chunks for index in completed):
            raise ContractError("Completed indexes are outside the plan.")
        if any(index < 1 or index > self.planned_chunks for index in self.uncertain_indexes):
            raise ContractError("Uncertain indexes are outside the plan.")
        occupied = set(completed).union(self.uncertain_indexes)
        if self.client_attempts_started < len(occupied):
            raise ContractError("Occupied indexes require started client attempts.")
        if set(completed).intersection(self.uncertain_indexes):
            raise ContractError("Uncertain chunks cannot overlap completed chunks.")


@dataclass(frozen=True, slots=True)
class SuccessOutcome:
    message: str
    output_path: str
    accounting: RunAccounting
    finalization: FinalizationReport | None = None

    def __post_init__(self) -> None:
        if self.accounting.planned_chunks < 1:
            raise ContractError("A successful run must plan at least one chunk.")
        if self.accounting.completed_chunks != self.accounting.planned_chunks:
            raise ContractError("A successful run must complete every chunk.")
        if (
            self.accounting.uncertain_indexes
            or self.accounting.cancellation_stage is not CancellationStage.NONE
        ):
            raise ContractError("A successful run must be certain and uncancelled.")
        if (
            self.finalization is not None
            and self.finalization.canonical_state is not CanonicalState.VERIFIED_NEW_PAIR
        ):
            raise ContractError("Success must retain a verified canonical pair.")


@dataclass(frozen=True, slots=True)
class CancelledOutcome:
    message: str
    accounting: RunAccounting
    finalization: FinalizationReport | None = None

    def __post_init__(self) -> None:
        if self.accounting.cancellation_stage is CancellationStage.NONE:
            raise ContractError("Cancelled runs require a cancellation stage.")


@dataclass(frozen=True, slots=True)
class ProviderFailureOutcome:
    message: str
    accounting: RunAccounting
    status_code: int | None = None
    request_id: str | None = None
    finalization: FinalizationReport | None = None


@dataclass(frozen=True, slots=True)
class ChunkFailureOutcome:
    message: str
    chunk_index: int | None
    accounting: RunAccounting
    file_path: str | None = None
    finalization: FinalizationReport | None = None


@dataclass(frozen=True, slots=True)
class FfmpegFailureOutcome:
    message: str
    accounting: RunAccounting
    finalization: FinalizationReport | None = None


@dataclass(frozen=True, slots=True)
class FfmpegNotFoundOutcome:
    message: str
    accounting: RunAccounting
    finalization: FinalizationReport | None = None


@dataclass(frozen=True, slots=True)
class OutputBusyOutcome:
    output_path: str
    accounting: RunAccounting
    finalization: FinalizationReport | None = None


@dataclass(frozen=True, slots=True)
class DestinationChangedOutcome:
    output_path: str
    reason: str
    accounting: RunAccounting
    finalization: FinalizationReport | None = None


@dataclass(frozen=True, slots=True)
class PublicationFailureOutcome:
    message: str
    reason: PublicationFailureReason
    finalization: FinalizationReport
    accounting: RunAccounting


@dataclass(frozen=True, slots=True)
class PublicationRecoveryFailureOutcome(PublicationFailureOutcome):
    pass


@dataclass(frozen=True, slots=True)
class UnknownFailureOutcome:
    message: str
    accounting: RunAccounting
    finalization: FinalizationReport | None = None


type GenerationOutcome = (
    SuccessOutcome
    | CancelledOutcome
    | ProviderFailureOutcome
    | ChunkFailureOutcome
    | FfmpegFailureOutcome
    | FfmpegNotFoundOutcome
    | OutputBusyOutcome
    | DestinationChangedOutcome
    | PublicationRecoveryFailureOutcome
    | PublicationFailureOutcome
    | UnknownFailureOutcome
)
