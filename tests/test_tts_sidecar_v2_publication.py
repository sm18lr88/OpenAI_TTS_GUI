from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Never

from openai_tts_gui.core import (
    SidecarV2,
    parse_sidecar_metadata,
    resolve_retained_directory,
    verify_sidecar_audio,
)
from openai_tts_gui.errors import PublicationError
from openai_tts_gui.tts import TTSService
from openai_tts_gui.tts._contracts import GenerationConfig, GenerationRequest
from openai_tts_gui.tts._outcomes import PublicationFailureOutcome
from openai_tts_gui.tts._publication_types import (
    CanonicalState,
    FinalizationReport,
    PublicationFailureReason,
)
from tests.fakes_tts_service import FakeChunkOutcome, FakeTTSServiceHarness


def _configure_generation(monkeypatch, harness: FakeTTSServiceHarness) -> None:
    def concatenate(_files: list[str], output_path: str) -> None:
        Path(output_path).write_bytes(b"fully-staged-final-audio")

    monkeypatch.setattr("openai_tts_gui.tts._service.OpenAI", harness.openai_class())
    monkeypatch.setattr("openai_tts_gui.tts._service.require_preflight", lambda: "ffmpeg OK")
    monkeypatch.setattr("openai_tts_gui.tts._service.concatenate_audio_files", concatenate)
    monkeypatch.setattr(
        "openai_tts_gui.tts._service.split_text", lambda _text, _size: ["one", "two"]
    )


def test_nonretained_multichunk_publication_writes_private_verified_v2_sidecar(
    monkeypatch, tmp_path: Path
) -> None:
    # Given: a multi-chunk generation carrying unique sensitive text and instructions.
    output = tmp_path / "published.wav"
    harness = FakeTTSServiceHarness(
        {
            "one": [FakeChunkOutcome(audio_bytes=b"one", request_id="req-one")],
            "two": [FakeChunkOutcome(audio_bytes=b"two", request_id="req-two")],
        }
    )
    _configure_generation(monkeypatch, harness)

    # When: final audio and sidecar are published without retaining chunks.
    TTSService(api_key="sk-task14-secret").generate(
        text="UNIQUE_RAW_TEXT_TASK14_DO_NOT_PERSIST",
        output_path=str(output),
        model="gpt-4o-mini-tts",
        voice="nova",
        response_format="wav",
        speed=1.25,
        instructions="UNIQUE_PRIVATE_INSTRUCTIONS_TASK14_DO_NOT_PERSIST",
        parallelism=2,
        retain_files=False,
    )
    sidecar_path = Path(f"{output}.json")
    payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
    parsed = parse_sidecar_metadata(sidecar_path)

    # Then: v2 identities final bytes and excludes sensitive inputs and absolute paths.
    assert payload["schema_version"] == 2
    assert isinstance(parsed, SidecarV2)
    assert verify_sidecar_audio(parsed, output).status == "verified"
    serialized = sidecar_path.read_text(encoding="utf-8")
    assert "UNIQUE_RAW_TEXT_TASK14_DO_NOT_PERSIST" not in serialized
    assert "UNIQUE_PRIVATE_INSTRUCTIONS_TASK14_DO_NOT_PERSIST" not in serialized
    assert "sk-task14-secret" not in serialized
    assert str(tmp_path) not in serialized
    assert parsed.retained_directory is None


def test_retained_multichunk_publication_persists_only_relative_directory_and_basenames(
    monkeypatch, tmp_path: Path
) -> None:
    # Given: a retained multi-chunk generation published into a nested output directory.
    output = tmp_path / "nested" / "retained.wav"
    harness = FakeTTSServiceHarness(
        {
            "one": [FakeChunkOutcome(audio_bytes=b"one", request_id="req-one")],
            "two": [FakeChunkOutcome(audio_bytes=b"two", request_id="req-two")],
        }
    )
    _configure_generation(monkeypatch, harness)

    # When: publication retains intermediate chunk files.
    TTSService(api_key="sk-test").generate(
        text="two chunks",
        output_path=str(output),
        response_format="wav",
        parallelism=2,
        retain_files=True,
    )
    parsed = parse_sidecar_metadata(Path(f"{output}.json"))

    # Then: the resolver reconstructs a local retained directory from a safe relative name.
    assert isinstance(parsed, SidecarV2)
    retained_directory = resolve_retained_directory(parsed, output)
    assert retained_directory is not None
    assert retained_directory.is_dir()
    assert all("/" not in item.file and "\\" not in item.file for item in parsed.request_meta)
    assert str(output.parent) not in Path(f"{output}.json").read_text(encoding="utf-8")


def test_execution_reports_late_sidecar_replace_failure_truthfully(
    monkeypatch, tmp_path: Path
) -> None:
    # Given: generation completes, then publication fails after the new audio replaces its target.
    output = tmp_path / "published.wav"
    harness = FakeTTSServiceHarness(
        {
            "one": [FakeChunkOutcome(audio_bytes=b"one", request_id="req-one")],
            "two": [FakeChunkOutcome(audio_bytes=b"two", request_id="req-two")],
        }
    )
    _configure_generation(monkeypatch, harness)

    def fail_sidecar_replace(*_args: Never, **_kwargs: Never) -> Never:
        raise PublicationError(
            PublicationFailureReason.REPLACE_SIDECAR,
            "blocked",
            FinalizationReport(CanonicalState.NEW_AUDIO_WITHOUT_SIDECAR),
        )

    monkeypatch.setattr("openai_tts_gui.tts._execution._publication.publish", fail_sidecar_replace)

    # When: execution converts the publication error into its typed outcome.
    outcome = TTSService(api_key="sk-test").execute(
        GenerationRequest("one two", str(output), GenerationConfig(response_format="wav"))
    )

    # Then: the published audio without its sidecar retains its actual state and cutpoint.
    assert isinstance(outcome, PublicationFailureOutcome)
    assert outcome.reason is PublicationFailureReason.REPLACE_SIDECAR
    assert outcome.finalization.canonical_state is CanonicalState.NEW_AUDIO_WITHOUT_SIDECAR


def test_execution_reports_stage_directory_failure_without_touching_destination(
    monkeypatch, tmp_path: Path
) -> None:
    # Given: output has no sidecar and the publication staging directory cannot be created.
    output = tmp_path / "published.wav"
    harness = FakeTTSServiceHarness(
        {
            "one": [FakeChunkOutcome(audio_bytes=b"one", request_id="req-one")],
            "two": [FakeChunkOutcome(audio_bytes=b"two", request_id="req-two")],
        }
    )
    _configure_generation(monkeypatch, harness)

    def fail_stage_directory(_output: Path) -> Path:
        raise OSError("stage directory blocked")

    monkeypatch.setattr(
        "openai_tts_gui.tts._execution._publication._stage_directory", fail_stage_directory
    )

    # When: the service executes its normal provider and publication flow.
    outcome = TTSService(api_key="sk-test").execute(
        GenerationRequest("one two", str(output), GenerationConfig(response_format="wav"))
    )

    # Then: stage creation is the reported cutpoint and no output pair was created.
    assert isinstance(outcome, PublicationFailureOutcome)
    assert outcome.reason is PublicationFailureReason.PREPARE_STAGE
    assert outcome.finalization.canonical_state is CanonicalState.ORIGINAL_AUDIO_WITHOUT_SIDECAR
    assert not output.exists()
    assert not Path(f"{output}.json").exists()


def test_execution_restores_existing_pair_when_sidecar_backup_fails(
    monkeypatch, tmp_path: Path
) -> None:
    # Given: an existing output pair and a backup operation that fails before the audio replacement.
    output = tmp_path / "published.wav"
    sidecar = Path(f"{output}.json")
    output.write_bytes(b"original-audio")
    sidecar.write_bytes(b"original-sidecar")
    harness = FakeTTSServiceHarness(
        {
            "one": [FakeChunkOutcome(audio_bytes=b"one", request_id="req-one")],
            "two": [FakeChunkOutcome(audio_bytes=b"two", request_id="req-two")],
        }
    )
    _configure_generation(monkeypatch, harness)
    replace = os.replace

    def fail_backup(source: str | Path, destination: str | Path) -> None:
        if Path(source) == sidecar:
            raise OSError("backup blocked")
        replace(source, destination)

    monkeypatch.setattr("openai_tts_gui.tts._publication.os.replace", fail_backup)

    # When: the service reaches publication.
    outcome = TTSService(api_key="sk-test").execute(
        GenerationRequest("one two", str(output), GenerationConfig(response_format="wav"))
    )

    # Then: both original artifacts remain canonical and the failure identifies backup precisely.
    assert isinstance(outcome, PublicationFailureOutcome)
    assert outcome.reason is PublicationFailureReason.BACKUP_SIDECAR
    assert outcome.finalization.canonical_state is CanonicalState.ORIGINAL_DESTINATION
    assert output.read_bytes() == b"original-audio"
    assert sidecar.read_bytes() == b"original-sidecar"


def test_execution_retains_new_audio_when_sidecar_replace_fails(
    monkeypatch, tmp_path: Path
) -> None:
    # Given: staging succeeds but the final sidecar replacement is denied by the filesystem.
    output = tmp_path / "published.wav"
    sidecar = Path(f"{output}.json")
    harness = FakeTTSServiceHarness(
        {
            "one": [FakeChunkOutcome(audio_bytes=b"one", request_id="req-one")],
            "two": [FakeChunkOutcome(audio_bytes=b"two", request_id="req-two")],
        }
    )
    _configure_generation(monkeypatch, harness)
    replace = os.replace

    def fail_final_sidecar(source: str | Path, destination: str | Path) -> None:
        source_path = Path(source)
        if source_path.name == sidecar.name and source_path.parent.name.startswith(
            ".published.publication-"
        ):
            raise OSError("sidecar replace blocked")
        replace(source, destination)

    monkeypatch.setattr("openai_tts_gui.tts._publication.os.replace", fail_final_sidecar)

    # When: the service publishes a new audio artifact.
    outcome = TTSService(api_key="sk-test").execute(
        GenerationRequest("one two", str(output), GenerationConfig(response_format="wav"))
    )

    # Then: staged audio is canonical and the incomplete sidecar is retained for recovery.
    assert isinstance(outcome, PublicationFailureOutcome)
    assert outcome.reason is PublicationFailureReason.REPLACE_SIDECAR
    assert outcome.finalization.canonical_state is CanonicalState.NEW_AUDIO_WITHOUT_SIDECAR
    assert output.read_bytes() == b"fully-staged-final-audio"
    assert not sidecar.exists()
    assert outcome.finalization.retained_basenames
