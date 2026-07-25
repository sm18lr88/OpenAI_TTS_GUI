from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from openai_tts_gui.tts import (
    GenerationConfig,
    GenerationRequest,
    ProviderFailureOutcome,
    SuccessOutcome,
    TTSService,
    compute_backoff,
)
from openai_tts_gui.tts import _service as service_module
from tests.fakes_tts_service import (
    FakeAPIStatusError,
    FakeChunkOutcome,
    FakeRateLimitError,
    FakeTTSServiceHarness,
)


class FakeTimeoutError(Exception):
    pass


class FakeConnectionError(Exception):
    pass


class FakeUnknownProviderError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class NonRetryCase:
    name: str
    error: Exception
    error_symbol: str
    uncertain: bool
    request_ids: tuple[str, ...]


def _execute_script(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    outcome: FakeChunkOutcome,
    error_symbol: str,
) -> tuple[ProviderFailureOutcome | SuccessOutcome, FakeTTSServiceHarness, list[float]]:
    harness = FakeTTSServiceHarness({"speech": [outcome]})
    monkeypatch.setattr(service_module, "OpenAI", harness.openai_class())
    monkeypatch.setattr(service_module, "require_preflight", lambda: "ffmpeg OK")
    monkeypatch.setattr(
        service_module,
        "concatenate_audio_files",
        lambda files, destination: Path(destination).write_bytes(Path(files[0]).read_bytes()),
    )
    monkeypatch.setattr(service_module, error_symbol, type(outcome.error))
    service = TTSService(api_key="synthetic")
    waits: list[float] = []
    monkeypatch.setattr(service, "_sleep_with_cancel", lambda seconds, event: waits.append(seconds))
    result = service.execute(
        GenerationRequest(
            "speech", str(tmp_path / "out.wav"), GenerationConfig(response_format="wav")
        )
    )
    assert isinstance(result, ProviderFailureOutcome | SuccessOutcome)
    return result, harness, waits


@pytest.mark.parametrize(
    "case",
    [
        NonRetryCase("pre_wire", FakeConnectionError("pre-wire"), "APIConnectionError", True, ()),
        NonRetryCase("timeout", FakeTimeoutError("timeout"), "APITimeoutError", True, ()),
        NonRetryCase(
            "connection", FakeConnectionError("connection"), "APIConnectionError", True, ()
        ),
        NonRetryCase(
            "server_error",
            FakeAPIStatusError("server", status_code=500, request_id="req-500"),
            "APIStatusError",
            True,
            ("req-500",),
        ),
        NonRetryCase(
            "validation",
            FakeAPIStatusError("invalid", status_code=400, request_id="req-400"),
            "APIStatusError",
            False,
            ("req-400",),
        ),
        NonRetryCase(
            "authentication",
            FakeAPIStatusError("auth", status_code=401, request_id="req-401"),
            "APIStatusError",
            False,
            ("req-401",),
        ),
        NonRetryCase("unknown", FakeUnknownProviderError("unknown"), "APIError", True, ()),
    ],
    ids=lambda case: case.name,
)
def test_truth_table_non_429_provider_outcomes_are_single_attempt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, case: NonRetryCase
) -> None:
    # Given: one provider outcome that is not an explicit HTTP 429.
    result, harness, waits = _execute_script(
        monkeypatch,
        tmp_path,
        FakeChunkOutcome(error=case.error),
        case.error_symbol,
    )

    # When: the public typed service executes the request.

    # Then: it never retries or claims certainty beyond the observed response.
    assert isinstance(result, ProviderFailureOutcome)
    assert len(harness.api_calls) == 1
    assert waits == []
    assert result.accounting.client_attempts_started == 1
    assert result.accounting.uncertain_indexes == ((1,) if case.uncertain else ())
    assert result.accounting.request_ids == case.request_ids
    assert "extra_headers" not in harness.api_calls[0]["api_params"]


def test_truth_table_explicit_429_has_two_retry_budget_and_collects_request_ids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: three explicit rate-limit responses with distinct provider request IDs.
    rate_limits = [
        FakeChunkOutcome(error=FakeRateLimitError(request_id=f"req-429-{attempt}"))
        for attempt in range(1, 4)
    ]
    harness = FakeTTSServiceHarness({"speech": rate_limits})
    monkeypatch.setattr(service_module, "OpenAI", harness.openai_class())
    monkeypatch.setattr(service_module, "RateLimitError", FakeRateLimitError)
    monkeypatch.setattr(service_module, "require_preflight", lambda: "ffmpeg OK")
    service = TTSService(api_key="synthetic")
    waits: list[float] = []
    monkeypatch.setattr(service, "_sleep_with_cancel", lambda seconds, event: waits.append(seconds))
    monkeypatch.setattr(service_module, "compute_backoff", lambda error, attempt: 0.0)

    # When: the retry budget is exhausted.
    result = service.execute(
        GenerationRequest(
            "speech", str(tmp_path / "out.wav"), GenerationConfig(response_format="wav")
        )
    )

    # Then: three total attempts yield two waits, no fourth invocation, and definitive accounting.
    assert isinstance(result, ProviderFailureOutcome)
    assert len(harness.api_calls) == 3
    assert waits == [0.0, 0.0]
    assert result.accounting.client_attempts_started == 3
    assert result.accounting.request_ids == ("req-429-1", "req-429-2", "req-429-3")
    assert result.accounting.uncertain_indexes == ()
    assert result.status_code == 429
    assert result.request_id == "req-429-3"


def test_truth_table_explicit_429_then_success_has_one_retry_and_two_receipts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: an explicit HTTP 429 followed by a successful response.
    harness = FakeTTSServiceHarness(
        {
            "speech": [
                FakeChunkOutcome(error=FakeRateLimitError(request_id="req-rate")),
                FakeChunkOutcome(audio_bytes=b"audio", request_id="req-success"),
            ]
        }
    )
    monkeypatch.setattr(service_module, "OpenAI", harness.openai_class())
    monkeypatch.setattr(service_module, "RateLimitError", FakeRateLimitError)
    monkeypatch.setattr(service_module, "require_preflight", lambda: "ffmpeg OK")
    monkeypatch.setattr(
        service_module,
        "concatenate_audio_files",
        lambda files, destination: Path(destination).write_bytes(Path(files[0]).read_bytes()),
    )
    monkeypatch.setattr(service_module, "compute_backoff", lambda error, attempt: 0.0)
    service = TTSService(api_key="synthetic")
    waits: list[float] = []
    monkeypatch.setattr(service, "_sleep_with_cancel", lambda seconds, event: waits.append(seconds))

    # When: the public execution API receives the accepted retry response.
    result = service.execute(
        GenerationRequest(
            "speech", str(tmp_path / "out.wav"), GenerationConfig(response_format="wav")
        )
    )

    # Then: both request IDs and exactly two started adapter calls are accounted for.
    assert isinstance(result, SuccessOutcome)
    assert len(harness.api_calls) == 2
    assert waits == [0.0]
    assert result.accounting.client_attempts_started == 2
    assert result.accounting.request_ids == ("req-rate", "req-success")
    assert result.accounting.uncertain_indexes == ()


@pytest.mark.parametrize(
    ("headers", "expected_wait"),
    [
        ({"retry-after-ms": "250"}, 0.25),
        ({"retry-after": "1.5"}, 1.5),
        ({"retry-after-ms": "invalid", "retry-after": "1.5"}, 1.5),
    ],
)
def test_truth_table_429_wait_uses_first_valid_retry_header(
    monkeypatch: pytest.MonkeyPatch, headers: dict[str, str], expected_wait: float
) -> None:
    # Given: deterministic fallback jitter and provider retry headers.
    monkeypatch.setattr(service_module.random, "uniform", lambda start, stop: 0.0)

    # When: the 429 retry delay is selected.
    wait = compute_backoff(FakeRateLimitError(headers=headers), 0)

    # Then: valid milliseconds precede valid seconds, while malformed values are skipped.
    assert wait == expected_wait


def test_truth_table_non_429_rate_limit_type_is_not_retried(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: an SDK rate-limit class that does not carry the explicit HTTP 429 status.
    result, harness, waits = _execute_script(
        monkeypatch,
        tmp_path,
        FakeChunkOutcome(error=FakeRateLimitError(status_code=503, request_id="req-ambiguous")),
        "RateLimitError",
    )

    # When / Then: the classification stays single-attempt and uncertain.
    assert isinstance(result, ProviderFailureOutcome)
    assert len(harness.api_calls) == 1
    assert waits == []
    assert result.accounting.uncertain_indexes == (1,)
    assert result.accounting.request_ids == ("req-ambiguous",)


def test_service_exposes_total_attempt_and_429_retry_limits() -> None:
    # Given: a service instance with the fixed provider policy.
    service = TTSService(api_key="synthetic")

    # When / Then: the visible limits distinguish total attempts from retries.
    assert service.max_attempts_per_chunk == 3
    assert service.max_429_retries_per_chunk == 2
