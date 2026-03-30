from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class FakeChunkOutcome:
    audio_bytes: bytes = b"\x00"
    delay_seconds: float = 0.0
    request_id: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    error: Exception | None = None
    response_attr: str = "response"


@dataclass(slots=True)
class FakeEvent:
    kind: str
    chunk_input: str
    attempt: int
    thread_name: str
    detail: str | None = None


class FakeHTTPResponse:
    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.headers = dict(headers or {})


class FakeRateLimitError(Exception):
    def __init__(
        self,
        message: str = "rate limited",
        *,
        headers: dict[str, str] | None = None,
        request_id: str | None = None,
    ) -> None:
        Exception.__init__(self, message)
        self.message = message
        self.request_id = request_id
        self.response = FakeHTTPResponse(headers)


class FakeAPIStatusError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        request_id: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        Exception.__init__(self, message)
        self.message = message
        self.status_code = status_code
        self.request_id = request_id
        self.response = FakeHTTPResponse(headers)


class FakeStreamResponse:
    def __init__(
        self,
        harness: FakeTTSServiceHarness,
        api_params: dict[str, Any],
        attempt: int,
        outcome: FakeChunkOutcome,
    ) -> None:
        headers = dict(outcome.headers)
        if outcome.request_id and "x-request-id" not in headers:
            headers["x-request-id"] = outcome.request_id
        self.request_id = outcome.request_id
        self._audio_bytes = outcome.audio_bytes
        self._delay_seconds = outcome.delay_seconds
        self._harness = harness
        self._api_params = dict(api_params)
        self._attempt = attempt
        setattr(self, outcome.response_attr, FakeHTTPResponse(headers))

    def stream_to_file(self, filename: str) -> None:
        if self._delay_seconds > 0:
            time.sleep(self._delay_seconds)
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self._audio_bytes)
        self._harness._record_write(str(path))
        self._harness._record_event(
            FakeEvent(
                kind="write",
                chunk_input=str(self._api_params["input"]),
                attempt=self._attempt,
                thread_name=threading.current_thread().name,
                detail=str(path),
            )
        )


class FakeStreamingResponseContext:
    def __init__(
        self,
        harness: FakeTTSServiceHarness,
        api_params: dict[str, Any],
        attempt: int,
        outcome: FakeChunkOutcome,
    ) -> None:
        self._harness = harness
        self._api_params = dict(api_params)
        self._attempt = attempt
        self._outcome = outcome

    def __enter__(self) -> FakeStreamResponse:
        self._harness._record_event(
            FakeEvent(
                kind="enter",
                chunk_input=str(self._api_params["input"]),
                attempt=self._attempt,
                thread_name=threading.current_thread().name,
            )
        )
        if self._outcome.delay_seconds > 0 and self._outcome.error is not None:
            time.sleep(self._outcome.delay_seconds)
        if self._outcome.error is not None:
            self._harness._record_event(
                FakeEvent(
                    kind="raise",
                    chunk_input=str(self._api_params["input"]),
                    attempt=self._attempt,
                    thread_name=threading.current_thread().name,
                    detail=type(self._outcome.error).__name__,
                )
            )
            raise self._outcome.error
        return FakeStreamResponse(self._harness, self._api_params, self._attempt, self._outcome)

    def __exit__(self, exc_type, exc, tb) -> bool:
        self._harness._record_event(
            FakeEvent(
                kind="exit",
                chunk_input=str(self._api_params["input"]),
                attempt=self._attempt,
                thread_name=threading.current_thread().name,
                detail=None if exc is None else type(exc).__name__,
            )
        )
        return False


class FakeTTSServiceHarness:
    def __init__(self, plan: dict[str, list[FakeChunkOutcome]]) -> None:
        self._plan = {chunk_input: list(outcomes) for chunk_input, outcomes in plan.items()}
        self._lock = threading.Lock()
        self._attempts_by_input: dict[str, int] = {chunk_input: 0 for chunk_input in self._plan}
        self.client_kwargs: list[dict[str, Any]] = []
        self.api_calls: list[dict[str, Any]] = []
        self.write_order: list[str] = []
        self.events: list[FakeEvent] = []

    def _record_event(self, event: FakeEvent) -> None:
        with self._lock:
            self.events.append(event)

    def _record_write(self, filename: str) -> None:
        with self._lock:
            self.write_order.append(filename)

    def _next_outcome(self, chunk_input: str) -> tuple[int, FakeChunkOutcome]:
        with self._lock:
            if chunk_input not in self._plan:
                raise AssertionError(f"No scripted fake outcome for input: {chunk_input!r}")
            attempt = self._attempts_by_input[chunk_input] + 1
            outcomes = self._plan[chunk_input]
            if attempt > len(outcomes):
                raise AssertionError(
                    f"No scripted fake outcome for input {chunk_input!r} attempt {attempt}."
                )
            self._attempts_by_input[chunk_input] = attempt
            return attempt, outcomes[attempt - 1]

    def openai_class(self) -> type:
        harness = self

        class FakeOpenAI:
            def __init__(self, **kwargs: Any) -> None:
                with harness._lock:
                    harness.client_kwargs.append(dict(kwargs))
                self.audio = type(
                    "AudioNamespace",
                    (),
                    {"speech": type("SpeechNamespace", (), {"with_streaming_response": self})()},
                )()

            def create(self, **api_params: Any) -> FakeStreamingResponseContext:
                attempt, outcome = harness._next_outcome(str(api_params["input"]))
                with harness._lock:
                    harness.api_calls.append(
                        {
                            "attempt": attempt,
                            "api_params": dict(api_params),
                            "thread_name": threading.current_thread().name,
                        }
                    )
                harness._record_event(
                    FakeEvent(
                        kind="create",
                        chunk_input=str(api_params["input"]),
                        attempt=attempt,
                        thread_name=threading.current_thread().name,
                    )
                )
                return FakeStreamingResponseContext(harness, dict(api_params), attempt, outcome)

        return FakeOpenAI


__all__ = [
    "FakeAPIStatusError",
    "FakeChunkOutcome",
    "FakeEvent",
    "FakeRateLimitError",
    "FakeTTSServiceHarness",
]
