from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path

from .ffmpeg import get_ffmpeg_version
from .sidecar import SidecarV2

logger = logging.getLogger(__name__)


type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
type MetadataValue = JsonValue | Path
type MetadataInput = Mapping[str, MetadataValue] | SidecarV2


def write_sidecar_metadata(output_file: str, meta: MetadataInput) -> str:
    sidecar_path = Path(f"{output_file}.json")
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)

    match meta:
        case SidecarV2() as v2:
            payload = v2.to_payload()
        case Mapping() as legacy:
            payload = dict(legacy)
            payload.setdefault("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
            payload.setdefault("ffmpeg", get_ffmpeg_version())
            payload.setdefault("os", platform.platform())

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=sidecar_path.stem + ".",
            suffix=".tmp",
            dir=sidecar_path.parent,
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(payload, handle, indent=2, sort_keys=True, default=str)
            handle.write("\n")
        os.replace(temp_path, sidecar_path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)

    logger.info("Wrote sidecar metadata to %s", sidecar_path)
    return str(sidecar_path)


def sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()
