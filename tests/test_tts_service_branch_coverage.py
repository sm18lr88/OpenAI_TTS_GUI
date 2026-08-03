from __future__ import annotations

import math
import threading
from pathlib import Path

import pytest

from openai_tts_gui.config import settings
from openai_tts_gui.errors import (
    ConfigError,
    FFmpegError,
    PublicationError,
    TTSAPIError,
    TTSCancelledError,
    TTSChunkError,
)
from openai_tts_gui.tts import TTSService
from openai_tts_gui.tts import _service as service_module
from tests.fakes_tts_service import FakeChunkOutcome, FakeTTSServiceHarness


def _install_successful_provider(
    monkeypatch: pytest.MonkeyPatch, harness: FakeTTSServiceHarness
) -> None:
    monkeypatch.setattr(service_module, "OpenAI", harness.openai_class())
    monkeypatch.setattr(service_module, "require_preflight", lambda: "ffmpeg OK")


@pytest.mark.parametrize(
    ("options", "error_type"),
    [
        ({"text": " "}, TTSChunkError),
        ({"output_path": ""}, ConfigError),
        ({"model": "unknown"}, ConfigError),
        ({"voice": "unknown"}, ConfigError),
        ({"response_format": "unknown"}, ConfigError),
        ({"speed": math.nan}, ConfigError),
        ({"speed": settings.MAX_SPEED + 0.1}, ConfigError),
    ],
)
def test_generate_rejects_invalid_request_boundaries(
    tmp_path: Path, options: dict[str, str | float], error_type: type[Exception]
) -> None:
    # Given: an invalid public generation request.
    service = TTSService(api_key="sk-test")

    # When: the boundary validates its options.
    request: dict[str, str | float] = {
        "text": "text",
        "output_path": str(tmp_path / "out.wav"),
    }
    request.update(options)
    with pytest.raises(error_type):
        service.generate(**request)

    # Then: validation fails before any provider or filesystem work.


def test_serial_callbacks_and_sidecar_failure_does_not_publish_unverified_audio(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: a one-chunk provider result and callbacks for the public lifecycle.
    output = tmp_path / "callbacks.wav"
    harness = FakeTTSServiceHarness({"speech": [FakeChunkOutcome(audio_bytes=b"chunk")]})
    progress: list[int] = []
    status: list[str] = []
    parallelism: list[tuple[int, int]] = []
    _install_successful_provider(monkeypatch, harness)
    monkeypatch.setattr(
        service_module,
        "concatenate_audio_files",
        lambda files, destination: Path(destination).write_bytes(Path(files[0]).read_bytes()),
    )
    monkeypatch.setattr(
        service_module,
        "write_sidecar_metadata",
        lambda output_path, metadata: (_ for _ in ()).throw(OSError("sidecar unavailable")),
    )

    # When: TTSService reaches a staged sidecar publication failure.
    with pytest.raises(PublicationError):
        TTSService(api_key="sk-test").generate(
            text="speech",
            output_path=str(output),
            response_format="wav",
            on_progress=progress.append,
            on_status=status.append,
            on_parallelism=lambda active, cap: parallelism.append((active, cap)),
        )

    # Then: no canonical audio is exposed without a verified sidecar.
    assert not output.exists()
    assert progress == [1, 95]
    assert status == ["Generating chunk 1/1"]
    assert parallelism == [(0, 1), (1, 1), (0, 1)]
    assert not Path(f"{output}.json").exists()
    assert not list(tmp_path.glob("callbacks_chunks_*"))


def test_callback_failure_cleans_intermediates_and_surfaces_callback_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: a provider response and a status callback that fails at the public seam.
    output = tmp_path / "callback-failure.wav"
    harness = FakeTTSServiceHarness({"speech": [FakeChunkOutcome(audio_bytes=b"chunk")]})
    _install_successful_provider(monkeypatch, harness)

    # When: the callback rejects the status update.
    with pytest.raises(RuntimeError, match="callback failed"):
        TTSService(api_key="sk-test").generate(
            text="speech",
            output_path=str(output),
            response_format="wav",
            on_status=lambda _: (_ for _ in ()).throw(RuntimeError("callback failed")),
        )

    # Then: no output, sidecar, or temporary directory survives.
    assert not output.exists()
    assert not Path(f"{output}.json").exists()
    assert not list(tmp_path.glob("callback-failure_chunks_*"))


def test_chunk_accounting_rejects_unexpected_duplicate_and_missing_results(tmp_path: Path) -> None:
    # Given: a service task set with an independently reported result.
    service = TTSService(api_key="sk-test")
    task = service_module._ChunkTask(1, "speech", tmp_path / "chunk.wav")
    meta = service_module._ChunkRequestMeta(2, "req", "tts-1", str(task.filename), 1, 6)
    recorded: dict[int, service_module._ChunkRequestMeta] = {}
    lock = threading.Lock()

    # When / Then: invalid provider accounting fails before concatenation.
    with pytest.raises(TTSChunkError, match="Unexpected chunk result"):
        service._record_chunk_meta(
            meta=meta, chunk_meta=recorded, expected_indexes={1}, meta_lock=lock
        )
    valid = service_module._ChunkRequestMeta(1, "req", "tts-1", str(task.filename), 1, 6)
    service._record_chunk_meta(
        meta=valid,
        chunk_meta=recorded,
        expected_indexes={1},
        meta_lock=lock,
    )
    with pytest.raises(TTSChunkError, match="Duplicate result for chunk"):
        service._record_chunk_meta(
            meta=valid,
            chunk_meta=recorded,
            expected_indexes={1},
            meta_lock=lock,
        )
    with pytest.raises(TTSChunkError, match="Missing successful chunk"):
        service._ordered_chunk_meta(tasks=[task], chunk_meta={})


@pytest.mark.parametrize(
    "error",
    [
        TTSAPIError("api", status_code=429, request_id="req-429"),
        TTSChunkError("chunk", chunk_index=2, file_path="chunk.wav"),
        TTSCancelledError("cancelled"),
    ],
)
def test_retained_failures_preserve_domain_error_details(error: Exception, tmp_path: Path) -> None:
    # Given: a domain error after a user requested retained intermediate files.
    service = TTSService(api_key="sk-test")

    # When: the service annotates the public failure.
    retained = service._with_retained_dir(error, tmp_path)

    # Then: the original domain type and diagnostic fields survive.
    assert type(retained) is type(error)
    assert str(tmp_path) in str(retained)
    if isinstance(error, TTSAPIError):
        assert retained.status_code == error.status_code
        assert retained.request_id == error.request_id
    if isinstance(error, TTSChunkError):
        assert retained.chunk_index == error.chunk_index
        assert retained.file_path == error.file_path


def test_coordinator_and_cancel_waits_are_event_driven(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: coordinator capacity and cancellation events at each wait boundary.
    coordinator = service_module._RunCoordinator(1)
    cancelled = threading.Event()
    cancelled.set()

    # When: capacity and retry waits observe cancellation without polling sleeps.
    with pytest.raises(TTSCancelledError):
        coordinator.acquire(cancelled)
    coordinator.acquire(None)
    monkeypatch.setattr(service_module.time, "sleep", lambda _: coordinator.release())
    coordinator.acquire(None)
    coordinator.release()
    coordinator.acquire(None)

    wait_cancelled = threading.Event()
    monkeypatch.setattr(wait_cancelled, "is_set", lambda: False)
    monkeypatch.setattr(wait_cancelled, "wait", lambda timeout: True)
    with pytest.raises(TTSCancelledError):
        coordinator.acquire(wait_cancelled)
    coordinator.release()
    assert coordinator.snapshot() == (0, 1)
    waits: list[float] = []
    monkeypatch.setattr(service_module.time, "sleep", waits.append)
    TTSService(api_key="sk-test")._sleep_with_cancel(0.0, None)
    with pytest.raises(TTSCancelledError):
        TTSService(api_key="sk-test")._sleep_with_cancel(0.0, cancelled)

    # Then: local waiting honors immediate events and never creates an artifact.
    assert waits == [0.0]


def test_combined_cancel_event_detects_a_late_event_without_wall_clock_sleep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an event that becomes cancelled after the initial combined check.
    late_event = threading.Event()
    calls = 0

    def becomes_cancelled() -> bool:
        nonlocal calls
        calls += 1
        return calls > 1

    monkeypatch.setattr(late_event, "is_set", becomes_cancelled)

    # When: the combined event starts waiting.
    combined = service_module._CombinedCancelEvent(late_event)

    # Then: its next synchronized observation ends the wait immediately.
    assert combined.wait(0.0)
    immediate = threading.Event()
    immediate.set()
    assert service_module._CombinedCancelEvent(immediate).wait(0.0)


def test_retained_generic_domain_error_keeps_its_error_type(tmp_path: Path) -> None:
    # Given: a domain error without a specialized retained-file branch.
    error = FFmpegError("concat failed")

    # When: the service appends the retained directory diagnostic.
    retained = TTSService(api_key="sk-test")._with_retained_dir(error, tmp_path)

    # Then: callers retain the original error category.
    assert type(retained) is FFmpegError


def test_backoff_tolerates_an_unreadable_provider_header_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a provider response whose optional retry headers cannot be read.
    class BrokenHeaders:
        def get(self, key: str) -> str:
            raise OSError("headers unavailable")

    class Error(Exception):
        response = type("Response", (), {"headers": BrokenHeaders()})()

    monkeypatch.setattr(service_module.random, "uniform", lambda start, stop: 0.0)

    # When: retry backoff reads the optional response metadata.
    delay = service_module.compute_backoff(Error(), 0)

    # Then: the defensive fallback remains deterministic and usable.
    assert delay == max(1.0, float(settings.RETRY_DELAY))


def test_response_metadata_uses_http_response_headers_and_tolerates_bad_headers() -> None:
    # Given: provider response objects with alternate metadata shapes.
    service = TTSService(api_key="sk-test")

    class Response:
        request_id = None
        http_response = type(
            "HTTP",
            (),
            {"headers": {"x-request-id": "req", "openai-model": "tts-1"}},
        )()

    class BrokenResponse:
        request_id = "direct"
        response = type(
            "HTTP",
            (),
            {"headers": property(lambda _: (_ for _ in ()).throw(OSError()))},
        )()

    class RetryResponse:
        request_id = "direct"
        response = type(
            "HTTP",
            (),
            {
                "headers": {
                    "x-request-id": "ignored",
                    "openai-model": "tts-1",
                    "retry-after-ms": 42,
                }
            },
        )()

    # When: metadata is extracted.
    metadata = service._extract_response_metadata(Response())
    broken_metadata = service._extract_response_metadata(BrokenResponse())
    retry_metadata = service._extract_response_metadata(RetryResponse())

    # Then: valid headers are retained and an unreadable optional header source is non-fatal.
    assert metadata == ("req", "tts-1", None)
    assert broken_metadata == ("direct", None, None)
    assert retry_metadata == ("direct", "tts-1", {"retry-after-ms": "42"})
