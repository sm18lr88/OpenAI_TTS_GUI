from __future__ import annotations

from pathlib import Path

from openai_tts_gui.errors import CleanupReport, FFmpegError
from openai_tts_gui.tts import (
    CancellationStage,
    TTSService,
    _execution,
    _publication,
)
from openai_tts_gui.tts._contracts import GenerationConfig, GenerationRequest
from openai_tts_gui.tts._outcomes import CancelledOutcome, FfmpegFailureOutcome, SuccessOutcome
from openai_tts_gui.tts._publication_plan import PublicationPlan, cleanup_plan
from tests.fakes_tts_service import FakeChunkOutcome, FakeTTSServiceHarness


def test_cleanup_plan_reports_only_the_exact_blocked_chunk_and_directory(tmp_path: Path) -> None:
    # Given: two chunks where cleanup removes the first and the second remains locked.
    first = tmp_path / "chunk_0001.wav"
    second = tmp_path / "chunk_0002.wav"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    plan = PublicationPlan(
        tmp_path / "out.wav", tmp_path, [str(first), str(second)], (), 1, 1, False
    )

    def cleanup(paths: list[str]) -> None:
        path = Path(paths[0])
        if path == second:
            raise OSError("locked")
        path.unlink()

    # When: execution performs terminal chunk cleanup one tracked artifact at a time.
    report = cleanup_plan(plan, cleanup)

    # Then: retained artifacts and warnings identify only the blocked chunk and directory.
    assert report.retained_basenames == ("chunk_0002.wav", tmp_path.name)
    assert len(report.warnings) == 2
    assert any("Could not remove chunk file" in warning for warning in report.warnings)
    assert any("Could not remove chunk directory" in warning for warning in report.warnings)


def test_execution_attaches_exact_cleanup_and_release_warnings(monkeypatch, tmp_path: Path) -> None:
    # Given: a successful run whose chunk cleanup and lease release report independent failures.
    output = tmp_path / "out.wav"
    harness = FakeTTSServiceHarness({"speech": [FakeChunkOutcome(audio_bytes=b"audio")]})
    monkeypatch.setattr("openai_tts_gui.tts._service.OpenAI", harness.openai_class())
    monkeypatch.setattr("openai_tts_gui.tts._service.require_preflight", lambda: "ffmpeg OK")
    monkeypatch.setattr(
        "openai_tts_gui.tts._service.concatenate_audio_files",
        lambda _files, destination: Path(destination).write_bytes(b"audio"),
    )

    class Lease:
        def release(self) -> CleanupReport:
            return CleanupReport((), ("Could not close the lease for output.lock: locked",))

    monkeypatch.setattr(
        _execution,
        "acquire_lease",
        lambda _paths, _root: Lease(),
    )

    def fail_cleanup(_paths: list[str]) -> None:
        raise OSError("locked")

    monkeypatch.setattr("openai_tts_gui.tts._service.cleanup_files", fail_cleanup)

    # When: terminal cleanup and release run after the successful publication.
    outcome = TTSService(api_key="synthetic").execute(
        GenerationRequest("speech", str(output), GenerationConfig(response_format="wav"))
    )

    # Then: the finalization report retains each artifact once and keeps warnings separate.
    assert isinstance(outcome, SuccessOutcome)
    assert outcome.finalization is not None
    chunk_directory = next(tmp_path.glob("out_chunks_*")).name
    assert outcome.finalization.retained_basenames == ("chunk_0001.wav", chunk_directory)
    assert (
        outcome.finalization.warnings.count("Could not remove chunk file chunk_0001.wav: locked")
        == 1
    )
    assert (
        outcome.finalization.warnings.count("Could not close the lease for output.lock: locked")
        == 1
    )
    assert sum(chunk_directory in warning for warning in outcome.finalization.warnings) == 1


def test_execution_preserves_ffmpeg_failure_with_blocked_stage_cleanup(
    monkeypatch, tmp_path: Path
) -> None:
    # Given: ffmpeg leaves a tracked staged audio file whose unlink is blocked.
    output = tmp_path / "out.wav"
    harness = FakeTTSServiceHarness({"speech": [FakeChunkOutcome(audio_bytes=b"audio")]})
    monkeypatch.setattr("openai_tts_gui.tts._service.OpenAI", harness.openai_class())
    monkeypatch.setattr("openai_tts_gui.tts._service.require_preflight", lambda: "ffmpeg OK")

    def fail_ffmpeg(_files: list[str], destination: str) -> None:
        Path(destination).write_bytes(b"staged")
        raise FFmpegError("native ffmpeg failed")

    original_unlink = Path.unlink

    def block_staged_audio(path: Path, **kwargs: bool) -> None:
        if path.name == output.name and path.parent.name.startswith(".out.publication-"):
            raise PermissionError("stage locked")
        original_unlink(path, **kwargs)

    monkeypatch.setattr("openai_tts_gui.tts._service.concatenate_audio_files", fail_ffmpeg)
    monkeypatch.setattr(Path, "unlink", block_staged_audio)

    # When: publication cleans the failed staging transaction.
    outcome = TTSService(api_key="synthetic").execute(
        GenerationRequest("speech", str(output), GenerationConfig(response_format="wav"))
    )

    # Then: the native ffmpeg category and blocked stage cleanup report both survive.
    assert isinstance(outcome, FfmpegFailureOutcome)
    assert outcome.finalization is not None
    assert output.name in outcome.finalization.retained_basenames
    assert any(
        "Could not clean up the stage path" in warning for warning in outcome.finalization.warnings
    )
    assert not output.exists()


def test_execution_preserves_cancelled_outcome_with_blocked_stage_cleanup(
    monkeypatch, tmp_path: Path
) -> None:
    # Given: cancellation wins the publication gate after staged audio validation.
    output = tmp_path / "out.wav"
    harness = FakeTTSServiceHarness({"speech": [FakeChunkOutcome(audio_bytes=b"audio")]})
    monkeypatch.setattr("openai_tts_gui.tts._service.OpenAI", harness.openai_class())
    monkeypatch.setattr("openai_tts_gui.tts._service.require_preflight", lambda: "ffmpeg OK")
    monkeypatch.setattr(
        "openai_tts_gui.tts._service.concatenate_audio_files",
        lambda _files, destination: Path(destination).write_bytes(b"staged"),
    )
    original_unlink = Path.unlink

    def block_staged_audio(path: Path, **kwargs: bool) -> None:
        if path.name == output.name and path.parent.name.startswith(".out.publication-"):
            raise PermissionError("stage locked")
        original_unlink(path, **kwargs)

    service = TTSService(api_key="synthetic")

    def cancel_after_audio_validation(_audio_path: Path) -> None:
        service.request_cancel()

    monkeypatch.setattr(Path, "unlink", block_staged_audio)
    monkeypatch.setattr(_publication, "verify_audio", cancel_after_audio_validation)

    # When: the gate observes the prior cancellation and rolls back staging.
    outcome = service.execute(
        GenerationRequest("speech", str(output), GenerationConfig(response_format="wav"))
    )

    # Then: cancellation remains the terminal category and reports retained staging artifacts.
    assert isinstance(outcome, CancelledOutcome)
    assert outcome.accounting.cancellation_stage is CancellationStage.BEFORE_PUBLICATION
    assert outcome.finalization is not None
    assert output.name in outcome.finalization.retained_basenames
    assert any(
        "Could not clean up the stage path" in warning for warning in outcome.finalization.warnings
    )
    assert not output.exists()
