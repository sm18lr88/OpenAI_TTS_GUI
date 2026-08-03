from __future__ import annotations

import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..errors import CleanupReport, TTSAPIError, TTSCancelledError, TTSChunkError, TTSError


@dataclass(frozen=True, slots=True)
class ChunkTask:
    index: int
    text: str
    filename: Path


@dataclass(frozen=True, slots=True)
class ChunkRequestMeta:
    chunk_index: int
    request_id: str | None
    model_header: str | None
    file: str
    attempts: int
    characters: int
    retry_headers: dict[str, str] | None = None


@dataclass(frozen=True, slots=True)
class PublicationPlan:
    output_path: Path
    temp_dir: Path
    temp_files: list[str]
    tasks: tuple[ChunkTask, ...]
    requested_parallelism: int
    worker_count: int
    retain_files: bool


def create_plan(
    output_path: str,
    chunks: list[str],
    response_format: str,
    requested_parallelism: int,
    retain_files: bool,
) -> PublicationPlan:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f"{destination.stem}_chunks_", dir=destination.parent))
    tasks = tuple(
        ChunkTask(index, chunk, temp_dir / f"chunk_{index:04d}.{response_format}")
        for index, chunk in enumerate(chunks, start=1)
    )
    return PublicationPlan(
        destination,
        temp_dir,
        [str(task.filename) for task in tasks],
        tasks,
        requested_parallelism,
        min(requested_parallelism, len(tasks)),
        retain_files,
    )


def cleanup_plan(
    plan: PublicationPlan, cleanup_files: Callable[[list[str]], CleanupReport | None]
) -> CleanupReport:
    if plan.retain_files:
        return CleanupReport()
    retained: list[str] = []
    warnings: list[str] = []
    for file_name in plan.temp_files:
        try:
            result = cleanup_files([file_name])
        except OSError as exc:
            retained.append(Path(file_name).name)
            warnings.append(f"Could not remove chunk file {Path(file_name).name}: {exc}")
            continue
        if result is not None:
            retained.extend(result.retained_basenames)
            warnings.extend(result.warnings)
    for path in (plan.temp_dir,):
        try:
            path.rmdir()
        except FileNotFoundError:
            continue
        except OSError as exc:
            retained.append(path.name)
            warnings.append(f"Could not remove chunk directory {path.name}: {exc}")
    return CleanupReport(tuple(sorted(set(retained))), tuple(sorted(set(warnings))))


def with_retained_dir(error: TTSError, temp_dir: Path) -> TTSError:
    message = f"{error}\nThe app kept partial chunk files in:\n{temp_dir}"
    if isinstance(error, TTSAPIError):
        return TTSAPIError(message, status_code=error.status_code, request_id=error.request_id)
    if isinstance(error, TTSChunkError):
        return TTSChunkError(message, chunk_index=error.chunk_index, file_path=error.file_path)
    if isinstance(error, TTSCancelledError):
        return TTSCancelledError(message)
    return type(error)(message)


def retained_failure_message(message: str, plan: PublicationPlan | None) -> str:
    if plan is not None and plan.retain_files:
        return f"{message}\nThe app kept partial chunk files in:\n{plan.temp_dir}"
    return message
