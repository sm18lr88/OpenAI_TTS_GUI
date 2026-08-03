from __future__ import annotations

from pathlib import Path

from ..errors import CanonicalState, CleanupReport, FinalizationReport


def cleanup_stage(stage_dir: Path, *tracked_paths: Path) -> CleanupReport:
    retained: list[str] = []
    warnings: list[str] = []
    for path in tracked_paths:
        if not path.exists():
            continue
        try:
            path.unlink()
        except OSError as exc:
            retained.append(path.name)
            warnings.append(f"Could not clean up the stage path {path.name}: {exc}")
    try:
        stage_dir.rmdir()
    except FileNotFoundError:
        return CleanupReport(tuple(sorted(set(retained))), tuple(sorted(set(warnings))))
    except OSError as exc:
        retained.append(stage_dir.name)
        warnings.append(f"Could not clean up the stage path {stage_dir.name}: {exc}")
    return CleanupReport(tuple(sorted(set(retained))), tuple(sorted(set(warnings))))


def retained(stage_dir: Path, *paths: Path) -> tuple[str, ...]:
    names = {stage_dir.name}
    names.update(path.name for path in paths if path.exists())
    return tuple(sorted(names))


def with_terminal_cleanup(
    finalization: FinalizationReport | None, cleanup: CleanupReport, canonical_state: CanonicalState
) -> FinalizationReport | None:
    if not cleanup.retained_basenames and not cleanup.warnings:
        return finalization
    return (finalization or FinalizationReport(canonical_state)).with_cleanup(cleanup)
