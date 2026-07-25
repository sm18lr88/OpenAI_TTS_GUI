from __future__ import annotations

import io
import json
import wave
from pathlib import Path

import pytest

from openai_tts_gui.config import settings
from openai_tts_gui.tts import ChunkFailureOutcome, ProviderFailureOutcome, TTSService
from openai_tts_gui.tts import _service as service_module
from tests.integration.speech_server import ResponseKind, SpeechResponse, SpeechServer

pytestmark = pytest.mark.integration

_SYNTHETIC_API_KEY = "sk-loopback-synthetic"


def _wav_bytes() -> bytes:
    stream = io.BytesIO()
    with wave.open(stream, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(8_000)
        writer.writeframes(b"\x00\x00" * 80)
    return stream.getvalue()


def test_service_uses_real_sdk_for_instruction_sidecar_and_single_chunk_cleanup(
    tmp_path: Path,
) -> None:
    # Given: a local provider response with valid WAV bytes and an instruction-capable model.
    output = tmp_path / "instruction.wav"
    audio = _wav_bytes()
    with SpeechServer((SpeechResponse(body=audio, request_id="req-instruction"),)) as server:
        service = TTSService(api_key=_SYNTHETIC_API_KEY, base_url=server.base_url)

        # When: the public service runs its real SDK and single-file concatenation path.
        message = service.generate(
            text="loopback speech",
            output_path=str(output),
            model=settings.GPT_4O_MINI_TTS_MODEL,
            response_format="wav",
            instructions="warm and clear",
        )

        # Then: the request, output, sidecar, and temporary directory reflect the provider outcome.
        request = server.requests[0]
        metadata = json.loads(Path(f"{output}.json").read_text(encoding="utf-8"))
        assert request.authorization_present
        assert json.loads(request.body)["instructions"] == "warm and clear"
        assert output.read_bytes() == audio
        assert "saved successfully" in message
        assert metadata["request_meta"][0]["request_id"] == "req-instruction"
        assert metadata["request_meta"][0]["model_header"] == "tts-1"
        assert not list(tmp_path.glob("instruction_chunks_*"))
    assert not server.is_running


def test_public_service_retries_real_loopback_429_with_request_receipts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: a real SDK loopback fault followed by a successful WAV response.
    output = tmp_path / "rate-limit.wav"
    audio = _wav_bytes()
    with SpeechServer(
        (
            SpeechResponse(ResponseKind.RATE_LIMIT, request_id="req-429"),
            SpeechResponse(body=audio, request_id="req-ok"),
        )
    ) as server:
        service = TTSService(api_key=_SYNTHETIC_API_KEY, base_url=server.base_url)
        retry_waits: list[float] = []
        monkeypatch.setattr(
            service,
            "_sleep_with_cancel",
            lambda wait, event: retry_waits.append(wait),
        )
        monkeypatch.setattr(service_module, "compute_backoff", lambda error, attempt: 0.0)

        # When: TTSService applies its retry policy around the actual OpenAI SDK response.
        service.generate(text="retry speech", output_path=str(output), response_format="wav")

        # Then: the final bytes and sidecar record the successful second request.
        metadata = json.loads(Path(f"{output}.json").read_text(encoding="utf-8"))
        assert output.read_bytes() == audio
        assert retry_waits == [0.0]
        assert [response.status for response in server.responses_sent] == [429, 200]
        assert "idempotency-key" not in server.requests[0].header_names
        assert metadata["request_meta"] == [
            {
                "attempts": 2,
                "characters": len("retry speech"),
                "chunk_index": 1,
                "file": metadata["request_meta"][0]["file"],
                "model_header": "tts-1",
                "request_id": "req-ok",
                "retry_headers": None,
            }
        ]
    assert not server.is_running


def test_service_keeps_real_loopback_500_as_one_uncertain_attempt(tmp_path: Path) -> None:
    # Given: a local provider 500 response followed by an unused success response.
    output = tmp_path / "server-error.wav"
    with SpeechServer(
        (
            SpeechResponse(ResponseKind.SERVER_ERROR, request_id="req-500"),
            SpeechResponse(body=_wav_bytes(), request_id="req-unused"),
        )
    ) as server:
        service = TTSService(api_key=_SYNTHETIC_API_KEY, base_url=server.base_url)

        # When: the typed API receives the uncertain server response.
        outcome = service.execute(
            service_module.GenerationRequest(
                "server error", str(output), service_module.GenerationConfig(response_format="wav")
            )
        )

        # Then: it exposes one attempt, the provider request ID, and no output claim.
        assert isinstance(outcome, ProviderFailureOutcome)
        assert outcome.accounting.client_attempts_started == 1
        assert outcome.accounting.uncertain_indexes == (1,)
        assert outcome.accounting.request_ids == ("req-500",)
        assert len(server.requests) == 1
        assert not output.exists()
    assert not server.is_running


def test_service_serial_multi_chunk_real_loopback_retains_received_chunk_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: two real loopback responses and forced serial text chunks.
    output = tmp_path / "retained.wav"
    audio = _wav_bytes()
    monkeypatch.setattr(service_module, "split_text", lambda text, size: ["first", "second"])
    responses = (
        SpeechResponse(body=audio, request_id="req-1"),
        SpeechResponse(body=audio, request_id="req-2"),
    )
    with SpeechServer(responses) as server:
        service = TTSService(api_key=_SYNTHETIC_API_KEY, base_url=server.base_url)

        # When: real SDK requests are generated serially and retained after ffmpeg concatenation.
        message = service.generate(
            text="forced chunks",
            output_path=str(output),
            response_format="wav",
            parallelism=1,
            retain_files=True,
        )

        # Then: each local provider receipt maps to retained audio and ordered sidecar metadata.
        metadata = json.loads(Path(f"{output}.json").read_text(encoding="utf-8"))
        retained = Path(message.rsplit("\n", maxsplit=1)[-1])
        assert output.stat().st_size > len(audio)
        assert [json.loads(request.body)["input"] for request in server.requests] == [
            "first",
            "second",
        ]
        assert [item["request_id"] for item in metadata["request_meta"]] == ["req-1", "req-2"]
        assert [path.read_bytes() for path in sorted(retained.glob("*.wav"))] == [audio, audio]
        assert metadata["settings"]["parallelism_requested"] == 1
        assert metadata["settings"]["parallelism_used"] == 1
    assert not server.is_running


def test_service_parallel_multi_chunk_reports_real_worker_accounting(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: two local WAV responses and a forced parallel chunk plan.
    output = tmp_path / "parallel.wav"
    audio = _wav_bytes()
    monkeypatch.setattr(service_module, "split_text", lambda text, size: ["first", "second"])
    responses = (
        SpeechResponse(body=audio, request_id="req-1"),
        SpeechResponse(body=audio, request_id="req-2"),
    )
    with SpeechServer(responses) as server:
        worker_events: list[tuple[int, int]] = []
        progress: list[int] = []
        status: list[str] = []

        # When: the real SDK service schedules both chunks concurrently.
        TTSService(api_key=_SYNTHETIC_API_KEY, base_url=server.base_url).generate(
            text="forced chunks",
            output_path=str(output),
            response_format="wav",
            parallelism=2,
            on_progress=progress.append,
            on_status=status.append,
            on_parallelism=lambda active, cap: worker_events.append((active, cap)),
        )

        # Then: both requests complete, worker signals return to zero, and cleanup succeeds.
        assert output.exists()
        assert sorted(json.loads(request.body)["input"] for request in server.requests) == [
            "first",
            "second",
        ]
        assert progress[0] == 1
        assert progress[-1] == 100
        assert status[0] == "Generating 2 chunks with parallelism 2"
        assert worker_events[0] == (0, 2)
        assert worker_events[-1] == (0, 2)
        assert any(active == 2 for active, _ in worker_events)
        assert not list(tmp_path.glob("parallel_chunks_*"))
    assert not server.is_running


def test_service_propagates_real_mid_body_failure_without_artifact_leak(
    tmp_path: Path,
) -> None:
    # Given: a loopback response that closes before its declared audio body is complete.
    output = tmp_path / "partial.wav"
    response = SpeechResponse(ResponseKind.PARTIAL_CLOSE, _wav_bytes(), "req-close")
    with SpeechServer((response,)) as server:
        service = TTSService(api_key=_SYNTHETIC_API_KEY, base_url=server.base_url)

        # When: the real OpenAI SDK streams that partial response through the service.
        outcome = service.execute(
            service_module.GenerationRequest(
                "partial speech",
                str(output),
                service_module.GenerationConfig(response_format="wav"),
            )
        )

        # Then: the incomplete stream is a typed uncertain outcome with no completed artifact.
        assert isinstance(outcome, ChunkFailureOutcome)
        assert outcome.accounting.client_attempts_started == 1
        assert outcome.accounting.uncertain_indexes == (1,)
        assert outcome.accounting.request_ids == ("req-close",)
        assert len(server.requests) == 1
        assert not output.exists()
        assert not Path(f"{output}.json").exists()
        assert not list(tmp_path.glob("partial_chunks_*"))
    assert not server.is_running
