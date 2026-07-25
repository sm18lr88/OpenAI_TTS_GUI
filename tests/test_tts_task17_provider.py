from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

from openai_tts_gui.errors import ContractError, TTSCancelledError
from openai_tts_gui.tts import CancellationStage, GenerationConfig, ProviderRequest, RunState
from openai_tts_gui.tts._provider import OpenAIProviderAdapter
from openai_tts_gui.tts._run_state import AttemptKey


class _Response:
    request_id = "req-task17"
    response = SimpleNamespace(headers={"x-request-id": "req-task17"})

    def __init__(self) -> None:
        self.close_calls = 0
        self.stream_calls = 0

    def close(self) -> None:
        self.close_calls += 1

    def stream_to_file(self, filename: str) -> None:
        self.stream_calls += 1
        Path(filename).write_bytes(b"audio")


class _Context:
    def __init__(self, response: _Response, after_enter: Callable[[], None] | None = None) -> None:
        self._response = response
        self._after_enter = after_enter

    def __enter__(self) -> _Response:
        if self._after_enter is not None:
            self._after_enter()
        return self._response

    def __exit__(self, exception_type, exception, traceback) -> bool:
        return False


class _Requests:
    def __init__(self, context: _Context) -> None:
        self._context = context

    def create(self, **_params: str | float) -> _Context:
        return self._context


def _adapter(
    response: _Response, after_enter: Callable[[], None] | None = None
) -> OpenAIProviderAdapter:
    requests = _Requests(_Context(response, after_enter))
    client = SimpleNamespace(
        audio=SimpleNamespace(speech=SimpleNamespace(with_streaming_response=requests))
    )
    return OpenAIProviderAdapter(lambda: client)


def _request(path: Path) -> ProviderRequest:
    return ProviderRequest(1, "speech", str(path), GenerationConfig(response_format="wav"))


def test_provider_releases_response_when_cancellation_wins_after_headers(
    tmp_path: Path,
) -> None:
    state = RunState(1, None)
    response = _Response()
    adapter = _adapter(response, state.request_cancel)

    with pytest.raises(TTSCancelledError):
        adapter.stream(_request(tmp_path / "late.wav"), state=state, key=AttemptKey(1, 1))

    assert response.close_calls == 1
    assert state._responses == {}


def test_provider_emits_legacy_stages_without_run_state(tmp_path: Path) -> None:
    response = _Response()
    stages = []

    receipt = _adapter(response).stream(_request(tmp_path / "speech.wav"), stages.append)

    assert response.stream_calls == 1
    assert stages == [
        CancellationStage.AWAITING_PROVIDER_RESPONSE,
        CancellationStage.DURING_PROVIDER_STREAM,
    ]
    assert receipt.request_id == "req-task17"


def test_provider_rejects_run_owned_stream_without_attempt_key(tmp_path: Path) -> None:
    with pytest.raises(ContractError, match="attempt key"):
        _adapter(_Response()).stream(_request(tmp_path / "speech.wav"), state=RunState(1, None))
