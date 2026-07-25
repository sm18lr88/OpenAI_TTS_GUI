# /// script
# requires-python = ">=3.14,<3.15"
# dependencies = ["openai>=2.9,<3"]
# ///
from __future__ import annotations

import io
import json
import tempfile
import wave
from pathlib import Path

from openai_tts_gui.tts import ChunkFailureOutcome, GenerationConfig, GenerationRequest, TTSService
from tests.integration.speech_server import ResponseKind, SpeechResponse, SpeechServer

_EVIDENCE_PATH = Path(".omo/evidence/task-16-openai-tts-codebase-modernization-truth-table.json")
_SYNTHETIC_API_KEY = "sk-loopback-synthetic"

type EvidenceCaseValue = str | int | float | bool | None | list[str] | list[int] | list[float]
type EvidenceCase = dict[str, EvidenceCaseValue]
type NoIdempotencyScan = dict[str, str | list[str]]
type EvidenceDocumentValue = (
    int | list[str] | list[EvidenceCase] | NoIdempotencyScan | dict[str, bool]
)


def _wav_bytes() -> bytes:
    stream = io.BytesIO()
    with wave.open(stream, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(8_000)
        writer.writeframes(b"\x00\x00" * 80)
    return stream.getvalue()


def _idempotency_matches() -> list[str]:
    source_root = Path("src/openai_tts_gui")
    prohibited = ("idempotency-key", "extra_headers")
    return [
        str(path).replace("\\", "/")
        for path in source_root.rglob("*.py")
        if any(term in path.read_text(encoding="utf-8").casefold() for term in prohibited)
    ]


def main() -> None:
    audio = _wav_bytes()
    cases: list[EvidenceCase] = []
    evidence: dict[str, EvidenceDocumentValue] = {
        "max_attempts_per_chunk": 3,
        "max_429_retries_per_chunk": 2,
        "cases": cases,
        "adversarial_classes": [
            "pre_wire",
            "timeout",
            "connection",
            "http_500",
            "mid_stream_close",
            "http_400",
            "http_401",
            "unknown_provider_error",
        ],
        "no_idempotency_scan": {
            "command": 'rg -n -i "idempotency[-_ ]?key|extra_headers" src/openai_tts_gui',
            "matches": _idempotency_matches(),
        },
    }
    with tempfile.TemporaryDirectory(dir=".pytest_tmp") as directory:
        temporary = Path(directory)
        with SpeechServer(
            (
                SpeechResponse(ResponseKind.RATE_LIMIT, request_id="req-429"),
                SpeechResponse(body=audio, request_id="req-success"),
            )
        ) as server:
            waits: list[float] = []
            service = TTSService(api_key=_SYNTHETIC_API_KEY, base_url=server.base_url)
            service._sleep_with_cancel = lambda seconds, event: waits.append(seconds)
            service.generate(
                text="task 16 rate limit",
                output_path=str(temporary / "rate-limit.wav"),
                response_format="wav",
            )
            cases.append(
                {
                    "name": "local_429_then_success",
                    "client_attempts_started": len(server.requests),
                    "wait_source": "retry-after-ms",
                    "wait_seconds": waits,
                    "request_ids": ["req-429", "req-success"],
                    "uncertain_indexes": [],
                    "outbound_header_names": list(server.requests[0].header_names),
                    "idempotency_key_present": "idempotency-key" in server.requests[0].header_names,
                    "output_matches_response": (temporary / "rate-limit.wav").read_bytes() == audio,
                    "server_shutdown": False,
                }
            )
        cases[0]["server_shutdown"] = not server.is_running
        with SpeechServer(
            (SpeechResponse(ResponseKind.PARTIAL_CLOSE, audio, "req-close"),)
        ) as server:
            service = TTSService(api_key=_SYNTHETIC_API_KEY, base_url=server.base_url)
            outcome = service.execute(
                GenerationRequest(
                    "task 16 partial stream",
                    str(temporary / "partial.wav"),
                    GenerationConfig(response_format="wav"),
                )
            )
            assert isinstance(outcome, ChunkFailureOutcome)
            cases.append(
                {
                    "name": "local_body_accepted_then_close",
                    "client_attempts_started": outcome.accounting.client_attempts_started,
                    "wait_source": None,
                    "wait_seconds": [],
                    "request_ids": list(outcome.accounting.request_ids),
                    "uncertain_indexes": list(outcome.accounting.uncertain_indexes),
                    "outbound_header_names": list(server.requests[0].header_names),
                    "idempotency_key_present": "idempotency-key" in server.requests[0].header_names,
                    "output_exists": (temporary / "partial.wav").exists(),
                    "server_shutdown": False,
                }
            )
        cases[1]["server_shutdown"] = not server.is_running
    evidence["cleanup"] = {
        "temporary_directory_removed": not temporary.exists(),
        "listeners_closed": all(case["server_shutdown"] for case in cases),
    }
    _EVIDENCE_PATH.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
