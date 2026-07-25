from __future__ import annotations

import math
import threading
from collections.abc import Callable
from dataclasses import dataclass

from ..config import MAX_SPEED, MIN_SPEED, TTS_FORMATS, TTS_MODELS, TTS_VOICES
from ..errors import ContractError, ContractErrorCode
from ._destination import DestinationObservation
from ._outcomes import (
    CancellationStage,
    CancelledOutcome,
    ChunkFailureOutcome,
    DestinationChangedOutcome,
    FfmpegFailureOutcome,
    FfmpegNotFoundOutcome,
    GenerationOutcome,
    OutputBusyOutcome,
    ProviderFailureOutcome,
    PublicationFailureOutcome,
    PublicationInProgress,
    PublicationRecoveryFailureOutcome,
    RunAccounting,
    SuccessOutcome,
    UnknownFailureOutcome,
)

ProgressCallback = Callable[["GenerationProgress"], None]
StatusCallback = Callable[[str], None]
ParallelismCallback = Callable[[int, int], None]


@dataclass(frozen=True, slots=True)
class GenerationConfig:
    model: str = "tts-1"
    voice: str = "alloy"
    response_format: str = "mp3"
    speed: float = 1.0
    instructions: str = ""
    parallelism: int | None = None
    retain_files: bool = False

    def __post_init__(self) -> None:
        if (
            self.model not in TTS_MODELS
            or self.voice not in TTS_VOICES
            or self.response_format not in TTS_FORMATS
        ):
            raise ContractError("Unsupported generation configuration.")
        if not math.isfinite(self.speed) or not MIN_SPEED <= self.speed <= MAX_SPEED:
            raise ContractError("Speed must be finite and within the supported range.")
        if self.parallelism is not None and self.parallelism < 1:
            raise ContractError("Parallelism must be at least one.")


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    text: str
    output_path: str
    config: GenerationConfig
    destination_observation: DestinationObservation | None = None

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ContractError("No text provided.", ContractErrorCode.EMPTY_TEXT)
        if not self.output_path.strip():
            raise ContractError("An output path is required.")


@dataclass(frozen=True, slots=True)
class GenerationHooks:
    on_progress: ProgressCallback | None = None
    on_status: StatusCallback | None = None
    on_parallelism: ParallelismCallback | None = None
    cancel_event: threading.Event | None = None


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    chunk_index: int
    text: str
    output_path: str
    config: GenerationConfig

    def __post_init__(self) -> None:
        if self.chunk_index < 1:
            raise ContractError("Chunk indexes start at one.")


@dataclass(frozen=True, slots=True)
class ProviderReceipt:
    request_id: str | None
    model_header: str | None
    retry_headers: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class RunStarted:
    planned_chunks: int


@dataclass(frozen=True, slots=True)
class ChunkStarted:
    chunk_index: int
    attempt: int


@dataclass(frozen=True, slots=True)
class ChunkCompleted:
    chunk_index: int
    request_id: str | None


@dataclass(frozen=True, slots=True)
class RetryWaiting:
    chunk_index: int
    attempt: int
    seconds: float


@dataclass(frozen=True, slots=True)
class FfmpegStarted:
    pass


@dataclass(frozen=True, slots=True)
class PublicationStarted:
    pass


@dataclass(frozen=True, slots=True)
class CancelRequested:
    stage: CancellationStage


type GenerationProgress = (
    RunStarted
    | ChunkStarted
    | ChunkCompleted
    | RetryWaiting
    | FfmpegStarted
    | PublicationStarted
    | CancelRequested
)

__all__ = [
    "CancellationStage",
    "CancelledOutcome",
    "CancelRequested",
    "ChunkCompleted",
    "ChunkFailureOutcome",
    "ChunkStarted",
    "DestinationChangedOutcome",
    "FfmpegFailureOutcome",
    "FfmpegNotFoundOutcome",
    "FfmpegStarted",
    "GenerationConfig",
    "GenerationHooks",
    "GenerationOutcome",
    "GenerationProgress",
    "GenerationRequest",
    "OutputBusyOutcome",
    "ProviderFailureOutcome",
    "ProviderReceipt",
    "ProviderRequest",
    "PublicationFailureOutcome",
    "PublicationInProgress",
    "PublicationRecoveryFailureOutcome",
    "PublicationStarted",
    "RetryWaiting",
    "RunAccounting",
    "RunStarted",
    "SuccessOutcome",
    "UnknownFailureOutcome",
]
