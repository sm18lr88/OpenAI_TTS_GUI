from __future__ import annotations

import os
from contextlib import suppress
from pathlib import Path

from ..errors import CleanupReport
from ._destination import DestinationPaths, ResourceIdentity


class DestinationLease:
    """Owns acquired native file descriptors until release."""

    def __init__(self, root: Path, resources: tuple[ResourceIdentity, ...]) -> None:
        self.root = root
        self.resources = resources
        self._descriptors: list[tuple[int, Path]] = []

    def release(self) -> CleanupReport:
        warnings: list[str] = []
        for descriptor, path in reversed(self._descriptors):
            try:
                _unlock(descriptor)
            except OSError as exc:
                warnings.append(f"lease unlock failed for {path.name}: {exc}")
            try:
                os.close(descriptor)
            except OSError as exc:
                warnings.append(f"lease close failed for {path.name}: {exc}")
        self._descriptors.clear()
        return CleanupReport((), tuple(sorted(set(warnings))))


def acquire_lease(paths: DestinationPaths, lock_root: Path) -> DestinationLease | None:
    try:
        resolved_root = lock_root.expanduser().resolve(strict=False)
        resolved_root.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    lease = DestinationLease(resolved_root, paths.resources)
    for resource in paths.resources:
        lock_path = resolved_root / f"publication-{resource.digest}.lock"
        descriptor = _try_lock(lock_path)
        if descriptor is None:
            lease.release()
            return None
        lease._descriptors.append((descriptor, lock_path))
    return lease


def _try_lock(path: Path) -> int | None:
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags, 0o600)
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"\0")
        os.lseek(descriptor, 0, os.SEEK_SET)
        _lock(descriptor)
    except OSError:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)
        return None
    return descriptor


def _lock(descriptor: int) -> None:
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        return
    import fcntl

    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(descriptor: int) -> None:
    if os.name == "nt":
        import msvcrt

        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(descriptor, fcntl.LOCK_UN)
