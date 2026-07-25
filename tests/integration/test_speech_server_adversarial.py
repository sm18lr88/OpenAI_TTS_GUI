from __future__ import annotations

import socket
from urllib.parse import urlsplit

import pytest

from tests.integration.speech_server import ResponseKind, SpeechResponse, SpeechServer

pytestmark = pytest.mark.integration


def _send_raw_request(server: SpeechServer, request: bytes) -> bytes:
    parsed = urlsplit(server.base_url)
    assert parsed.hostname == "127.0.0.1"
    assert parsed.port is not None
    with socket.create_connection((parsed.hostname, parsed.port), timeout=1.0) as connection:
        connection.sendall(request)
        connection.shutdown(socket.SHUT_WR)
        return connection.recv(1024)


def test_server_records_malformed_partial_and_oversized_request_bodies() -> None:
    with SpeechServer() as server:
        malformed = _send_raw_request(
            server,
            b"POST /v1/audio/speech HTTP/1.1\r\nHost: localhost\r\nContent-Length: 1\r\n\r\n{",
        )
        partial = _send_raw_request(
            server,
            b"POST /v1/audio/speech HTTP/1.1\r\nHost: localhost\r\nContent-Length: 4\r\n\r\n{",
        )
        oversized = _send_raw_request(
            server,
            b"POST /v1/audio/speech HTTP/1.1\r\nHost: localhost\r\nContent-Length: 65537\r\n\r\n",
        )

    assert b"400" in malformed
    assert b"400" in partial
    assert b"413" in oversized
    assert [record.json_valid for record in server.requests] == [False, False, False]
    assert [record.body_complete for record in server.requests] == [True, False, False]
    assert server.requests[-1].body_too_large is True


def test_ephemeral_servers_can_be_created_repeatedly_without_listener_leaks() -> None:
    servers = [SpeechServer() for _ in range(3)]
    for server in servers:
        parsed = urlsplit(server.base_url)
        assert parsed.hostname == "127.0.0.1"
        assert parsed.port is not None
        with server:
            assert server.is_running
        assert not server.is_running
        with pytest.raises(OSError):
            socket.create_connection((parsed.hostname, parsed.port), timeout=0.1)


def test_server_withholds_response_headers_until_the_client_closes() -> None:
    # Given: a local request whose selected response accepts but withholds headers.
    with SpeechServer((SpeechResponse(ResponseKind.WITHHELD_HEADERS),)) as server:
        parsed = urlsplit(server.base_url)
        assert parsed.hostname == "127.0.0.1"
        assert parsed.port is not None
        with socket.create_connection((parsed.hostname, parsed.port), timeout=1.0) as connection:
            connection.sendall(
                b"POST /v1/audio/speech HTTP/1.1\r\nHost: localhost\r\n"
                b"Content-Type: application/json\r\nContent-Length: 2\r\n\r\n{}"
            )
            assert server.wait_until_blocked()
            connection.settimeout(0.05)

            # When: no response headers are released to the connected client.
            with pytest.raises(TimeoutError):
                connection.recv(1)

        # Then: closing the client releases the handler without stopping its server.
        assert server.wait_until_client_closed()
        assert server.is_running
