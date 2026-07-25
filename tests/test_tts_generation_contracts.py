from __future__ import annotations

from pathlib import Path

import pytest

from openai_tts_gui.errors import ContractError
from openai_tts_gui.tts import (
    CancellationStage,
    CancelRequested,
    ChunkCompleted,
    ChunkStarted,
    FfmpegStarted,
    GenerationConfig,
    GenerationRequest,
    PublicationInProgress,
    PublicationStarted,
    RetryWaiting,
    RunAccounting,
    RunStarted,
    RunState,
    SuccessOutcome,
)
from openai_tts_gui.tts import _service as service_module
from tests.fakes_tts_service import FakeChunkOutcome, FakeRateLimitError, FakeTTSServiceHarness


def test_generation_request_rejects_invalid_boundary_values() -> None:
    # Given: malformed request values at the typed boundary.
    config = GenerationConfig(response_format="wav")

    # When / Then: construction rejects values before execution can begin.
    with pytest.raises(ContractError):
        GenerationRequest(text=" ", output_path="out.wav", config=config)
    with pytest.raises(ContractError):
        GenerationConfig(speed=float("nan"))
    with pytest.raises(ContractError):
        RunAccounting(
            planned_chunks=1,
            planned_initial_requests=2,
            client_attempts_started=0,
            completed_chunks=0,
            request_ids=(),
            uncertain_indexes=(),
            cancellation_stage=CancellationStage.NONE,
        )


def test_success_outcome_requires_complete_certain_accounting() -> None:
    # Given: incomplete accounting for a terminal success outcome.
    incomplete = RunAccounting(
        planned_chunks=2,
        planned_initial_requests=2,
        client_attempts_started=2,
        completed_chunks=1,
        request_ids=("req-1",),
        uncertain_indexes=(2,),
        cancellation_stage=CancellationStage.NONE,
    )

    # When / Then: the invalid terminal state cannot be constructed.
    with pytest.raises(ContractError):
        SuccessOutcome(message="saved", output_path="out.wav", accounting=incomplete)


def test_accounting_rejects_occupied_indexes_without_matching_attempts() -> None:
    # Given: one completed and one uncertain chunk whose occupied indexes require two attempts.
    # When / Then: the frozen accounting snapshot rejects the fabricated attempt total.
    with pytest.raises(ContractError):
        RunAccounting(
            planned_chunks=2,
            planned_initial_requests=2,
            client_attempts_started=1,
            completed_chunks=1,
            request_ids=("req-1",),
            uncertain_indexes=(2,),
            cancellation_stage=CancellationStage.NONE,
            completed_indexes=(1,),
        )


def test_progress_variants_are_exhaustively_handleable() -> None:
    # Given: every declared typed progress variant.
    progress = (
        RunStarted(planned_chunks=1),
        ChunkStarted(chunk_index=1, attempt=1),
        ChunkCompleted(chunk_index=1, request_id="req-1"),
        RetryWaiting(chunk_index=1, attempt=1, seconds=1.0),
        FfmpegStarted(),
        PublicationStarted(),
        CancelRequested(stage=CancellationStage.BEFORE_REQUEST),
    )

    # When / Then: every variant has concrete typed data without parsing status strings.
    assert len(progress) == 7


def test_publication_gate_makes_cancellation_and_publication_mutually_exclusive() -> None:
    # Given: two runs waiting at the final cancellation/publication decision point.
    cancelled = RunState(planned_chunks=1, cancel_event=None)
    published = RunState(planned_chunks=1, cancel_event=None)

    # When: cancellation reaches one gate first and publication reaches the other first.
    cancel_stage = cancelled.request_cancel()
    cancel_wins = cancelled.begin_publication()
    publication_wins = published.begin_publication()
    late_cancel = published.request_cancel()

    # Then: cancellation blocks publication, while publication rejects late cancellation.
    assert cancel_wins is cancel_stage is CancellationStage.BEFORE_REQUEST
    assert isinstance(publication_wins, PublicationInProgress)
    assert isinstance(late_cancel, PublicationInProgress)
    published.finish_publication()
    assert published.freeze().cancellation_stage is CancellationStage.NONE


def test_execute_accounts_for_each_started_sdk_adapter_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: a rate limit response followed by one successful adapter response.
    output = tmp_path / "accounted.wav"
    harness = FakeTTSServiceHarness(
        {
            "speech": [
                FakeChunkOutcome(error=FakeRateLimitError()),
                FakeChunkOutcome(audio_bytes=b"audio", request_id="req-final"),
            ]
        }
    )
    monkeypatch.setattr(service_module, "OpenAI", harness.openai_class())
    monkeypatch.setattr(service_module, "RateLimitError", FakeRateLimitError)
    monkeypatch.setattr(service_module, "require_preflight", lambda: "ffmpeg OK")
    monkeypatch.setattr(service_module, "compute_backoff", lambda error, attempt: 0.0)
    monkeypatch.setattr(
        service_module,
        "concatenate_audio_files",
        lambda files, destination: Path(destination).write_bytes(Path(files[0]).read_bytes()),
    )
    service = service_module.TTSService(api_key="synthetic")
    monkeypatch.setattr(service, "_sleep_with_cancel", lambda seconds, event: None)

    # When: typed execution retries the single planned chunk.
    outcome = service.execute(
        GenerationRequest("speech", str(output), GenerationConfig(response_format="wav"))
    )

    # Then: attempts represent adapter calls begun, while the completed chunk has one receipt.
    assert isinstance(outcome, SuccessOutcome)
    assert outcome.accounting.planned_initial_requests == 1
    assert outcome.accounting.client_attempts_started == 2
    assert outcome.accounting.completed_chunks == 1
    assert outcome.accounting.request_ids == ("req-final",)


def test_legacy_generate_projects_authoritative_success_without_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: an authoritative typed success outcome with no provider installation.
    outcome = SuccessOutcome(
        message="TTS audio saved successfully to:\nout.wav",
        output_path=str(tmp_path / "out.wav"),
        accounting=RunAccounting(1, 1, 1, 1, ("req-1",), (), CancellationStage.NONE),
    )
    service = service_module.TTSService(api_key="synthetic")
    monkeypatch.setattr(service, "execute", lambda request, hooks=None: outcome)

    # When: the legacy facade receives the historical keyword-only call.
    message = service.generate(text="speech", output_path=str(tmp_path / "out.wav"))

    # Then: it returns the typed success message without contacting a provider.
    assert message == outcome.message


def test_execute_does_not_call_legacy_generate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: a legacy generate method that fails if execution reverses direction.
    service = service_module.TTSService(api_key="synthetic")
    monkeypatch.setattr(service, "generate", lambda **kwargs: pytest.fail("legacy generate called"))
    monkeypatch.setattr(service_module, "require_preflight", lambda: "ffmpeg OK")
    monkeypatch.setattr(service_module, "split_text", lambda text, size: ["speech"])

    # When: execute is called directly.
    outcome = service.execute(
        GenerationRequest(
            "speech", str(tmp_path / "out.wav"), GenerationConfig("tts-1", "alloy", "wav")
        )
    )

    # Then: the old projection path was not used.
    assert not isinstance(outcome, SuccessOutcome)
