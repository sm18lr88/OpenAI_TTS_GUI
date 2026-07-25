from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Never

from openai_tts_gui.tts import TTSService
from openai_tts_gui.tts._contracts import GenerationConfig, GenerationRequest
from openai_tts_gui.tts._outcomes import (
    PublicationFailureOutcome,
    PublicationRecoveryFailureOutcome,
)
from openai_tts_gui.tts._publication_types import CanonicalState, PublicationFailureReason
from tests.fakes_tts_service import FakeChunkOutcome, FakeTTSServiceHarness


def _configure_generation(monkeypatch, harness: FakeTTSServiceHarness) -> None:
    monkeypatch.setattr("openai_tts_gui.tts._service.OpenAI", harness.openai_class())
    monkeypatch.setattr("openai_tts_gui.tts._service.require_preflight", lambda: "ffmpeg OK")
    monkeypatch.setattr(
        "openai_tts_gui.tts._service.split_text", lambda _text, _size: ["one", "two"]
    )


def _harness() -> FakeTTSServiceHarness:
    return FakeTTSServiceHarness(
        {
            "one": [FakeChunkOutcome(audio_bytes=b"one", request_id="req-one")],
            "two": [FakeChunkOutcome(audio_bytes=b"two", request_id="req-two")],
        }
    )


def _request(output: Path) -> GenerationRequest:
    return GenerationRequest("one two", str(output), GenerationConfig(response_format="wav"))


def test_execution_reports_audio_staging_failure(monkeypatch, tmp_path: Path) -> None:
    # Given: concatenation cannot write the staged audio artifact.
    _configure_generation(monkeypatch, _harness())

    def fail_concatenate(_files: list[str], _output: str) -> None:
        raise OSError("audio staging blocked")

    monkeypatch.setattr("openai_tts_gui.tts._service.concatenate_audio_files", fail_concatenate)

    # When: the service executes a normal generation request.
    outcome = TTSService(api_key="sk-test").execute(_request(tmp_path / "published.wav"))

    # Then: it reports the audio staging cutpoint without publishing an output.
    assert isinstance(outcome, PublicationFailureOutcome)
    assert outcome.reason is PublicationFailureReason.STAGE_AUDIO
    assert outcome.finalization.canonical_state is CanonicalState.ORIGINAL_AUDIO_WITHOUT_SIDECAR


def test_execution_reports_empty_staged_audio(monkeypatch, tmp_path: Path) -> None:
    # Given: concatenation creates an empty staged audio artifact.
    _configure_generation(monkeypatch, _harness())

    def write_empty_audio(_files: list[str], output: str) -> None:
        Path(output).touch()

    monkeypatch.setattr("openai_tts_gui.tts._service.concatenate_audio_files", write_empty_audio)

    # When: publication validates the staged audio.
    outcome = TTSService(api_key="sk-test").execute(_request(tmp_path / "published.wav"))

    # Then: empty audio is classified as validation failure.
    assert isinstance(outcome, PublicationFailureOutcome)
    assert outcome.reason is PublicationFailureReason.VALIDATE_AUDIO


def test_execution_reports_sidecar_staging_failure(monkeypatch, tmp_path: Path) -> None:
    # Given: staged audio exists but writing the staged sidecar is denied.
    _configure_generation(monkeypatch, _harness())

    def write_audio(_files: list[str], output: str) -> None:
        Path(output).write_bytes(b"staged-audio")

    def fail_sidecar(_audio_path: str, _sidecar: Never) -> None:
        raise OSError("sidecar staging blocked")

    monkeypatch.setattr("openai_tts_gui.tts._service.concatenate_audio_files", write_audio)
    monkeypatch.setattr("openai_tts_gui.tts._service.write_sidecar_metadata", fail_sidecar)

    # When: publication writes the staged sidecar.
    outcome = TTSService(api_key="sk-test").execute(_request(tmp_path / "published.wav"))

    # Then: sidecar staging is the exact typed failure reason.
    assert isinstance(outcome, PublicationFailureOutcome)
    assert outcome.reason is PublicationFailureReason.STAGE_SIDECAR


def test_execution_reports_invalid_staged_sidecar(monkeypatch, tmp_path: Path) -> None:
    # Given: staged audio exists and the sidecar writer emits invalid JSON.
    _configure_generation(monkeypatch, _harness())

    def write_audio(_files: list[str], output: str) -> None:
        Path(output).write_bytes(b"staged-audio")

    def write_invalid_sidecar(audio_path: str, _sidecar: Never) -> None:
        Path(f"{audio_path}.json").write_text("not-json", encoding="utf-8")

    monkeypatch.setattr("openai_tts_gui.tts._service.concatenate_audio_files", write_audio)
    monkeypatch.setattr("openai_tts_gui.tts._service.write_sidecar_metadata", write_invalid_sidecar)

    # When: publication verifies the staged sidecar.
    outcome = TTSService(api_key="sk-test").execute(_request(tmp_path / "published.wav"))

    # Then: invalid sidecar data is classified at its validation cutpoint.
    assert isinstance(outcome, PublicationFailureOutcome)
    assert outcome.reason is PublicationFailureReason.VALIDATE_SIDECAR


def test_execution_reports_unverified_staged_sidecar(monkeypatch, tmp_path: Path) -> None:
    # Given: staging succeeds but sidecar verification returns an unverified status.
    _configure_generation(monkeypatch, _harness())

    def write_audio(_files: list[str], output: str) -> None:
        Path(output).write_bytes(b"staged-audio")

    monkeypatch.setattr("openai_tts_gui.tts._service.concatenate_audio_files", write_audio)
    monkeypatch.setattr(
        "openai_tts_gui.tts._publication_staging.parse_sidecar_metadata", lambda _path: None
    )
    monkeypatch.setattr(
        "openai_tts_gui.tts._publication_staging.verify_sidecar_audio",
        lambda _parsed, _audio: SimpleNamespace(status="unverified"),
    )

    # When: publication validates the otherwise staged sidecar.
    outcome = TTSService(api_key="sk-test").execute(_request(tmp_path / "published.wav"))

    # Then: the unverified status is classified as sidecar validation failure.
    assert isinstance(outcome, PublicationFailureOutcome)
    assert outcome.reason is PublicationFailureReason.VALIDATE_SIDECAR


def test_execution_restores_original_state_when_audio_replace_fails(
    monkeypatch, tmp_path: Path
) -> None:
    # Given: all staging succeeds but the staged audio cannot replace the destination.
    output = tmp_path / "published.wav"
    _configure_generation(monkeypatch, _harness())

    def write_audio(_files: list[str], staged_output: str) -> None:
        Path(staged_output).write_bytes(b"staged-audio")

    replace = os.replace

    def fail_audio_replace(source: str | Path, destination: str | Path) -> None:
        source_path = Path(source)
        if source_path.name == output.name and source_path.parent.name.startswith(
            ".published.publication-"
        ):
            raise OSError("audio replace blocked")
        replace(source, destination)

    monkeypatch.setattr("openai_tts_gui.tts._service.concatenate_audio_files", write_audio)
    monkeypatch.setattr("openai_tts_gui.tts._publication.os.replace", fail_audio_replace)

    # When: publication replaces the final audio target.
    outcome = TTSService(api_key="sk-test").execute(_request(output))

    # Then: the original no-sidecar state is retained and the exact cutpoint is reported.
    assert isinstance(outcome, PublicationFailureOutcome)
    assert outcome.reason is PublicationFailureReason.REPLACE_AUDIO
    assert outcome.finalization.canonical_state is CanonicalState.ORIGINAL_AUDIO_WITHOUT_SIDECAR
    assert not output.exists()


def test_execution_preserves_recovery_failure_subtype(monkeypatch, tmp_path: Path) -> None:
    # Given: replacing audio and restoring the backed-up sidecar both fail.
    output = tmp_path / "published.wav"
    sidecar = Path(f"{output}.json")
    output.write_bytes(b"original-audio")
    sidecar.write_bytes(b"original-sidecar")
    _configure_generation(monkeypatch, _harness())
    monkeypatch.setattr(
        "openai_tts_gui.tts._service.concatenate_audio_files",
        lambda _files, destination: Path(destination).write_bytes(b"staged-audio"),
    )
    replace = os.replace

    def fail_audio_and_restore(source: str | Path, destination: str | Path) -> None:
        source_path = Path(source)
        if source_path.name == output.name and source_path.parent.name.startswith(
            ".published.publication-"
        ):
            raise OSError("audio replace blocked")
        if source_path.name == "previous-sidecar.json":
            raise OSError("sidecar restore blocked")
        replace(source, destination)

    monkeypatch.setattr("openai_tts_gui.tts._publication.os.replace", fail_audio_and_restore)

    # When: publication attempts the recovery path.
    outcome = TTSService(api_key="sk-test").execute(_request(output))

    # Then: the modern terminal outcome retains the recovery-specific subtype and cutpoint.
    assert isinstance(outcome, PublicationRecoveryFailureOutcome)
    assert outcome.reason is PublicationFailureReason.RESTORE_SIDECAR
