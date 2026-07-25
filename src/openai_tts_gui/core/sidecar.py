from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict

from . import sidecar_validation
from .sidecar_validation import SidecarParseError

type ParsedSidecar = SidecarV1 | SidecarV2
type AudioVerification = AudioVerified | MissingAudio | AudioMismatch

_basename = sidecar_validation.basename
_safe_environment = sidecar_validation.safe_environment
_safe_retry_headers = sidecar_validation.safe_retry_headers


@dataclass(frozen=True, slots=True)
class UnsupportedSidecarSchemaError(SidecarParseError):
    schema_version: int

    def __init__(self, schema_version: int) -> None:
        super().__init__("unsupported schema version")
        object.__setattr__(self, "schema_version", schema_version)


@dataclass(frozen=True, slots=True)
class AudioIdentity:
    basename: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class SidecarSettings:
    model: str
    voice: str
    response_format: str
    speed: float
    chunk_count: int
    chunk_size: int
    parallelism_requested: int
    parallelism_used: int
    stream_format: str
    retain_files: bool
    input_chars: int


@dataclass(frozen=True, slots=True)
class SidecarRequestInput:
    chunk_index: int
    request_id: str | None
    model_header: str | None
    file: Path | str
    attempts: int
    characters: int
    retry_headers: Mapping[str, str] | None


@dataclass(frozen=True, slots=True)
class SidecarRequestMeta:
    chunk_index: int
    request_id: str | None
    model_header: str | None
    file: str
    attempts: int
    characters: int
    retry_headers: tuple[tuple[str, str], ...] | None


@dataclass(frozen=True, slots=True)
class SidecarWriteInput:
    audio_path: Path
    model: str
    voice: str
    response_format: str
    speed: float
    chunk_count: int
    chunk_size: int
    parallelism_requested: int
    parallelism_used: int
    stream_format: str
    retain_files: bool
    input_chars: int
    environment: Mapping[str, str]
    retained_directory: Path | None
    request_meta: tuple[SidecarRequestInput, ...]


@dataclass(frozen=True, slots=True)
class SidecarV1:
    request_ids: tuple[str, ...]
    parallelism_used: int | None
    schema_version: Literal[1] = 1


@dataclass(frozen=True, slots=True)
class SidecarV2:
    audio: AudioIdentity
    settings: SidecarSettings
    environment: tuple[tuple[str, str], ...]
    retained_directory: str | None
    request_meta: tuple[SidecarRequestMeta, ...]
    schema_version: Literal[2] = 2

    @property
    def request_ids(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(item.request_id for item in self.request_meta if item.request_id)
        )

    @property
    def parallelism_used(self) -> int:
        return self.settings.parallelism_used

    def to_payload(self) -> SidecarV2Payload:
        return {
            "schema_version": self.schema_version,
            "audio": {
                "basename": self.audio.basename,
                "size_bytes": self.audio.size_bytes,
                "sha256": self.audio.sha256,
            },
            "settings": {
                "model": self.settings.model,
                "voice": self.settings.voice,
                "response_format": self.settings.response_format,
                "speed": self.settings.speed,
                "chunk_count": self.settings.chunk_count,
                "chunk_size": self.settings.chunk_size,
                "parallelism_requested": self.settings.parallelism_requested,
                "parallelism_used": self.settings.parallelism_used,
                "stream_format": self.settings.stream_format,
                "retain_files": self.settings.retain_files,
                "input_chars": self.settings.input_chars,
            },
            "environment": dict(self.environment),
            "retained_directory": self.retained_directory,
            "request_meta": [_request_payload(item) for item in self.request_meta],
        }


@dataclass(frozen=True, slots=True)
class AudioVerified:
    identity: AudioIdentity
    status: Literal["verified"] = "verified"


@dataclass(frozen=True, slots=True)
class MissingAudio:
    expected_basename: str
    status: Literal["missing_audio"] = "missing_audio"


@dataclass(frozen=True, slots=True)
class AudioMismatch:
    expected: AudioIdentity
    actual: AudioIdentity
    status: Literal["mismatch"] = "mismatch"


class AudioPayload(TypedDict):
    basename: str
    size_bytes: int
    sha256: str


class SettingsPayload(TypedDict):
    model: str
    voice: str
    response_format: str
    speed: float
    chunk_count: int
    chunk_size: int
    parallelism_requested: int
    parallelism_used: int
    stream_format: str
    retain_files: bool
    input_chars: int


class RequestPayload(TypedDict):
    chunk_index: int
    request_id: str | None
    model_header: str | None
    file: str
    attempts: int
    characters: int
    retry_headers: dict[str, str] | None


class SidecarV2Payload(TypedDict):
    schema_version: Literal[2]
    audio: AudioPayload
    settings: SettingsPayload
    environment: dict[str, str]
    retained_directory: str | None
    request_meta: list[RequestPayload]


def build_sidecar_v2(input: SidecarWriteInput) -> SidecarV2:
    audio = _identity(input.audio_path)
    retained_directory = (
        _basename(input.retained_directory) if input.retained_directory is not None else None
    )
    return SidecarV2(
        audio=audio,
        settings=SidecarSettings(
            input.model,
            input.voice,
            input.response_format,
            input.speed,
            input.chunk_count,
            input.chunk_size,
            input.parallelism_requested,
            input.parallelism_used,
            input.stream_format,
            input.retain_files,
            input.input_chars,
        ),
        environment=_safe_environment(input.environment),
        retained_directory=retained_directory,
        request_meta=tuple(_request_meta(item) for item in input.request_meta),
    )


def resolve_retained_directory(sidecar: SidecarV2, audio_path: Path) -> Path | None:
    return audio_path.parent / sidecar.retained_directory if sidecar.retained_directory else None


def verify_sidecar_audio(sidecar: SidecarV2, audio_path: Path) -> AudioVerification:
    if not audio_path.exists():
        return MissingAudio(sidecar.audio.basename)
    actual = _identity(audio_path)
    if actual == sidecar.audio:
        return AudioVerified(sidecar.audio)
    return AudioMismatch(sidecar.audio, actual)


def _request_meta(item: SidecarRequestInput) -> SidecarRequestMeta:
    return SidecarRequestMeta(
        item.chunk_index,
        item.request_id,
        item.model_header,
        _basename(item.file),
        item.attempts,
        item.characters,
        _safe_retry_headers(item.retry_headers),
    )


def _request_payload(item: SidecarRequestMeta) -> RequestPayload:
    return {
        "chunk_index": item.chunk_index,
        "request_id": item.request_id,
        "model_header": item.model_header,
        "file": item.file,
        "attempts": item.attempts,
        "characters": item.characters,
        "retry_headers": dict(item.retry_headers) if item.retry_headers is not None else None,
    }


def _identity(path: Path) -> AudioIdentity:
    return AudioIdentity(_basename(path), path.stat().st_size, _sha256_file(path))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()
