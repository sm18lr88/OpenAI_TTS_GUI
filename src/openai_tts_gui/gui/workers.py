from __future__ import annotations

import logging
import threading
from typing import NotRequired, TypedDict, assert_never

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from .. import config
from ..tts import (
    CancellationStage,
    CancelledOutcome,
    ChunkFailureOutcome,
    DestinationChangedOutcome,
    FfmpegFailureOutcome,
    FfmpegNotFoundOutcome,
    GenerationConfig,
    GenerationHooks,
    GenerationOutcome,
    GenerationProgress,
    GenerationRequest,
    OutputBusyOutcome,
    ProviderFailureOutcome,
    PublicationFailureOutcome,
    PublicationInProgress,
    PublicationRecoveryFailureOutcome,
    RunAccounting,
    SuccessOutcome,
    TTSService,
    UnknownFailureOutcome,
)

logger = logging.getLogger(__name__)


class WorkerParameters(TypedDict):
    api_key: str
    text: str
    output_path: str
    model: str
    voice: str
    response_format: str
    speed: float
    instructions: NotRequired[str]
    parallelism: NotRequired[int]
    retain_files: NotRequired[bool]


class TTSWorker(QThread):
    progress_updated = pyqtSignal(int)
    tts_complete = pyqtSignal(str)
    tts_error = pyqtSignal(str)
    terminal_outcome = pyqtSignal(object)
    status_update = pyqtSignal(str)
    parallelism_updated = pyqtSignal(int, int)

    def __init__(self, params: WorkerParameters, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.params = params
        self._cancel_event = threading.Event()
        self._service_lock = threading.Lock()
        self._service: TTSService | None = None
        self._planned_chunks = 1

    def cancel(self) -> None:
        with self._service_lock:
            service = self._service
        if service is None:
            self._cancel_event.set()
            return
        decision = service.request_cancel()
        match decision:
            case CancellationStage.NONE:
                self._cancel_event.set()
            case PublicationInProgress():
                pass
            case CancellationStage():
                pass
            case unreachable:
                assert_never(unreachable)
        self._emit_cancel_status(decision)

    def run(self) -> None:
        if self._cancel_event.is_set():
            accounting = RunAccounting(0, 0, 0, 0, (), (), CancellationStage.BEFORE_REQUEST)
            self._emit_terminal(CancelledOutcome("TTS generation cancelled.", accounting))
            return
        service = TTSService(
            api_key=self.params["api_key"],
            base_url=config.OPENAI_BASE_URL,
            timeout=config.OPENAI_TIMEOUT,
        )
        with self._service_lock:
            self._service = service
        try:
            outcome = service.execute(self._request(), self._hooks())
            self._emit_terminal(outcome)
        finally:
            with self._service_lock:
                self._service = None
            logger.info("TTSWorker thread finished.")

    def _request(self) -> GenerationRequest:
        return GenerationRequest(
            self.params["text"],
            self.params["output_path"],
            GenerationConfig(
                self.params["model"],
                self.params["voice"],
                self.params["response_format"],
                self.params["speed"],
                self.params.get("instructions", ""),
                self.params.get("parallelism", config.PARALLELISM),
                self.params.get("retain_files", False),
            ),
        )

    def _hooks(self) -> GenerationHooks:
        return GenerationHooks(
            on_progress=self._emit_progress,
            on_status=self.status_update.emit,
            on_parallelism=self.parallelism_updated.emit,
            cancel_event=self._cancel_event,
        )

    def _emit_terminal(self, outcome: GenerationOutcome) -> None:
        self.terminal_outcome.emit(outcome)
        match outcome:
            case SuccessOutcome(message=message):
                self.tts_complete.emit(message)
            case CancelledOutcome(message=message):
                self.tts_error.emit(message)
            case ProviderFailureOutcome(message=message) | ChunkFailureOutcome(message=message):
                self.tts_error.emit(message)
            case FfmpegFailureOutcome(message=message) | FfmpegNotFoundOutcome(message=message):
                self.tts_error.emit(message)
            case (
                PublicationRecoveryFailureOutcome(message=message)
                | PublicationFailureOutcome(message=message)
            ):
                self.tts_error.emit(message)
            case UnknownFailureOutcome(message=message):
                self.tts_error.emit(message)
            case OutputBusyOutcome(output_path=output_path):
                self.tts_error.emit(f"Output is busy: {output_path}")
            case DestinationChangedOutcome(output_path=output_path, reason=reason):
                self.tts_error.emit(f"Output changed: {output_path} ({reason})")
            case unreachable:
                assert_never(unreachable)

    def _emit_cancel_status(self, decision: CancellationStage | PublicationInProgress) -> None:
        match decision:
            case PublicationInProgress():
                self.status_update.emit(
                    "Publication is already in progress. Waiting for verified finalization."
                )
            case CancellationStage.AWAITING_PROVIDER_RESPONSE:
                self.status_update.emit(
                    "Cancellation requested. Waiting for the provider request to return."
                )
            case CancellationStage.DURING_PROVIDER_STREAM:
                self.status_update.emit(
                    "Cancellation requested. Closing active response streams. Waiting for workers."
                )
            case CancellationStage.DURING_FFMPEG:
                self.status_update.emit(
                    "Cancellation requested. Stopping ffmpeg and cleaning staged files."
                )
            case CancellationStage.NONE:
                return
            case CancellationStage():
                self.status_update.emit("Cancellation requested. Queued work stopped.")
            case unreachable:
                assert_never(unreachable)

    def _emit_progress(self, progress: GenerationProgress) -> None:
        from ..tts import ChunkCompleted, PublicationStarted, RunStarted

        match progress:
            case RunStarted(planned_chunks=planned_chunks):
                self._planned_chunks = planned_chunks
                self.progress_updated.emit(1)
            case ChunkCompleted(chunk_index=chunk_index):
                if not self._cancel_event.is_set():
                    self.progress_updated.emit(int((chunk_index / self._planned_chunks) * 95))
            case PublicationStarted():
                self.progress_updated.emit(100)
            case _:
                return


class FFmpegPreflightWorker(QThread):
    preflight_finished = pyqtSignal(bool, str)

    def run(self) -> None:
        from ..core import preflight_check

        ok, detail = preflight_check()
        self.preflight_finished.emit(ok, detail)


class ApiKeyLoadWorker(QThread):
    api_key_loaded = pyqtSignal(object)
    legacy_credential_cleanup_required = pyqtSignal(str)

    def run(self) -> None:
        from ..keystore import (
            credential_value,
            read_api_key_outcome,
            stale_legacy_credential_guidance,
        )

        credential = read_api_key_outcome()
        self.api_key_loaded.emit(credential_value(credential))
        guidance = stale_legacy_credential_guidance(credential)
        if guidance is not None:
            self.legacy_credential_cleanup_required.emit(guidance)
