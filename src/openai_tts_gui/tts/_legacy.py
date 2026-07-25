from __future__ import annotations

from collections.abc import Callable
from typing import assert_never

from ..errors import (
    ConfigError,
    ContractError,
    ContractErrorCode,
    DestinationChangedError,
    FFmpegError,
    FFmpegNotFoundError,
    OutputBusyError,
    PublicationError,
    PublicationRecoveryError,
    TTSAPIError,
    TTSCancelledError,
    TTSChunkError,
)
from ._contracts import (
    CancelledOutcome,
    CancelRequested,
    ChunkCompleted,
    ChunkFailureOutcome,
    ChunkStarted,
    DestinationChangedOutcome,
    FfmpegFailureOutcome,
    FfmpegNotFoundOutcome,
    FfmpegStarted,
    GenerationOutcome,
    GenerationProgress,
    OutputBusyOutcome,
    ProviderFailureOutcome,
    PublicationFailureOutcome,
    PublicationRecoveryFailureOutcome,
    PublicationStarted,
    RetryWaiting,
    RunStarted,
    SuccessOutcome,
    UnknownFailureOutcome,
)

ProgressCallback = Callable[[int], None]


def progress_callback(
    callback: ProgressCallback | None, total: list[int]
) -> Callable[[GenerationProgress], None] | None:
    if callback is None:
        return None

    def emit(progress: GenerationProgress) -> None:
        match progress:
            case RunStarted(planned_chunks=planned_chunks):
                total[0] = planned_chunks
                callback(1)
            case ChunkCompleted(chunk_index=chunk_index):
                callback(int((chunk_index / total[0]) * 95))
            case PublicationStarted():
                callback(100)
            case ChunkStarted() | RetryWaiting() | FfmpegStarted() | CancelRequested():
                return
            case unreachable:
                assert_never(unreachable)

    return emit


def project_contract_error(error: ContractError) -> ConfigError | TTSChunkError:
    match error.code:
        case ContractErrorCode.EMPTY_TEXT:
            return TTSChunkError(error.message)
        case ContractErrorCode.CONFIGURATION:
            return ConfigError(error.message)
        case unreachable:
            assert_never(unreachable)


def project_outcome(outcome: GenerationOutcome) -> str:
    match outcome:
        case SuccessOutcome(message=message):
            return message
        case CancelledOutcome(message=message):
            raise TTSCancelledError(message)
        case ProviderFailureOutcome(message=message, status_code=status, request_id=request_id):
            raise TTSAPIError(message, status_code=status, request_id=request_id)
        case ChunkFailureOutcome(message=message, chunk_index=index, file_path=file_path):
            raise TTSChunkError(message, chunk_index=index, file_path=file_path)
        case FfmpegFailureOutcome(message=message):
            raise FFmpegError(message)
        case FfmpegNotFoundOutcome(message=message):
            raise FFmpegNotFoundError(message)
        case OutputBusyOutcome(output_path=output_path):
            raise OutputBusyError(output_path)
        case DestinationChangedOutcome(output_path=output_path, reason=reason):
            raise DestinationChangedError(output_path, reason)
        case PublicationRecoveryFailureOutcome(
            message=message, reason=reason, finalization=finalization
        ):
            raise PublicationRecoveryError(reason, message, finalization)
        case PublicationFailureOutcome(message=message, reason=reason, finalization=finalization):
            raise PublicationError(reason, message, finalization)
        case UnknownFailureOutcome(message=message):
            raise TTSAPIError(message)
        case unreachable:
            assert_never(unreachable)
