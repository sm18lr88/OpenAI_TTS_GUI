from __future__ import annotations

import os
import tempfile
from pathlib import Path

from ..errors import (
    CleanupReport,
    FFmpegError,
    PublicationError,
    PublicationRecoveryError,
    TTSCancelledError,
    TTSChunkError,
)
from ._destination import DestinationObservation, DestinationPaths, ExistingResource
from ._outcomes import PublicationInProgress
from ._publication_cleanup import cleanup_stage, retained
from ._publication_plan import (
    ChunkRequestMeta,
    ChunkTask,
    PublicationPlan,
    with_retained_dir,
)
from ._publication_staging import build_sidecar, verify_audio, verify_sidecar
from ._publication_types import (
    CanonicalState,
    FinalizationReport,
    PublicationCommit,
    PublicationDependencies,
    PublicationFailureReason,
    PublicationPayload,
)

__all__ = ["ChunkRequestMeta", "ChunkTask", "PublicationPlan", "with_retained_dir"]


def publish(
    payload: PublicationPayload,
    dependencies: PublicationDependencies,
    paths: DestinationPaths,
    observation: DestinationObservation,
) -> PublicationCommit:
    has_old_sidecar = _has_old_sidecar(observation, paths)
    original_state = _original_state(has_old_sidecar)
    try:
        stage_dir = _stage_directory(paths.audio.operational_path)
    except OSError as exc:
        raise PublicationError(
            PublicationFailureReason.PREPARE_STAGE,
            str(exc),
            FinalizationReport(original_state),
        ) from exc
    stage_audio = stage_dir / paths.audio.operational_path.name
    stage_sidecar = stage_dir / paths.sidecar.operational_path.name
    backup = stage_dir / "previous-sidecar.json"
    try:
        dependencies.concatenate(payload.plan.temp_files, str(stage_audio))
    except (FFmpegError, TTSChunkError) as exc:
        _attach_stage_cleanup(
            exc, cleanup_stage(stage_dir, stage_audio, stage_sidecar, backup), original_state
        )
        raise
    except (OSError, PublicationError) as exc:
        raise _failed_publication(
            PublicationFailureReason.STAGE_AUDIO,
            exc,
            stage_dir,
            original_state,
            stage_audio,
            stage_sidecar,
            backup,
        ) from exc
    try:
        verify_audio(stage_audio)
    except PublicationError as exc:
        raise _failed_publication(
            PublicationFailureReason.VALIDATE_AUDIO,
            exc,
            stage_dir,
            original_state,
            stage_audio,
            stage_sidecar,
            backup,
        ) from exc
    try:
        sidecar = build_sidecar(payload, stage_audio)
        dependencies.write_sidecar(str(stage_audio), sidecar)
    except (FFmpegError, TTSChunkError) as exc:
        _attach_stage_cleanup(
            exc, cleanup_stage(stage_dir, stage_audio, stage_sidecar, backup), original_state
        )
        raise
    except (OSError, PublicationError) as exc:
        raise _failed_publication(
            PublicationFailureReason.STAGE_SIDECAR,
            exc,
            stage_dir,
            original_state,
            stage_audio,
            stage_sidecar,
            backup,
        ) from exc
    try:
        verify_sidecar(stage_sidecar, stage_audio)
    except PublicationError as exc:
        raise _failed_publication(
            PublicationFailureReason.VALIDATE_SIDECAR,
            exc,
            stage_dir,
            original_state,
            stage_audio,
            stage_sidecar,
            backup,
        ) from exc
    decision = payload.begin_publication()
    if not isinstance(decision, PublicationInProgress):
        cleanup = cleanup_stage(stage_dir, stage_audio, stage_sidecar, backup)
        raise TTSCancelledError(
            "TTS generation cancelled.",
            finalization=FinalizationReport(original_state).with_cleanup(cleanup),
        )
    payload.on_publication_started()
    if has_old_sidecar:
        try:
            os.replace(paths.sidecar.operational_path, backup)
        except OSError as exc:
            raise _failed_publication(
                PublicationFailureReason.BACKUP_SIDECAR,
                exc,
                stage_dir,
                original_state,
                stage_audio,
                stage_sidecar,
                backup,
            ) from exc
    try:
        os.replace(stage_audio, paths.audio.operational_path)
    except OSError as exc:
        return _recover_audio_replace(
            exc, paths, backup, stage_dir, has_old_sidecar, original_state
        )
    try:
        os.replace(stage_sidecar, paths.sidecar.operational_path)
    except OSError as exc:
        retained_paths = retained(stage_dir, backup, stage_sidecar)
        raise PublicationError(
            PublicationFailureReason.REPLACE_SIDECAR,
            f"{exc}; retained={retained_paths}",
            FinalizationReport(CanonicalState.NEW_AUDIO_WITHOUT_SIDECAR, retained_paths),
        ) from exc
    cleanup = cleanup_stage(stage_dir, stage_audio, stage_sidecar, backup)
    return PublicationCommit(
        f"TTS audio saved successfully to:\n{paths.audio.operational_path}",
        FinalizationReport(
            CanonicalState.VERIFIED_NEW_PAIR,
            cleanup.retained_basenames,
            cleanup.warnings,
        ),
    )


def _stage_directory(audio_path: Path) -> Path:
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=f".{audio_path.stem}.publication-", dir=audio_path.parent))


def _has_old_sidecar(observation: DestinationObservation, paths: DestinationPaths) -> bool:
    return any(
        item.identity == paths.sidecar and isinstance(item.state, ExistingResource)
        for item in observation.resources
    )


def _original_state(has_old_sidecar: bool) -> CanonicalState:
    return (
        CanonicalState.ORIGINAL_DESTINATION
        if has_old_sidecar
        else CanonicalState.ORIGINAL_AUDIO_WITHOUT_SIDECAR
    )


def _recover_audio_replace(
    error: OSError,
    paths: DestinationPaths,
    backup: Path,
    stage_dir: Path,
    has_old_sidecar: bool,
    original_state: CanonicalState,
) -> PublicationCommit:
    if has_old_sidecar:
        try:
            os.replace(backup, paths.sidecar.operational_path)
        except OSError as restore_error:
            retained_paths = retained(stage_dir, backup)
            raise PublicationRecoveryError(
                PublicationFailureReason.RESTORE_SIDECAR,
                f"{restore_error}; retained={retained_paths}",
                FinalizationReport(CanonicalState.ORIGINAL_AUDIO_WITHOUT_SIDECAR, retained_paths),
            ) from restore_error
    cleanup = cleanup_stage(stage_dir, backup)
    raise PublicationError(
        PublicationFailureReason.REPLACE_AUDIO,
        f"{error}; retained={cleanup.retained_basenames}",
        FinalizationReport(original_state, cleanup.retained_basenames, cleanup.warnings),
    )


def _failed_publication(
    reason: PublicationFailureReason,
    error: OSError | PublicationError,
    stage_dir: Path,
    original_state: CanonicalState,
    *tracked_paths: Path,
) -> PublicationError:
    cleanup = cleanup_stage(stage_dir, *tracked_paths)
    return PublicationError(
        reason,
        f"{error}; retained={cleanup.retained_basenames}",
        FinalizationReport(original_state, cleanup.retained_basenames, cleanup.warnings),
    )


def _attach_stage_cleanup(
    error: FFmpegError | TTSChunkError,
    cleanup: CleanupReport,
    original_state: CanonicalState,
) -> None:
    finalization = error.finalization or FinalizationReport(original_state)
    error.finalization = finalization.with_cleanup(cleanup)
