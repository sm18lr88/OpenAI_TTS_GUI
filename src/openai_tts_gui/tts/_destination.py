from __future__ import annotations

import hashlib
import os
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from ..errors import DestinationObservationError


@dataclass(frozen=True, slots=True)
class ResourceIdentity:
    operational_path: Path
    normalized: str
    digest: str


@dataclass(frozen=True, slots=True)
class MissingResource:
    pass


@dataclass(frozen=True, slots=True)
class ExistingResource:
    st_dev: int
    st_ino: int
    st_size: int
    st_mtime_ns: int


type ResourceState = MissingResource | ExistingResource


@dataclass(frozen=True, slots=True)
class ResourceObservation:
    identity: ResourceIdentity
    state: ResourceState


@dataclass(frozen=True, slots=True)
class DestinationPaths:
    audio: ResourceIdentity
    sidecar: ResourceIdentity
    resources: tuple[ResourceIdentity, ...]


@dataclass(frozen=True, slots=True)
class DestinationObservation:
    resources: tuple[ResourceObservation, ...]


def destination_paths(output_path: str) -> DestinationPaths:
    audio = _identity(Path(output_path))
    sidecar = _identity(Path(f"{output_path}.json"))
    unique_resources = {resource.normalized: resource for resource in (audio, sidecar)}
    resources = tuple(
        sorted(unique_resources.values(), key=lambda item: (item.digest, item.normalized))
    )
    return DestinationPaths(audio, sidecar, resources)


def observe_destination(paths: DestinationPaths) -> DestinationObservation:
    return DestinationObservation(tuple(_observe(resource) for resource in paths.resources))


def _identity(raw_path: Path) -> ResourceIdentity:
    expanded = raw_path.expanduser()
    absolute = Path(os.path.abspath(expanded))
    operational = absolute.parent.resolve(strict=False) / absolute.name
    normalized = unicodedata.normalize("NFC", operational.as_posix())
    if sys.platform in {"win32", "darwin"}:
        normalized = normalized.casefold()
    normalized = unicodedata.normalize("NFC", normalized)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return ResourceIdentity(operational, normalized, digest)


def _observe(identity: ResourceIdentity) -> ResourceObservation:
    try:
        stat = os.lstat(identity.operational_path)
    except FileNotFoundError:
        return ResourceObservation(identity, MissingResource())
    except OSError as exc:
        raise DestinationObservationError(identity.normalized, str(exc)) from exc
    return ResourceObservation(
        identity,
        ExistingResource(stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns),
    )
