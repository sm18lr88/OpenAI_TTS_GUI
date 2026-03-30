from __future__ import annotations


class TTSError(Exception):
    """Base class for all domain-specific TTS errors."""


class ValidationError(TTSError):
    """Raised when user-provided options are invalid."""


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
    ) -> None:
        self.chunk_index = chunk_index
        self.file_path = file_path
        super().__init__(message)


class TTSCancelledError(TTSError):
    """Raised when a running generation job is cancelled."""


class FFmpegError(TTSError):
    """Raised when ffmpeg validation or processing fails."""


class FFmpegNotFoundError(FFmpegError):
    """Raised when the configured ffmpeg executable cannot be found."""


class ConfigError(ValidationError):
    """Raised when application or request configuration is invalid."""


class StorageError(TTSError):
    """Raised when secure storage or file persistence fails."""


class PresetError(TTSError):
    """Raised when preset persistence fails."""
