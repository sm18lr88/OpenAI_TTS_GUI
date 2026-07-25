from __future__ import annotations

import json
from pathlib import Path

import pytest

from openai_tts_gui.core import (
    AudioMismatch,
    AudioVerified,
    MissingAudio,
    SidecarParseError,
    SidecarRequestInput,
    SidecarV1,
    SidecarWriteInput,
    UnsupportedSidecarSchemaError,
    build_sidecar_v2,
    parse_sidecar_metadata,
    resolve_retained_directory,
    verify_sidecar_audio,
    write_sidecar_metadata,
)


def _sidecar(
    audio: Path,
    retained_directory: Path | None = None,
    environment: dict[str, str] | None = None,
    retry_headers: dict[str, str] | None = None,
    request_file: Path | str = Path(r"C:\\Users\\example\\chunk_0001.wav"),
):
    return build_sidecar_v2(
        SidecarWriteInput(
            audio_path=audio,
            model="gpt-4o-mini-tts",
            voice="nova",
            response_format="wav",
            speed=1.25,
            chunk_count=2,
            chunk_size=4096,
            parallelism_requested=2,
            parallelism_used=2,
            stream_format="wav",
            retain_files=retained_directory is not None,
            input_chars=42,
            environment=environment or {"app_version": "1.3.4", "platform": "Windows"},
            retained_directory=retained_directory,
            request_meta=(
                SidecarRequestInput(
                    chunk_index=1,
                    request_id="req-1",
                    model_header="gpt-4o-mini-tts",
                    file=request_file,
                    attempts=1,
                    characters=21,
                    retry_headers=retry_headers or {"retry-after-ms": "10"},
                ),
                SidecarRequestInput(
                    chunk_index=2,
                    request_id="req-2",
                    model_header="gpt-4o-mini-tts",
                    file=Path("/tmp/example/chunk_0002.wav"),
                    attempts=2,
                    characters=21,
                    retry_headers=None,
                ),
            ),
        )
    )


def test_v2_sidecar_round_trips_and_preserves_only_safe_support_fields(tmp_path: Path) -> None:
    # Given: staged audio plus Windows and POSIX-shaped source paths.
    audio = tmp_path / "narration.wav"
    audio.write_bytes(b"staged-audio")
    sidecar = _sidecar(audio, tmp_path / "narration_chunks_123")

    # When: the v2 sidecar is atomically published and read through the public facade.
    path = Path(write_sidecar_metadata(str(audio), sidecar))
    parsed = parse_sidecar_metadata(path)
    serialized = path.read_text(encoding="utf-8")

    # Then: typed support fields survive without text, instructions, secrets, or absolute paths.
    assert parsed == sidecar
    assert parsed.request_ids == ("req-1", "req-2")
    assert parsed.request_meta[0].file == "chunk_0001.wav"
    assert parsed.request_meta[1].file == "chunk_0002.wav"
    assert parsed.retained_directory == "narration_chunks_123"
    assert r"C:\\Users\\example" not in serialized
    assert "/tmp/example" not in serialized
    assert "instructions" not in serialized
    assert "api_key" not in serialized
    assert "raw text" not in serialized


def test_unversioned_v1_sidecar_remains_a_typed_read_only_compatibility_input() -> None:
    # Given: a current unversioned v1 sidecar payload.
    payload = {
        "parallelism_used": 2,
        "request_meta": [
            {"request_id": "req-v1-a"},
            {"request_id": "req-v1-a"},
            {"request_id": "req-v1-b"},
        ],
    }

    # When: it is parsed through the v2 reader facade.
    parsed = parse_sidecar_metadata(json.dumps(payload))

    # Then: request ID readers retain the legacy observable behavior.
    assert isinstance(parsed, SidecarV1)
    assert parsed.request_ids == ("req-v1-a", "req-v1-b")
    assert parsed.parallelism_used == 2


def test_v2_audio_identity_reports_exact_missing_and_mismatch_cases(tmp_path: Path) -> None:
    # Given: a v2 identity bound to fully staged final audio bytes.
    audio = tmp_path / "final.wav"
    audio.write_bytes(b"same-name-original")
    sidecar = _sidecar(audio)

    # When: the exact audio, absent audio, truncated audio, and replacement use the verifier.
    verified = verify_sidecar_audio(sidecar, audio)
    audio.unlink()
    missing = verify_sidecar_audio(sidecar, audio)
    audio.write_bytes(b"short")
    truncated = verify_sidecar_audio(sidecar, audio)
    audio.write_bytes(b"same-name-replaced")
    replaced = verify_sidecar_audio(sidecar, audio)

    # Then: every caller receives a typed, distinguishable outcome.
    assert isinstance(verified, AudioVerified)
    assert isinstance(missing, MissingAudio)
    assert isinstance(truncated, AudioMismatch)
    assert isinstance(replaced, AudioMismatch)


def test_v2_parser_rejects_malformed_and_unknown_schema_versions(tmp_path: Path) -> None:
    # Given: malformed JSON and a syntactically valid unknown schema.
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    unknown = json.dumps({"schema_version": 99})

    # When: callers parse through the public facade.
    with pytest.raises(SidecarParseError):
        parse_sidecar_metadata(malformed)
    with pytest.raises(UnsupportedSidecarSchemaError):
        parse_sidecar_metadata(unknown)

    # Then: bad metadata cannot silently become request ID data.


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.update({"schema_version": "2"}),
        lambda payload: payload.pop("environment"),
        lambda payload: payload.update(
            {
                "audio": {
                    "basename": "audio.wav",
                    "size_bytes": -1,
                    "sha256": "0" * 64,
                }
            }
        ),
        lambda payload: payload["settings"].update({"speed": "fast"}),
        lambda payload: payload.update({"retained_directory": "C:/private"}),
        lambda payload: payload.update({"request_meta": [{}]}),
        lambda payload: payload["request_meta"][0].update({"file": "/private.wav"}),
        lambda payload: payload["request_meta"][0].update({"request_id": 1}),
        lambda payload: payload["request_meta"][0].update({"chunk_index": True}),
        lambda payload: payload["settings"].update({"retain_files": 1}),
        lambda payload: payload["request_meta"][0].update({"retry_headers": []}),
        lambda payload: payload["environment"].update({"hostname": "private-host"}),
        lambda payload: payload["request_meta"][0].update(
            {"retry_headers": {"x-request-id": "req-1"}}
        ),
    ],
)
def test_v2_parser_rejects_invalid_nested_publication_fields(tmp_path: Path, mutation) -> None:
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"audio")
    payload = json.loads(json.dumps(_sidecar(audio).to_payload()))

    mutation(payload)

    with pytest.raises(SidecarParseError):
        parse_sidecar_metadata(json.dumps(payload))


def test_v2_parser_accepts_an_integer_speed(tmp_path: Path) -> None:
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"audio")
    payload = json.loads(json.dumps(_sidecar(audio).to_payload()))
    payload["settings"]["speed"] = 1

    parsed = parse_sidecar_metadata(json.dumps(payload))

    assert parsed.settings.speed == 1.0


def test_v2_builder_rejects_secret_and_absolute_environment_values(tmp_path: Path) -> None:
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"audio")

    with pytest.raises(SidecarParseError):
        _sidecar(audio, environment={"OPENAI_API_KEY": "sk-private"})
    with pytest.raises(SidecarParseError):
        _sidecar(audio, environment={"data_directory": r"C:\\Users\\private"})


def test_v2_builder_rejects_unapproved_environment_and_retry_metadata(tmp_path: Path) -> None:
    # Given: public construction with metadata outside the generated-safe contract.
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"audio")

    # When: callers try to persist an arbitrary runtime fact or provider header.
    with pytest.raises(SidecarParseError):
        _sidecar(audio, environment={"hostname": "private-host"})
    with pytest.raises(SidecarParseError):
        _sidecar(audio, retry_headers={"x-request-id": "req-1"})
    with pytest.raises(SidecarParseError):
        _sidecar(audio, request_file="C:private.wav")

    # Then: the public builder rejects rather than silently filtering the values.


@pytest.mark.parametrize(
    "field,name",
    [
        ("audio", "C:private.wav"),
        ("audio", "CON.wav"),
        ("audio", "file://private.wav"),
        ("retained_directory", "final_chunks/../private"),
        ("retained_directory", r"final_chunks\\private"),
        ("file", "chunk/../private.wav"),
        ("file", r"chunk\\private.wav"),
        ("file", "NUL"),
    ],
)
def test_v2_parser_rejects_nonportable_persisted_names(
    tmp_path: Path, field: str, name: str
) -> None:
    # Given: a valid public v2 payload with a hostile persisted name.
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"audio")
    payload = json.loads(json.dumps(_sidecar(audio).to_payload()))
    match field:
        case "audio":
            payload["audio"]["basename"] = name
        case "retained_directory":
            payload["retained_directory"] = name
        case "file":
            payload["request_meta"][0]["file"] = name

    # When / Then: the public parser fails closed instead of treating paths as names.
    with pytest.raises(SidecarParseError):
        parse_sidecar_metadata(json.dumps(payload))


def test_retained_directory_resolution_is_relative_to_published_audio(tmp_path: Path) -> None:
    # Given: a retained v2 sidecar whose directory was created beside the final audio.
    audio = tmp_path / "nested" / "final.wav"
    audio.parent.mkdir()
    audio.write_bytes(b"audio")
    sidecar = _sidecar(audio, audio.parent / "final_chunks_123")

    # When: the public resolver maps the retained directory from the output location.
    resolved = resolve_retained_directory(sidecar, audio)

    # Then: no absolute path was persisted, but the original directory can be found.
    assert resolved == audio.parent / "final_chunks_123"
