from __future__ import annotations

import threading
from pathlib import Path

import pytest

from openai_tts_gui.errors import TTSCancelledError
from openai_tts_gui.tts import TTSService
from openai_tts_gui.tts import _service as service_module
from tests.fakes_tts_service import FakeChunkOutcome, FakeTTSServiceHarness


def test_parallel_cancellation_after_chunk_completion_skips_publication(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: parallel chunks that complete before the user cancels at finalization.
    output = tmp_path / "cancel-finalization.wav"
    cancellation = threading.Event()
    concat_calls: list[list[str]] = []
    harness = FakeTTSServiceHarness(
        {
            "chunk-one": [FakeChunkOutcome(audio_bytes=b"one")],
            "chunk-two": [FakeChunkOutcome(audio_bytes=b"two")],
        }
    )

    def fake_concat(files: list[str], destination: str) -> None:
        concat_calls.append(files)
        Path(destination).write_bytes(b"published audio")

    def cancel_at_final_progress(progress: int) -> None:
        if progress == 95:
            cancellation.set()

    monkeypatch.setattr(service_module, "OpenAI", harness.openai_class())
    monkeypatch.setattr(service_module, "require_preflight", lambda: "ffmpeg OK")
    monkeypatch.setattr(service_module, "concatenate_audio_files", fake_concat)
    monkeypatch.setattr(service_module, "split_text", lambda text, size: ["chunk-one", "chunk-two"])

    # When: cancellation arrives after all chunks are ready but before publication.
    with pytest.raises(TTSCancelledError):
        TTSService(api_key="sk-test").generate(
            text="two chunk script",
            output_path=str(output),
            response_format="wav",
            parallelism=2,
            on_progress=cancel_at_final_progress,
            cancel_event=cancellation,
        )

    # Then: the cancelled request never publishes an audio artifact or sidecar.
    assert cancellation.is_set()
    assert len(harness.write_order) == 2
    assert concat_calls == []
    assert not output.exists()
    assert not Path(f"{output}.json").exists()
    assert not list(tmp_path.glob("cancel-finalization_chunks_*"))
