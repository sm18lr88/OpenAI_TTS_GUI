import hashlib
import json
import logging
import platform
import time

from .ffmpeg import get_ffmpeg_version

logger = logging.getLogger(__name__)


def write_sidecar_metadata(output_file: str, meta: dict):
    sidecar = output_file + ".json"
    meta = dict(meta or {})
    meta.setdefault("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    meta.setdefault("ffmpeg", get_ffmpeg_version())
    meta.setdefault("os", platform.platform())
    with open(sidecar, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    logger.info(f"Wrote sidecar metadata: {sidecar}")


def sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()
