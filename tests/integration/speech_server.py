from __future__ import annotations

import json
import socket
import threading
from dataclasses import asdict, dataclass
from enum import StrEnum
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import assert_never

_MAX_BODY_BYTES = 65_536
_AUDIO_PATH = "/v1/audio/speech"


class ResponseKind(StrEnum):
    AUDIO = "audio"
    RATE_LIMIT = "rate_limit"
    SERVER_ERROR = "server_error"
    EMPTY_BODY = "empty_body"
    PARTIAL_CLOSE = "partial_close"
    BLOCKED_AUDIO = "blocked_audio"
    WITHHELD_HEADERS = "withheld_headers"


@dataclass(frozen=True, slots=True)
class SpeechResponse:
    kind: ResponseKind = ResponseKind.AUDIO
    body: bytes = b"loopback-audio"
    request_id: str = "req-loopback"


@dataclass(frozen=True, slots=True)
class RequestRecord:
    method: str
    path: str
    destination: str
    authorization_present: bool
    content_length: int
    body: str
    json_valid: bool
    body_complete: bool
    body_too_large: bool
    header_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResponseRecord:
    kind: str
    status: int
    request_id: str
    bytes_sent: int


class _Server(ThreadingHTTPServer):
    contract: SpeechServer
    allow_reuse_address = True
    daemon_threads = True


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        server = self.server
        assert isinstance(server, _Server)
        server.contract._handle_post(self)

    def log_message(self, format: str, *args: str) -> None:
        return


class SpeechServer:
    def __init__(self, responses: tuple[SpeechResponse, ...] = ()) -> None:
        self._responses = responses or (SpeechResponse(),)
        self._response_index = 0
        self._requests: list[RequestRecord] = []
        self._responses_sent: list[ResponseRecord] = []
        self._lock = threading.Lock()
        self._blocked = threading.Event()
        self._client_closed = threading.Event()
        self._active_connections: set[socket.socket] = set()
        self._httpd = _Server(("127.0.0.1", 0), _Handler)
        self._httpd.contract = self
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._started = False

    def __enter__(self) -> SpeechServer:
        self._thread.start()
        self._started = True
        return self

    def __exit__(self, *_) -> None:
        self.close()

    @property
    def base_url(self) -> str:
        return f"http://{self._httpd.server_address[0]}:{self._httpd.server_address[1]}/v1"

    @property
    def requests(self) -> tuple[RequestRecord, ...]:
        with self._lock:
            return tuple(self._requests)

    @property
    def responses_sent(self) -> tuple[ResponseRecord, ...]:
        with self._lock:
            return tuple(self._responses_sent)

    @property
    def is_running(self) -> bool:
        return self._started and self._thread.is_alive()

    def wait_until_blocked(self, timeout: float = 1.0) -> bool:
        return self._blocked.wait(timeout)

    def wait_until_client_closed(self, timeout: float = 1.0) -> bool:
        return self._client_closed.wait(timeout)

    def close(self) -> None:
        self._close_active_connections()
        if self._started:
            self._httpd.shutdown()
            self._thread.join()
            self._started = False
        self._httpd.server_close()

    def write_transcript(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "base_url": self.base_url,
            "loopback_only": self.base_url.startswith("http://127.0.0.1:"),
            "server_shutdown": not self.is_running,
            "requests": [asdict(record) for record in self.requests],
            "responses": [asdict(record) for record in self.responses_sent],
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _handle_post(self, handler: _Handler) -> None:
        content_length = self._content_length(handler)
        record = self._record_request(handler, content_length)
        if record.path != _AUDIO_PATH:
            self._send_json_error(handler, 404, "req-not-found")
            return
        if record.body_too_large:
            self._send_json_error(handler, 413, "req-too-large")
            return
        if not record.json_valid or not record.body_complete:
            self._send_json_error(handler, 400, "req-invalid-body")
            return
        response = self._next_response()
        self._send_response(handler, response)

    def _content_length(self, handler: _Handler) -> int:
        try:
            return int(handler.headers.get("Content-Length", "0"))
        except ValueError:
            return 0

    def _record_request(self, handler: _Handler, content_length: int) -> RequestRecord:
        too_large = content_length > _MAX_BODY_BYTES
        raw_body = b"" if too_large else handler.rfile.read(content_length)
        try:
            body = raw_body.decode("utf-8")
            json.loads(body)
            json_valid = True
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = raw_body.decode("utf-8", errors="replace")
            json_valid = False
        record = RequestRecord(
            method=handler.command,
            path=handler.path,
            destination=self.base_url,
            authorization_present=bool(handler.headers.get("Authorization")),
            content_length=content_length,
            body=body,
            json_valid=json_valid,
            body_complete=len(raw_body) == content_length,
            body_too_large=too_large,
            header_names=tuple(sorted(header.lower() for header in handler.headers)),
        )
        with self._lock:
            self._requests.append(record)
        return record

    def _next_response(self) -> SpeechResponse:
        with self._lock:
            index = min(self._response_index, len(self._responses) - 1)
            self._response_index += 1
            return self._responses[index]

    def _send_response(self, handler: _Handler, response: SpeechResponse) -> None:
        match response.kind:
            case ResponseKind.AUDIO:
                self._send_audio(handler, response, response.body)
            case ResponseKind.RATE_LIMIT:
                self._send_json_error(handler, 429, response.request_id, retry_after=True)
            case ResponseKind.SERVER_ERROR:
                self._send_json_error(handler, 500, response.request_id)
            case ResponseKind.EMPTY_BODY:
                self._send_audio(handler, response, b"")
            case ResponseKind.PARTIAL_CLOSE:
                partial = response.body[: max(1, len(response.body) // 2)]
                self._send_audio(handler, response, partial, declared_size=len(response.body) + 1)
                handler.connection.shutdown(socket.SHUT_RDWR)
                handler.connection.close()
            case ResponseKind.BLOCKED_AUDIO:
                self._send_headers(handler, 200, response.request_id, len(response.body))
                self._wait_for_client_close(handler, response)
            case ResponseKind.WITHHELD_HEADERS:
                self._wait_for_client_close(handler, response, status=0)
            case unreachable:
                assert_never(unreachable)

    def _send_audio(
        self,
        handler: _Handler,
        response: SpeechResponse,
        body: bytes,
        declared_size: int | None = None,
    ) -> None:
        self._send_headers(handler, 200, response.request_id, declared_size or len(body))
        midpoint = len(body) // 2
        handler.wfile.write(body[:midpoint])
        handler.wfile.flush()
        handler.wfile.write(body[midpoint:])
        handler.wfile.flush()
        self._record_response(response, 200, len(body))

    def _send_json_error(
        self, handler: _Handler, status: int, request_id: str, *, retry_after: bool = False
    ) -> None:
        body = b'{"error":{"message":"loopback failure","type":"server_error"}}'
        self._send_headers(handler, status, request_id, len(body), retry_after=retry_after)
        handler.wfile.write(body)
        handler.wfile.flush()
        kind = ResponseKind.RATE_LIMIT if status == 429 else ResponseKind.SERVER_ERROR
        self._record_response(SpeechResponse(kind=kind, request_id=request_id), status, len(body))

    def _send_headers(
        self,
        handler: _Handler,
        status: int,
        request_id: str,
        size: int,
        *,
        retry_after: bool = False,
    ) -> None:
        handler.send_response(status)
        handler.send_header("Content-Type", "audio/wav")
        handler.send_header("Content-Length", str(size))
        handler.send_header("x-request-id", request_id)
        handler.send_header("openai-model", "tts-1")
        if retry_after:
            handler.send_header("retry-after-ms", "1")
            handler.send_header("retry-after", "1")
        handler.end_headers()
        handler.wfile.flush()

    def _record_response(self, response: SpeechResponse, status: int, bytes_sent: int) -> None:
        with self._lock:
            self._responses_sent.append(
                ResponseRecord(response.kind.value, status, response.request_id, bytes_sent)
            )

    def _wait_for_client_close(
        self, handler: _Handler, response: SpeechResponse, *, status: int = 200
    ) -> None:
        connection = handler.connection
        with self._lock:
            self._active_connections.add(connection)
        self._blocked.set()
        try:
            client_closed = connection.recv(1) == b""
        except OSError:
            client_closed = True
        if client_closed:
            self._client_closed.set()
            self._record_response(response, status, 0)
        with self._lock:
            self._active_connections.discard(connection)

    def _close_active_connections(self) -> None:
        with self._lock:
            connections = tuple(self._active_connections)
        for connection in connections:
            connection.shutdown(socket.SHUT_RDWR)
            connection.close()
