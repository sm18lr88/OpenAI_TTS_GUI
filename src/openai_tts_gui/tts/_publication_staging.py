from __future__ import annotations

from pathlib import Path

from ..config import MAX_CHUNK_SIZE, STREAM_FORMAT, env_snapshot
from ..core import (
    SidecarRequestInput,
    SidecarWriteInput,
    build_sidecar_v2,
    parse_sidecar_metadata,
    verify_sidecar_audio,
)
from ..errors import PublicationError, ValidationError
from ._publication_types import (
    CanonicalState,
    FinalizationReport,
    PublicationFailureReason,
    PublicationPayload,
)


def build_sidecar(payload: PublicationPayload, audio_path: Path):
    request = payload.request
    plan = payload.plan
    return build_sidecar_v2(
        SidecarWriteInput(
            audio_path=audio_path,
            model=request.model,
            voice=request.voice,
            response_format=request.response_format,
            speed=request.speed,
            chunk_count=len(plan.tasks),
            chunk_size=MAX_CHUNK_SIZE,
            parallelism_requested=plan.requested_parallelism,
            parallelism_used=plan.worker_count,
            stream_format=STREAM_FORMAT,
            retain_files=plan.retain_files,
            input_chars=len(request.text),
            environment=env_snapshot(),
            retained_directory=plan.temp_dir if plan.retain_files else None,
            request_meta=tuple(
                SidecarRequestInput(
                    chunk_index=item.chunk_index,
                    request_id=item.request_id,
                    model_header=item.model_header,
                    file=item.file,
                    attempts=item.attempts,
                    characters=item.characters,
                    retry_headers=item.retry_headers,
                )
                for item in payload.metadata
            ),
        )
    )


def verify_audio(path: Path) -> None:
    try:
        stat = path.stat()
    except OSError as exc:
        raise PublicationError(
            PublicationFailureReason.VALIDATE_AUDIO,
            str(exc),
            FinalizationReport(CanonicalState.ORIGINAL_DESTINATION),
        ) from exc
    if not path.is_file() or stat.st_size == 0:
        raise PublicationError(
            PublicationFailureReason.VALIDATE_AUDIO,
            "empty staged audio",
            FinalizationReport(CanonicalState.ORIGINAL_DESTINATION),
        )


def verify_sidecar(sidecar_path: Path, audio_path: Path) -> None:
    try:
        parsed = parse_sidecar_metadata(sidecar_path)
        verification = verify_sidecar_audio(parsed, audio_path)
    except (OSError, ValidationError) as exc:
        raise PublicationError(
            PublicationFailureReason.VALIDATE_SIDECAR,
            str(exc),
            FinalizationReport(CanonicalState.ORIGINAL_DESTINATION),
        ) from exc
    if verification.status != "verified":
        raise PublicationError(
            PublicationFailureReason.VALIDATE_SIDECAR,
            verification.status,
            FinalizationReport(CanonicalState.ORIGINAL_DESTINATION),
        )
