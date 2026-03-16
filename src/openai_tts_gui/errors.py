class TTSError(Exception):
    pass


class TTSAPIError(TTSError):
    def __init__(
        self, message: str, *, status_code: int | None = None, request_id: str | None = None
    ):
        self.status_code = status_code
        self.request_id = request_id
        super().__init__(message)


class TTSChunkError(TTSError):
    def __init__(
        self, message: str, *, chunk_index: int | None = None, file_path: str | None = None
    ):
        self.chunk_index = chunk_index
        self.file_path = file_path
        super().__init__(message)


class FFmpegError(TTSError):
    pass


class FFmpegNotFoundError(FFmpegError):
    pass


class ConfigError(TTSError):
    pass
