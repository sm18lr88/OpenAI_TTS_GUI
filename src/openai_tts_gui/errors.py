from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TTSError(Exception):
    """Base class for TTS domain errors."""


class ValidationError(TTSError):
    """Raised for invalid user options."""


class TTSAPIError(TTSError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        request_id: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.request_id = request_id
        super().__init__(message)


class TTSChunkError(TTSError):
    def __init__(
        self,
        message: str,
        *,
        chunk_index: int | None = None,
        file_path: str | None = None,
        finalization: FinalizationReport | None = None,
    ) -> None:
        self.chunk_index = chunk_index
        self.file_path = file_path
        self.finalization = finalization
        super().__init__(message)


class TTSCancelledError(TTSError):
    """Raised when a generation job is cancelled."""

    def __init__(self, message: str, *, finalization: FinalizationReport | None = None) -> None:
        self.finalization = finalization
        super().__init__(message)


class ConcurrentRunError(TTSError):
    """Raised before a service starts another active run."""


@dataclass(frozen=True, slots=True)
class OutputBusyError(TTSError):
    output_path: str

    def __str__(self) -> str:
        return f"Output is busy: {self.output_path}"


@dataclass(frozen=True, slots=True)
class DestinationChangedError(TTSError):
    output_path: str
    reason: str

    def __str__(self) -> str:
        return f"Destination changed for {self.output_path}: {self.reason}"


@dataclass(frozen=True, slots=True)
class DestinationObservationError(TTSError):
    output_path: str
    reason: str

    def __str__(self) -> str:
        return f"Cannot observe destination {self.output_path}: {self.reason}"


class PublicationFailureReason(StrEnum):
    PREPARE_STAGE = "prepare_stage"
    STAGE_AUDIO = "stage_audio"
    VALIDATE_AUDIO = "validate_audio"
    STAGE_SIDECAR = "stage_sidecar"
    VALIDATE_SIDECAR = "validate_sidecar"
    BACKUP_SIDECAR = "backup_sidecar"
    REPLACE_AUDIO = "replace_audio"
    RESTORE_SIDECAR = "restore_sidecar"
    REPLACE_SIDECAR = "replace_sidecar"


class CanonicalState(StrEnum):
    ORIGINAL_DESTINATION = "original_destination"
    ORIGINAL_AUDIO_WITHOUT_SIDECAR = "original_audio_without_sidecar"
    NEW_AUDIO_WITHOUT_SIDECAR = "new_audio_without_sidecar"
    VERIFIED_NEW_PAIR = "verified_new_pair"


@dataclass(frozen=True, slots=True)
class FinalizationReport:
    canonical_state: CanonicalState
    retained_basenames: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def with_cleanup(self, cleanup: CleanupReport) -> FinalizationReport:
        return FinalizationReport(
            self.canonical_state,
            tuple(sorted({*self.retained_basenames, *cleanup.retained_basenames})),
            tuple(sorted({*self.warnings, *cleanup.warnings})),
        )


@dataclass(frozen=True, slots=True)
class CleanupReport:
    retained_basenames: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def merged(self, other: CleanupReport) -> CleanupReport:
        return CleanupReport(
            tuple(sorted({*self.retained_basenames, *other.retained_basenames})),
            tuple(sorted({*self.warnings, *other.warnings})),
        )


class PublicationError(TTSError):
    def __init__(
        self,
        reason: PublicationFailureReason,
        message: str,
        finalization: FinalizationReport,
    ) -> None:
        self.reason = reason
        self.finalization = finalization
        super().__init__(message)

    def __str__(self) -> str:
        return f"Publication failed during {self.reason}: {super().__str__()}"


class PublicationRecoveryError(PublicationError):
    pass


class FFmpegError(TTSError):
    """Raised when ffmpeg validation or processing fails."""

    def __init__(self, message: str, *, finalization: FinalizationReport | None = None) -> None:
        self.finalization = finalization
        super().__init__(message)


class FFmpegNotFoundError(FFmpegError):
    """Raised when the configured ffmpeg executable cannot be found."""


class ConfigError(ValidationError):
    """Raised for invalid application or request configuration."""


@dataclass(frozen=True, slots=True)
class LoggingConfigurationError(ValidationError):
    """Raised when logging limits cannot meet their safety contract."""

    reason: str

    def __str__(self) -> str:
        return self.reason


class ContractErrorCode(StrEnum):
    CONFIGURATION = "configuration"
    EMPTY_TEXT = "empty_text"


@dataclass(frozen=True, slots=True)
class ContractError(ValidationError):
    """Raised when a typed generation contract is inconsistent."""

    message: str
    code: ContractErrorCode = ContractErrorCode.CONFIGURATION

    def __str__(self) -> str:
        return self.message


class StorageError(TTSError):
    """Raised when secure storage or file persistence fails."""


class PresetError(TTSError):
    """Raised when preset persistence fails."""
