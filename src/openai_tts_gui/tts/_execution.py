from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from .. import config
from ..core import own_ffmpeg_process
from ..errors import (
    CleanupReport,
    DestinationChangedError,
    DestinationObservationError,
    FFmpegError,
    FFmpegNotFoundError,
    OutputBusyError,
    PublicationError,
    PublicationRecoveryError,
    TTSAPIError,
    TTSCancelledError,
    TTSChunkError,
    TTSError,
)
from . import _publication, _scheduler
from ._contracts import (
    CancellationStage,
    CancelledOutcome,
    CancelRequested,
    ChunkFailureOutcome,
    DestinationChangedOutcome,
    FfmpegFailureOutcome,
    FfmpegNotFoundOutcome,
    FfmpegStarted,
    GenerationHooks,
    GenerationOutcome,
    GenerationRequest,
    OutputBusyOutcome,
    ProviderFailureOutcome,
    PublicationFailureOutcome,
    PublicationRecoveryFailureOutcome,
    PublicationStarted,
    RunStarted,
    SuccessOutcome,
    UnknownFailureOutcome,
)
from ._destination import destination_paths, observe_destination
from ._execution_helpers import accept as _accept
from ._execution_helpers import emit as _emit
from ._execution_helpers import raise_if_cancelled as _raise_if_cancelled
from ._execution_types import ExecutionDependencies
from ._lease import DestinationLease, acquire_lease
from ._publication_cleanup import with_terminal_cleanup
from ._publication_plan import PublicationPlan, cleanup_plan, create_plan, retained_failure_message
from ._publication_types import (
    CanonicalState,
    PublicationDependencies,
    PublicationPayload,
    PublicationRequest,
)
from ._run_state import FfmpegStopper, RunState

if TYPE_CHECKING:
    from ._service import TTSService


def run(
    service: TTSService,
    request: GenerationRequest,
    hooks: GenerationHooks,
    dependencies: ExecutionDependencies,
) -> GenerationOutcome:
    plan: PublicationPlan | None = None
    lease: DestinationLease | None = None
    cleanup = CleanupReport()
    release = CleanupReport()
    canonical_state = CanonicalState.ORIGINAL_AUDIO_WITHOUT_SIDECAR
    state = RunState(0, hooks.cancel_event)
    service._activate_run(state)
    try:
        _raise_if_cancelled(state)
        dependencies.preflight()
        chunks = dependencies.split_text(request.text, config.settings.MAX_CHUNK_SIZE)
        if not chunks:
            raise TTSChunkError("Text splitting produced no chunks.")
        state.bind_plan(len(chunks))
        _emit(hooks, RunStarted(len(chunks)))
        paths = destination_paths(request.output_path)
        try:
            expected = request.destination_observation or observe_destination(paths)
        except DestinationObservationError as exc:
            raise DestinationChangedError(request.output_path, str(exc)) from exc
        lease = acquire_lease(paths, Path(config.settings.DATA_DIR) / "publication-locks")
        if lease is None:
            raise OutputBusyError(request.output_path)
        try:
            current = observe_destination(paths)
        except DestinationObservationError as exc:
            raise DestinationChangedError(request.output_path, str(exc)) from exc
        if current != expected:
            raise DestinationChangedError(request.output_path, "observation changed")
        if _publication._has_old_sidecar(current, paths):
            canonical_state = CanonicalState.ORIGINAL_DESTINATION
        plan = create_plan(
            request.output_path,
            chunks,
            request.config.response_format,
            max(1, min(8, request.config.parallelism or config.settings.PARALLELISM)),
            request.config.retain_files,
        )
        metadata = _generate(service, request, hooks, state, plan)
        _raise_if_cancelled(state)

        def concatenate(files: list[str], destination: str) -> str | None:
            def attach_ffmpeg(stopper: FfmpegStopper) -> bool:
                accepted = state.begin_ffmpeg(stopper)
                if accepted:
                    _emit(hooks, FfmpegStarted())
                return accepted

            try:
                with own_ffmpeg_process(attach_ffmpeg):
                    return dependencies.concatenate(files, destination)
            finally:
                state.finish_ffmpeg()

        try:
            commit = _publication.publish(
                PublicationPayload(
                    plan,
                    PublicationRequest(
                        request.text,
                        request.config.model,
                        request.config.voice,
                        request.config.response_format,
                        request.config.speed,
                        request.config.instructions,
                    ),
                    metadata,
                    state.begin_publication,
                    lambda: _emit(hooks, PublicationStarted()),
                ),
                PublicationDependencies(concatenate, dependencies.write_sidecar),
                paths,
                current,
            )
        finally:
            state.finish_publication()
        message = commit.message
        if plan.retain_files:
            message += f"\nKept chunk files in:\n{plan.temp_dir}"
        outcome: GenerationOutcome = SuccessOutcome(
            message, request.output_path, state.freeze(), commit.finalization
        )
    except TTSCancelledError as exc:
        stage = state.request_cancel()
        if isinstance(stage, CancellationStage):
            _emit(hooks, CancelRequested(stage))
        outcome = CancelledOutcome(str(exc), state.freeze(), exc.finalization)
    except PublicationRecoveryError as exc:
        outcome = PublicationRecoveryFailureOutcome(
            str(exc), exc.reason, exc.finalization, state.freeze()
        )
    except PublicationError as exc:
        outcome = PublicationFailureOutcome(
            str(exc),
            exc.reason,
            exc.finalization,
            state.freeze(),
        )
    except TTSAPIError as exc:
        outcome = ProviderFailureOutcome(
            retained_failure_message(str(exc), plan),
            state.freeze(),
            exc.status_code,
            exc.request_id,
        )
    except TTSChunkError as exc:
        outcome = ChunkFailureOutcome(
            retained_failure_message(str(exc), plan),
            exc.chunk_index,
            state.freeze(),
            exc.file_path,
            exc.finalization,
        )
    except FFmpegNotFoundError as exc:
        outcome = FfmpegNotFoundOutcome(str(exc), state.freeze(), exc.finalization)
    except FFmpegError as exc:
        outcome = FfmpegFailureOutcome(str(exc), state.freeze(), exc.finalization)
    except OutputBusyError as exc:
        outcome = OutputBusyOutcome(exc.output_path, state.freeze())
    except DestinationChangedError as exc:
        outcome = DestinationChangedOutcome(exc.output_path, exc.reason, state.freeze())
    except TTSError as exc:
        outcome = UnknownFailureOutcome(str(exc), state.freeze())
    finally:
        if plan is not None:
            cleanup = cleanup_plan(plan, dependencies.cleanup)
        if lease is not None:
            release = lease.release()
        service._deactivate_run(state)
    finalization = with_terminal_cleanup(
        outcome.finalization,
        cleanup.merged(release).merged(CleanupReport(warnings=state.cleanup_warnings)),
        canonical_state,
    )
    return replace(outcome, finalization=finalization)


def _generate(
    service: TTSService,
    request: GenerationRequest,
    hooks: GenerationHooks,
    state: RunState,
    plan: PublicationPlan,
) -> list[_publication.ChunkRequestMeta]:
    metadata: dict[int, _publication.ChunkRequestMeta] = {}
    abort_event = threading.Event()
    batch = _scheduler.ScheduledBatch(
        tasks=plan.tasks,
        metadata=metadata,
        expected_indexes={task.index for task in plan.tasks},
        metadata_lock=threading.Lock(),
        on_progress=None,
        on_status=hooks.on_status,
        on_parallelism=hooks.on_parallelism,
        cancel_event=_scheduler.CombinedCancelEvent(state.cancel_event, abort_event),
        on_accepted=lambda item: _accept(state, hooks, item),
        state=state,
    )
    coordinator: _scheduler.RunCoordinator | None = None

    def runner(task: _publication.ChunkTask) -> _publication.ChunkRequestMeta:
        return service._generate_chunk_with_retries(
            task=task,
            config=request.config,
            on_status=hooks.on_status,
            on_parallelism=hooks.on_parallelism,
            on_progress=hooks.on_progress,
            cancel_event=batch.cancel_event,
            coordinator=coordinator,
            state=state,
        )

    if len(plan.tasks) > 1 and plan.requested_parallelism > 1:
        coordinator = _scheduler.RunCoordinator(plan.worker_count)
        service._last_run_coordinator = coordinator
        if hooks.on_status is not None:
            hooks.on_status(
                f"Generating {len(plan.tasks)} chunks with parallelism {plan.requested_parallelism}"
            )
        if hooks.on_parallelism is not None:
            hooks.on_parallelism(0, plan.worker_count)
        _scheduler.generate_parallel(batch, runner, coordinator, abort_event)
    else:
        service._last_run_coordinator = None
        if hooks.on_parallelism is not None:
            hooks.on_parallelism(0, 1)
        _scheduler.generate_serial(batch, runner)
    return _scheduler.ordered_metadata(plan.tasks, metadata)
