from __future__ import annotations

import pytest

from openai_tts_gui.errors import FFmpegError
from openai_tts_gui.tts import _provider as provider_module
from openai_tts_gui.tts import _service as service_module


def test_provider_metadata_retains_direct_request_id_and_retry_headers() -> None:
    class Response:
        request_id = "direct"
        response = type(
            "HTTP",
            (),
            {
                "headers": {
                    "x-request-id": "ignored",
                    "openai-model": "tts-1",
                    "retry-after": "1",
                }
            },
        )()

    metadata = provider_module.extract_response_metadata(Response())

    assert metadata == ("direct", "tts-1", {"retry-after": "1"})


def test_service_preflight_maps_all_outcomes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "preflight_check", lambda: (True, "ffmpeg 7"))
    assert service_module.require_preflight() == "ffmpeg 7"

    monkeypatch.setattr(service_module, "preflight_check", lambda: (False, "not found"))
    with pytest.raises(FFmpegError, match="not found"):
        service_module.require_preflight()

    monkeypatch.setattr(service_module, "preflight_check", lambda: (False, "too old"))
    with pytest.raises(FFmpegError, match="too old"):
        service_module.require_preflight()
