from __future__ import annotations

import threading
from collections.abc import Callable

import pytest

import openai_tts_gui.tts as tts
from openai_tts_gui.errors import (
    ConfigError,
    ContractError,
    ContractErrorCode,
    FFmpegError,
    FFmpegNotFoundError,
    PublicationRecoveryError,
    TTSAPIError,
    TTSCancelledError,
    TTSChunkError,
)
from openai_tts_gui.tts import (
    CancellationStage,
    CancelledOutcome,
    ChunkFailureOutcome,
    FfmpegFailureOutcome,
    FfmpegNotFoundOutcome,
    GenerationConfig,
    GenerationRequest,
    ProviderFailureOutcome,
    ProviderRequest,
    RunAccounting,
    RunState,
    SuccessOutcome,
    UnknownFailureOutcome,
)
from openai_tts_gui.tts._legacy import progress_callback, project_contract_error, project_outcome
from openai_tts_gui.tts._outcomes import PublicationRecoveryFailureOutcome
from openai_tts_gui.tts._publication import ChunkRequestMeta, ChunkTask
from openai_tts_gui.tts._publication_types import (
    CanonicalState,
    FinalizationReport,
    PublicationFailureReason,
)
from openai_tts_gui.tts._scheduler import (
    RunCoordinator,
    ScheduledBatch,
    generate_parallel,
    generate_serial,
)


def _accounting(
    *,
    planned_chunks: int = 1,
    planned_initial_requests: int = 1,
    client_attempts_started: int = 1,
    completed_chunks: int = 1,
    request_ids: tuple[str, ...] = ("req-1",),
    uncertain_indexes: tuple[int, ...] = (),
    cancellation_stage: CancellationStage = CancellationStage.NONE,
    completed_indexes: tuple[int, ...] = (),
) -> RunAccounting:
    return RunAccounting(
        planned_chunks,
        planned_initial_requests,
        client_attempts_started,
        completed_chunks,
        request_ids,
        uncertain_indexes,
        cancellation_stage,
        completed_indexes,
    )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: GenerationConfig(model="unsupported"),
        lambda: GenerationConfig(voice="unsupported"),
        lambda: GenerationConfig(response_format="unsupported"),
        lambda: GenerationConfig(speed=float("inf")),
        lambda: GenerationConfig(speed=0.01),
        lambda: GenerationConfig(parallelism=0),
    ],
)
def test_generation_config_rejects_every_invalid_field(
    factory: Callable[[], GenerationConfig],
) -> None:
    with pytest.raises(ContractError):
        factory()


def test_request_and_provider_contract_boundaries_reject_invalid_values() -> None:
    config = GenerationConfig(response_format="wav")
    with pytest.raises(ContractError):
        GenerationRequest("speech", " ", config)
    with pytest.raises(ContractError):
        ProviderRequest(0, "speech", "out.wav", config)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"planned_chunks": -1},
        {"planned_initial_requests": 2},
        {"client_attempts_started": 0},
        {"completed_chunks": 2},
        {"request_ids": ("req-1", "req-2")},
        {"uncertain_indexes": (1, 1)},
        {"request_ids": ("",), "completed_chunks": 0, "client_attempts_started": 1},
        {"uncertain_indexes": (2,)},
        {"completed_indexes": (1, 2)},
        {"completed_indexes": (1, 1), "completed_chunks": 2, "client_attempts_started": 2},
        {"completed_indexes": (2,)},
    ],
)
def test_accounting_rejects_each_inconsistent_snapshot(kwargs) -> None:
    with pytest.raises(ContractError):
        RunAccounting(
            **{
                "planned_chunks": kwargs.get("planned_chunks", 1),
                "planned_initial_requests": kwargs.get("planned_initial_requests", 1),
                "client_attempts_started": kwargs.get("client_attempts_started", 1),
                "completed_chunks": kwargs.get("completed_chunks", 1),
                "request_ids": kwargs.get("request_ids", ("req-1",)),
                "uncertain_indexes": kwargs.get("uncertain_indexes", ()),
                "cancellation_stage": CancellationStage.NONE,
                "completed_indexes": kwargs.get("completed_indexes", ()),
            }
        )


def test_terminal_outcomes_reject_impossible_snapshots() -> None:
    incomplete = _accounting(completed_chunks=0, client_attempts_started=0, request_ids=())
    cancelled = _accounting(cancellation_stage=CancellationStage.BEFORE_REQUEST)
    with pytest.raises(ContractError):
        SuccessOutcome("saved", "out.wav", incomplete)
    with pytest.raises(ContractError):
        SuccessOutcome(
            "saved",
            "out.wav",
            _accounting(uncertain_indexes=(1,), completed_chunks=0, request_ids=()),
        )
    with pytest.raises(ContractError):
        SuccessOutcome("saved", "out.wav", cancelled)
    with pytest.raises(ContractError):
        CancelledOutcome("cancelled", _accounting())


def test_accounting_rejects_duplicate_completed_indexes_and_empty_success_plan() -> None:
    with pytest.raises(ContractError):
        _accounting(
            planned_chunks=2,
            planned_initial_requests=2,
            client_attempts_started=2,
            completed_chunks=2,
            request_ids=("req-1", "req-2"),
            completed_indexes=(1, 1),
        )
    with pytest.raises(ContractError):
        SuccessOutcome(
            "saved",
            "out.wav",
            _accounting(
                planned_chunks=0,
                planned_initial_requests=0,
                client_attempts_started=0,
                completed_chunks=0,
                request_ids=(),
            ),
        )


def test_run_state_handles_plan_binding_and_frozen_cancellation() -> None:
    state = RunState(0, threading.Event())
    state.bind_plan(1)
    with pytest.raises(ContractError):
        state.bind_plan(1)
    frozen = state.freeze()
    assert state.request_cancel() is CancellationStage.NONE
    assert frozen.cancellation_stage is CancellationStage.NONE


def test_legacy_progress_projection_handles_every_runtime_variant() -> None:
    values: list[int] = []
    callback = progress_callback(values.append, [0])
    assert callback is not None
    callback(tts.RunStarted(2))
    callback(tts.ChunkCompleted(1, None))
    callback(tts.PublicationStarted())
    callback(tts.ChunkStarted(1, 1))
    callback(tts.RetryWaiting(1, 1, 0.0))
    callback(tts.FfmpegStarted())
    callback(tts.CancelRequested(CancellationStage.BEFORE_REQUEST))
    assert values == [1, 47, 100]
    assert progress_callback(None, [0]) is None


def test_legacy_contract_error_and_outcome_projection_is_exhaustive() -> None:
    assert isinstance(
        project_contract_error(ContractError("empty", ContractErrorCode.EMPTY_TEXT)), TTSChunkError
    )
    assert isinstance(project_contract_error(ContractError("config")), ConfigError)
    accounting = _accounting()
    assert project_outcome(SuccessOutcome("saved", "out.wav", accounting)) == "saved"
    with pytest.raises(TTSCancelledError):
        project_outcome(
            CancelledOutcome(
                "cancelled", _accounting(cancellation_stage=CancellationStage.BEFORE_REQUEST)
            )
        )
    with pytest.raises(TTSAPIError) as provider_error:
        project_outcome(ProviderFailureOutcome("provider", accounting, 429, "req-429"))
    assert provider_error.value.status_code == 429
    assert provider_error.value.request_id == "req-429"
    with pytest.raises(TTSChunkError) as chunk_error:
        project_outcome(ChunkFailureOutcome("chunk", 1, accounting, "chunk.wav"))
    assert chunk_error.value.chunk_index == 1
    assert chunk_error.value.file_path == "chunk.wav"
    with pytest.raises(FFmpegError):
        project_outcome(FfmpegFailureOutcome("ffmpeg", accounting))
    with pytest.raises(FFmpegNotFoundError):
        project_outcome(FfmpegNotFoundOutcome("missing", accounting))
    with pytest.raises(TTSAPIError):
        project_outcome(UnknownFailureOutcome("unknown", accounting))
    recovery = PublicationRecoveryFailureOutcome(
        "restore failed",
        PublicationFailureReason.RESTORE_SIDECAR,
        FinalizationReport(CanonicalState.ORIGINAL_AUDIO_WITHOUT_SIDECAR),
        accounting,
    )
    with pytest.raises(PublicationRecoveryError) as recovery_error:
        project_outcome(recovery)
    assert recovery_error.value.reason is PublicationFailureReason.RESTORE_SIDECAR


def test_tts_facade_resolves_provider_exports_and_rejects_unknown_name() -> None:
    assert tts.OpenAIProviderAdapter.__name__ == "OpenAIProviderAdapter"
    assert tts.SpeechProvider.__name__ == "SpeechProvider"
    with pytest.raises(AttributeError):
        tts.__getattr__("not_a_tts_export")


def test_scheduler_handles_no_callbacks_and_empty_permit_release(tmp_path) -> None:
    coordinator = RunCoordinator(1)
    coordinator.release()
    coordinator.apply_retry_wait(0.0, reduce_cap=False)
    task = ChunkTask(1, "speech", tmp_path / "chunk.wav")
    metadata = ChunkRequestMeta(1, "req-1", None, str(task.filename), 1, 6)
    batch = ScheduledBatch((task,), {}, {1}, threading.Lock(), None, None, None, None)
    generate_serial(batch, lambda *, task: metadata)
    assert batch.metadata == {1: metadata}
    assert coordinator.snapshot() == (0, 1)


def test_scheduler_reports_serial_progress_and_accepts_parallel_metadata(tmp_path) -> None:
    task = ChunkTask(1, "speech", tmp_path / "chunk.wav")
    metadata = ChunkRequestMeta(1, "req-1", None, str(task.filename), 1, 6)
    progress: list[int] = []
    serial_batch = ScheduledBatch(
        (task,), {}, {1}, threading.Lock(), progress.append, None, None, None
    )
    generate_serial(serial_batch, lambda *, task: metadata)
    parallel_batch = ScheduledBatch((task,), {}, {1}, threading.Lock(), None, None, None, None)
    generate_parallel(parallel_batch, lambda *, task: metadata, RunCoordinator(1), None)
    assert progress == [95]
    assert parallel_batch.metadata == {1: metadata}
