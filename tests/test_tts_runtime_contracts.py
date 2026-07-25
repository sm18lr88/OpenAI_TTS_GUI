from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from openai_tts_gui.core import audio
from openai_tts_gui.core._ffmpeg_process import ProcessOutput
from openai_tts_gui.errors import ContractError, FFmpegNotFoundError
from openai_tts_gui.tts import (
    CancellationStage,
    CancelledOutcome,
    ChunkCompleted,
    ChunkStarted,
    GenerationConfig,
    GenerationHooks,
    GenerationProgress,
    GenerationRequest,
    PublicationInProgress,
    PublicationStarted,
    RetryWaiting,
    RunAccounting,
    RunStarted,
    SuccessOutcome,
    TTSService,
)
from openai_tts_gui.tts import _service as service_module
from tests.fakes_tts_service import FakeChunkOutcome, FakeRateLimitError, FakeTTSServiceHarness


def _install_provider(monkeypatch: pytest.MonkeyPatch, harness: FakeTTSServiceHarness) -> None:
    monkeypatch.setattr(service_module, "OpenAI", harness.openai_class())
    monkeypatch.setattr(service_module, "require_preflight", lambda: "ffmpeg OK")
    monkeypatch.setattr(
        service_module,
        "concatenate_audio_files",
        lambda files, destination: Path(destination).write_bytes(Path(files[0]).read_bytes()),
    )


def test_execute_emits_typed_progress_in_runtime_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: one rate-limited provider request followed by a successful retry.
    harness = FakeTTSServiceHarness(
        {
            "speech": [
                FakeChunkOutcome(error=FakeRateLimitError()),
                FakeChunkOutcome(audio_bytes=b"audio", request_id="req-final"),
            ]
        }
    )
    _install_provider(monkeypatch, harness)
    monkeypatch.setattr(service_module, "RateLimitError", FakeRateLimitError)
    monkeypatch.setattr(service_module, "compute_backoff", lambda error, attempt: 0.0)
    service = TTSService(api_key="synthetic")
    monkeypatch.setattr(service, "_sleep_with_cancel", lambda seconds, event: None)
    progress: list[GenerationProgress] = []

    # When: the authoritative typed entrypoint executes the retry.
    outcome = service.execute(
        GenerationRequest(
            "speech", str(tmp_path / "out.wav"), GenerationConfig(response_format="wav")
        ),
        GenerationHooks(on_progress=progress.append),
    )

    # Then: events describe attempts, the actual retry wait, acceptance, and publication.
    assert isinstance(outcome, SuccessOutcome)
    assert [type(item) for item in progress] == [
        RunStarted,
        ChunkStarted,
        RetryWaiting,
        ChunkStarted,
        ChunkCompleted,
        PublicationStarted,
    ]
    assert isinstance(progress[1], ChunkStarted) and progress[1].attempt == 1
    assert isinstance(progress[2], RetryWaiting) and progress[2].attempt == 1
    assert isinstance(progress[3], ChunkStarted) and progress[3].attempt == 2
    assert isinstance(progress[4], ChunkCompleted) and progress[4].request_id == "req-final"


def test_execute_cancels_between_serial_accepted_chunks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: a second serial chunk whose status callback asks the active service to cancel.
    harness = FakeTTSServiceHarness(
        {
            "first": [FakeChunkOutcome(audio_bytes=b"first")],
            "second": [FakeChunkOutcome(audio_bytes=b"second")],
        }
    )
    _install_provider(monkeypatch, harness)
    monkeypatch.setattr(service_module, "split_text", lambda text, size: ["first", "second"])
    service = TTSService(api_key="synthetic")

    def cancel_before_second_request(status: str) -> None:
        if status.endswith("2/2"):
            service.request_cancel()

    # When: execution reaches the accepted-chunk boundary before the next request.
    outcome = service.execute(
        GenerationRequest(
            "speech", str(tmp_path / "out.wav"), GenerationConfig(response_format="wav")
        ),
        GenerationHooks(on_status=cancel_before_second_request),
    )

    # Then: the terminal snapshot records the real between-chunks phase and rolls back.
    assert isinstance(outcome, CancelledOutcome)
    assert outcome.accounting.cancellation_stage is CancellationStage.BETWEEN_CHUNKS
    assert not (tmp_path / "out.wav").exists()
    assert not (tmp_path / "out.wav.json").exists()


def test_execute_rolls_back_when_cancelled_during_ffmpeg(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: a multi-file concat attaches its process before requesting cancellation.
    harness = FakeTTSServiceHarness(
        {
            "first": [FakeChunkOutcome(audio_bytes=b"first")],
            "second": [FakeChunkOutcome(audio_bytes=b"second")],
        }
    )
    _install_provider(monkeypatch, harness)
    monkeypatch.setattr(service_module, "split_text", lambda _text, _size: ["first", "second"])
    service = TTSService(api_key="synthetic")
    output = tmp_path / "out.wav"

    class FakeProcess:
        def __init__(self, _command: list[str]) -> None:
            self.stop_requests = 0

        def run(self, on_started: Callable[[FakeProcess], bool] | None = None) -> ProcessOutput:
            assert on_started is not None
            assert on_started(self)
            service.request_cancel()
            return ProcessOutput("", "", 0, False, True)

        def request_stop(self) -> None:
            self.stop_requests += 1

    monkeypatch.setattr(audio, "FfmpegProcess", FakeProcess)
    monkeypatch.setattr(service_module, "concatenate_audio_files", audio.concatenate_audio_files)

    # When: the publication transaction observes the cancellation after concatenation.
    outcome = service.execute(
        GenerationRequest("speech", str(output), GenerationConfig(response_format="wav"))
    )

    # Then: final output and sidecar are both rolled back under the ffmpeg stage.
    assert isinstance(outcome, CancelledOutcome)
    assert outcome.accounting.cancellation_stage is CancellationStage.DURING_FFMPEG
    assert not output.exists()
    assert not Path(f"{output}.json").exists()


def test_execute_publication_gate_delivers_hook_after_ownership_is_committed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: a publication hook that requests cancellation as soon as publication begins.
    harness = FakeTTSServiceHarness({"speech": [FakeChunkOutcome(audio_bytes=b"audio")]})
    _install_provider(monkeypatch, harness)
    service = TTSService(api_key="synthetic")
    cancellation_results: list[PublicationInProgress] = []

    def request_late_cancel(progress: GenerationProgress) -> None:
        if isinstance(progress, PublicationStarted):
            result = service.request_cancel()
            assert isinstance(result, PublicationInProgress)
            cancellation_results.append(result)

    # When: execution crosses the atomic publication gate.
    outcome = service.execute(
        GenerationRequest(
            "speech", str(tmp_path / "out.wav"), GenerationConfig(response_format="wav")
        ),
        GenerationHooks(on_progress=request_late_cancel),
    )

    # Then: the delayed callback cannot cancel an already-owned publication.
    assert isinstance(outcome, SuccessOutcome)
    assert cancellation_results
    assert outcome.accounting.cancellation_stage is CancellationStage.NONE


def test_legacy_projection_preserves_ffmpeg_not_found_subclass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: preflight cannot locate the configured ffmpeg binary.
    monkeypatch.setattr(
        service_module,
        "require_preflight",
        lambda: (_ for _ in ()).throw(FFmpegNotFoundError("ffmpeg missing")),
    )

    # When / Then: the legacy facade retains the precise historical exception class.
    with pytest.raises(FFmpegNotFoundError):
        TTSService(api_key="synthetic").generate(
            text="speech", output_path=str(tmp_path / "out.wav")
        )


def test_accounting_rejects_uncertain_completed_overlap() -> None:
    # Given / When / Then: a chunk cannot be both accepted and uncertain.
    with pytest.raises(ContractError):
        RunAccounting(1, 1, 1, 1, ("req-1",), (1,), CancellationStage.NONE)
