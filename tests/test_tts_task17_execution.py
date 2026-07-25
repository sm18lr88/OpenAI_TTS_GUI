from __future__ import annotations

import threading
from pathlib import Path

import pytest

from openai_tts_gui.tts import (
    CancellationStage,
    CancelledOutcome,
    ChunkCompleted,
    GenerationConfig,
    GenerationHooks,
    GenerationProgress,
    GenerationRequest,
    TTSService,
)
from openai_tts_gui.tts import _service as service_module
from tests.fakes_tts_service import FakeChunkOutcome, FakeTTSServiceHarness


def _install_single_chunk_provider(
    monkeypatch: pytest.MonkeyPatch, harness: FakeTTSServiceHarness
) -> None:
    monkeypatch.setattr(service_module, "OpenAI", harness.openai_class())
    monkeypatch.setattr(service_module, "require_preflight", lambda: "ffmpeg OK")
    monkeypatch.setattr(
        service_module,
        "concatenate_audio_files",
        lambda files, destination: Path(destination).write_bytes(Path(files[0]).read_bytes()),
    )


def test_execute_honors_ingress_cancellation_before_preflight(tmp_path: Path, monkeypatch) -> None:
    cancel_event = threading.Event()
    cancel_event.set()
    monkeypatch.setattr(service_module, "require_preflight", lambda: pytest.fail("preflight ran"))

    outcome = TTSService(api_key="synthetic").execute(
        GenerationRequest(
            "speech", str(tmp_path / "ingress.wav"), GenerationConfig(response_format="wav")
        ),
        GenerationHooks(cancel_event=cancel_event),
    )

    assert isinstance(outcome, CancelledOutcome)
    assert outcome.accounting.cancellation_stage is CancellationStage.BEFORE_REQUEST
    assert not (tmp_path / "ingress.wav").exists()


def test_execute_cancels_after_acceptance_before_publication(tmp_path: Path, monkeypatch) -> None:
    harness = FakeTTSServiceHarness({"speech": [FakeChunkOutcome(audio_bytes=b"audio")]})
    _install_single_chunk_provider(monkeypatch, harness)
    service = TTSService(api_key="synthetic")
    cancellation_stages: list[CancellationStage] = []

    def cancel_on_acceptance(progress: GenerationProgress) -> None:
        if isinstance(progress, ChunkCompleted):
            stage = service.request_cancel()
            assert isinstance(stage, CancellationStage)
            cancellation_stages.append(stage)

    outcome = service.execute(
        GenerationRequest(
            "speech",
            str(tmp_path / "before-publication.wav"),
            GenerationConfig(response_format="wav"),
        ),
        GenerationHooks(on_progress=cancel_on_acceptance),
    )

    assert isinstance(outcome, CancelledOutcome)
    assert cancellation_stages == [CancellationStage.BEFORE_PUBLICATION]
    assert outcome.accounting.cancellation_stage is CancellationStage.BEFORE_PUBLICATION
    assert not (tmp_path / "before-publication.wav").exists()
    assert not Path(f"{tmp_path / 'before-publication.wav'}.json").exists()
