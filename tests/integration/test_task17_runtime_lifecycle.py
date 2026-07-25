from __future__ import annotations

import threading
from pathlib import Path

import pytest
from PyQt6.QtCore import QTimer

from openai_tts_gui.errors import ConcurrentRunError
from openai_tts_gui.gui import workers as worker_module
from openai_tts_gui.gui.workers import TTSWorker, WorkerParameters
from openai_tts_gui.tts import (
    CancellationStage,
    CancelledOutcome,
    GenerationConfig,
    GenerationRequest,
    RunState,
    TTSService,
)
from tests.integration.speech_server import ResponseKind, SpeechResponse, SpeechServer

pytestmark = pytest.mark.integration

_SYNTHETIC_API_KEY = "sk-loopback-synthetic"


def _worker_parameters(output: Path) -> WorkerParameters:
    return {
        "api_key": _SYNTHETIC_API_KEY,
        "text": "withheld headers",
        "output_path": str(output),
        "model": "tts-1",
        "voice": "alloy",
        "response_format": "wav",
        "speed": 1.0,
    }


def test_worker_cancel_waits_for_real_withheld_headers_without_false_terminal(
    qtbot, monkeypatch, tmp_path: Path
) -> None:
    with SpeechServer((SpeechResponse(ResponseKind.WITHHELD_HEADERS),)) as server:
        monkeypatch.setattr(worker_module.config, "OPENAI_BASE_URL", server.base_url)
        monkeypatch.setattr(worker_module.config, "OPENAI_TIMEOUT", 0.4)
        worker = TTSWorker(_worker_parameters(tmp_path / "withheld.wav"))
        statuses: list[str] = []
        completed: list[str] = []
        errors: list[str] = []
        terminal_client_closed: list[bool] = []
        heartbeats: list[int] = []
        ticker = QTimer()
        ticker.timeout.connect(lambda: heartbeats.append(1))
        worker.status_update.connect(statuses.append)
        worker.tts_complete.connect(completed.append)
        worker.tts_error.connect(
            lambda _message: terminal_client_closed.append(server.wait_until_client_closed(0.0))
        )
        worker.tts_error.connect(errors.append)
        ticker.start(10)
        worker.start()
        assert server.wait_until_blocked(2.0)

        worker.cancel()
        qtbot.waitUntil(lambda: bool(statuses), timeout=1_000)
        qtbot.waitUntil(lambda: len(heartbeats) >= 2, timeout=1_000)

        assert "Cancellation requested; waiting for the provider call to return." in statuses
        assert (
            statuses.count("Cancellation requested; waiting for the provider call to return.") == 1
        )
        assert completed == []
        assert errors == []
        qtbot.waitUntil(worker.isFinished, timeout=5_000)
        ticker.stop()
        assert worker.wait(1_000)
        assert len(errors) == 1
        assert terminal_client_closed == [True]
        assert not (tmp_path / "withheld.wav").exists()
        assert server.responses_sent[0].kind == ResponseKind.WITHHELD_HEADERS
    assert not server.is_running


def test_service_rejects_concurrent_run_then_reports_withheld_header_timeout(
    tmp_path: Path,
) -> None:
    with SpeechServer((SpeechResponse(ResponseKind.WITHHELD_HEADERS),)) as server:
        service = TTSService(api_key=_SYNTHETIC_API_KEY, base_url=server.base_url, timeout=0.4)
        outcomes: list[CancelledOutcome] = []
        terminal = threading.Event()

        def execute_first_run() -> None:
            outcome = service.execute(
                GenerationRequest(
                    "first run",
                    str(tmp_path / "first.wav"),
                    GenerationConfig(response_format="wav"),
                )
            )
            assert isinstance(outcome, CancelledOutcome)
            outcomes.append(outcome)
            terminal.set()

        worker = threading.Thread(target=execute_first_run)
        worker.start()
        assert server.wait_until_blocked(2.0)

        with pytest.raises(ConcurrentRunError):
            service.execute(
                GenerationRequest(
                    "second run",
                    str(tmp_path / "second.wav"),
                    GenerationConfig(response_format="wav"),
                )
            )
        assert service.request_cancel() is CancellationStage.AWAITING_PROVIDER_RESPONSE

        assert server.wait_until_client_closed(5.0)
        assert terminal.wait(5.0)
        worker.join(timeout=1.0)
        assert len(outcomes) == 1
        assert (
            outcomes[0].accounting.cancellation_stage
            is CancellationStage.AWAITING_PROVIDER_RESPONSE
        )
        assert outcomes[0].accounting.uncertain_indexes == (1,)
        assert not (tmp_path / "first.wav").exists()
        assert not (tmp_path / "second.wav").exists()
    assert not server.is_running


def test_real_blocked_stream_closes_before_its_owner_emits_terminal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    with SpeechServer((SpeechResponse(ResponseKind.BLOCKED_AUDIO),)) as server:
        service = TTSService(api_key=_SYNTHETIC_API_KEY, base_url=server.base_url, timeout=2.0)
        outcomes: list[CancelledOutcome] = []
        terminal_after_close: list[bool] = []
        terminal = threading.Event()
        response_registered = threading.Event()
        original_register_response = RunState.register_response

        def record_response_registration(state: RunState, key, response) -> bool:
            accepted = original_register_response(state, key, response)
            response_registered.set()
            return accepted

        monkeypatch.setattr(RunState, "register_response", record_response_registration)

        def execute_stream() -> None:
            outcome = service.execute(
                GenerationRequest(
                    "blocked stream",
                    str(tmp_path / "blocked.wav"),
                    GenerationConfig(response_format="wav"),
                )
            )
            assert isinstance(outcome, CancelledOutcome)
            terminal_after_close.append(server.wait_until_client_closed(0.0))
            outcomes.append(outcome)
            terminal.set()

        worker = threading.Thread(target=execute_stream)
        worker.start()
        assert server.wait_until_blocked(2.0)
        assert response_registered.wait(2.0)

        assert service.request_cancel() is CancellationStage.DURING_PROVIDER_STREAM

        assert server.wait_until_client_closed(5.0)
        assert terminal.wait(5.0)
        worker.join(timeout=1.0)
        assert terminal_after_close == [True]
        assert len(outcomes) == 1
        assert outcomes[0].accounting.cancellation_stage is CancellationStage.DURING_PROVIDER_STREAM
        assert not (tmp_path / "blocked.wav").exists()
    assert not server.is_running
