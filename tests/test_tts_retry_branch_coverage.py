from __future__ import annotations

import threading
from pathlib import Path
from types import TracebackType
from typing import Literal

import pytest

from openai_tts_gui.config import settings
from openai_tts_gui.errors import TTSAPIError, TTSCancelledError, TTSChunkError
from openai_tts_gui.tts import TTSService, compute_backoff
from openai_tts_gui.tts import _service as service_module
from tests.fakes_tts_service import FakeChunkOutcome, FakeRateLimitError, FakeTTSServiceHarness


class FakeTimeoutError(Exception):
    pass


class FakeConnectionError(Exception):
    pass


class FakeAPIError(Exception):
    pass


class FakeOpenAIError(Exception):
    pass


def _install_provider(
    monkeypatch: pytest.MonkeyPatch, harness: FakeTTSServiceHarness, output: Path
) -> TTSService:
    monkeypatch.setattr(service_module, "OpenAI", harness.openai_class())
    monkeypatch.setattr(service_module, "require_preflight", lambda: "ffmpeg OK")
    monkeypatch.setattr(
        service_module,
        "concatenate_audio_files",
        lambda files, destination: Path(destination).write_bytes(Path(files[0]).read_bytes()),
    )
    return TTSService(api_key="sk-test")


def test_generate_stops_before_preflight_when_already_cancelled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: cancellation has been requested before the public operation begins.
    cancel_event = threading.Event()
    cancel_event.set()
    monkeypatch.setattr(service_module, "require_preflight", lambda: pytest.fail("preflight ran"))

    # When: generation is requested.
    with pytest.raises(TTSCancelledError):
        TTSService(api_key="sk-test").generate(
            text="speech", output_path=str(tmp_path / "cancel.wav"), cancel_event=cancel_event
        )

    # Then: no output or working directory is created.
    assert not list(tmp_path.iterdir())


def test_generate_rejects_empty_split_result_after_preflight(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: valid text whose splitter produces no usable chunks.
    monkeypatch.setattr(service_module, "require_preflight", lambda: "ffmpeg OK")
    monkeypatch.setattr(service_module, "split_text", lambda text, size: [])

    # When: generation reaches chunk planning.
    with pytest.raises(TTSChunkError, match="No text chunks"):
        TTSService(api_key="sk-test").generate(
            text="speech", output_path=str(tmp_path / "empty.wav")
        )

    # Then: planning fails before creating an artifact.
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("error_type", [FakeTimeoutError, FakeConnectionError])
def test_timeout_and_connection_errors_fail_after_one_uncertain_attempt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, error_type: type[Exception]
) -> None:
    # Given: a provider request raises a non-definitive timeout or connection fault.
    output = tmp_path / "connection.wav"
    harness = FakeTTSServiceHarness({"speech": [FakeChunkOutcome(error=error_type("offline"))]})
    service = _install_provider(monkeypatch, harness, output)
    monkeypatch.setattr(service_module, "APITimeoutError", FakeTimeoutError)
    monkeypatch.setattr(service_module, "APIConnectionError", FakeConnectionError)
    waits: list[float] = []
    monkeypatch.setattr(service, "_sleep_with_cancel", lambda wait, event: waits.append(wait))

    # When: the public facade projects the provider failure.
    with pytest.raises(TTSAPIError, match="API Error"):
        service.generate(text="speech", output_path=str(output), response_format="wav")

    # Then: no second call or retry wait occurs, while no completed artifact exists.
    assert waits == []
    assert len(harness.api_calls) == 1
    assert not output.exists()
    assert not Path(f"{output}.json").exists()


@pytest.mark.parametrize(
    ("error_type", "expected"),
    [(FakeAPIError, "API Error"), (FakeOpenAIError, "API Error")],
)
def test_non_status_provider_errors_map_to_typed_api_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    error_type: type[Exception],
    expected: str,
) -> None:
    # Given: the provider raises a non-status SDK error.
    harness = FakeTTSServiceHarness({"speech": [FakeChunkOutcome(error=error_type("broken"))]})
    service = _install_provider(monkeypatch, harness, tmp_path / "error.wav")
    monkeypatch.setattr(service_module, "APIError", FakeAPIError)
    monkeypatch.setattr(service_module, "OpenAIError", FakeOpenAIError)

    # When: TTSService performs the request.
    with pytest.raises(TTSAPIError, match=expected):
        service.generate(
            text="speech",
            output_path=str(tmp_path / "error.wav"),
            response_format="wav",
        )

    # Then: callers see the domain error rather than an SDK-specific type.


def test_rate_limit_exhaustion_has_no_final_retry_wait(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: every request is rate limited with zero-duration retry guidance.
    harness = FakeTTSServiceHarness(
        {
            "speech": [
                FakeChunkOutcome(error=FakeRateLimitError()) for _ in range(settings.MAX_RETRIES)
            ]
        }
    )
    service = _install_provider(monkeypatch, harness, tmp_path / "rate.wav")
    monkeypatch.setattr(service_module, "RateLimitError", FakeRateLimitError)
    monkeypatch.setattr(service_module, "compute_backoff", lambda error, attempt: 0.0)
    waits: list[float] = []
    monkeypatch.setattr(service, "_sleep_with_cancel", lambda wait, event: waits.append(wait))

    # When: the final rate-limit attempt fails.
    with pytest.raises(TTSAPIError, match="Rate limit persisted"):
        service.generate(
            text="speech",
            output_path=str(tmp_path / "rate.wav"),
            response_format="wav",
        )

    # Then: only retryable attempts wait and the final failure stays typed.
    assert waits == [0.0, 0.0]


def test_instruction_and_stream_format_options_follow_provider_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: a GPT-4o-mini request with an instruction and no stream-format setting.
    harness = FakeTTSServiceHarness({"speech": [FakeChunkOutcome(audio_bytes=b"audio")]})
    service = _install_provider(monkeypatch, harness, tmp_path / "instruction.wav")
    monkeypatch.setattr(settings, "STREAM_FORMAT", "")

    # When: the public API generates audio.
    service.generate(
        text="speech",
        output_path=str(tmp_path / "instruction.wav"),
        model=settings.GPT_4O_MINI_TTS_MODEL,
        response_format="wav",
        instructions="warm and clear",
    )

    # Then: the supported instruction is transmitted and empty stream format is omitted.
    params = harness.api_calls[0]["api_params"]
    assert params["instructions"] == "warm and clear"
    assert "stream_format" not in params


def test_file_write_error_identifies_the_failed_chunk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: a narrow provider response whose stream write fails at the filesystem boundary.
    class BrokenResponse:
        request_id = "req-write"

        def stream_to_file(self, destination: str) -> None:
            raise OSError("disk full")

    class BrokenContext:
        def __enter__(self) -> BrokenResponse:
            return BrokenResponse()

        def __exit__(
            self,
            exception_type: type[BaseException] | None,
            exception: BaseException | None,
            traceback: TracebackType | None,
        ) -> Literal[False]:
            return False

    class BrokenClient:
        def __init__(self) -> None:
            speech = type("Speech", (), {"with_streaming_response": self})()
            self.audio = type("Audio", (), {"speech": speech})()

        def create(self, **params: str | float) -> BrokenContext:
            return BrokenContext()

    service = TTSService(api_key="sk-test")
    monkeypatch.setattr(service, "_get_client", BrokenClient)

    # When: a stream cannot be persisted.
    with pytest.raises(TTSChunkError, match="File saving error") as caught:
        service._generate_chunk_with_retries(
            task=service_module._ChunkTask(1, "speech", tmp_path / "chunk.wav"),
            model="tts-1",
            voice="alloy",
            response_format="wav",
            speed=1.0,
            instructions=None,
        )

    # Then: the typed chunk error identifies the failed output path.
    assert caught.value.chunk_index == 1
    assert caught.value.file_path == str(tmp_path / "chunk.wav")


def test_backoff_ignores_malformed_headers_without_masking_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: malformed provider retry headers and deterministic jitter.
    monkeypatch.setattr(service_module.random, "uniform", lambda start, stop: 0.0)
    error = FakeRateLimitError(headers={"retry-after-ms": "invalid", "retry-after": "also-invalid"})

    # When: backoff is computed.
    delay = compute_backoff(error, 1)

    # Then: the configured exponential fallback remains available.
    assert delay == max(1.0, float(settings.RETRY_DELAY)) * 2


def test_parallel_retry_callbacks_report_only_rate_limit_recovery(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: an explicit rate-limit response is followed by a successful stream.
    harness = FakeTTSServiceHarness(
        {
            "rate": [FakeChunkOutcome(error=FakeRateLimitError()), FakeChunkOutcome()],
        }
    )
    service = _install_provider(monkeypatch, harness, tmp_path / "unused.wav")
    monkeypatch.setattr(service_module, "RateLimitError", FakeRateLimitError)
    monkeypatch.setattr(service_module, "compute_backoff", lambda error, attempt: 0.0)
    monkeypatch.setattr(service, "_sleep_with_cancel", lambda wait, event: None)
    statuses: list[str] = []
    worker_events: list[tuple[int, int]] = []

    # When: its retry runs under a coordinator with public callbacks.
    metadata = [
        service._generate_chunk_with_retries(
            task=service_module._ChunkTask(index, text, tmp_path / f"{text}.wav"),
            model="tts-1",
            voice="alloy",
            response_format="wav",
            speed=1.0,
            instructions=None,
            coordinator=service_module._RunCoordinator(1),
            on_status=statuses.append,
            on_parallelism=lambda active, cap: worker_events.append((active, cap)),
        )
        for index, text in enumerate(("rate",), start=1)
    ]

    # Then: only the explicit rate-limit category recovers on attempt two.
    assert [item.attempts for item in metadata] == [2]
    assert any("rate limited" in status for status in statuses)
    assert worker_events[-1] == (0, 1)
