from __future__ import annotations

import re
import subprocess
from functools import lru_cache

from ..config import settings
from ..errors import FFmpegError, FFmpegNotFoundError


@lru_cache(maxsize=1)
def _run_ffmpeg_version() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [settings.FFMPEG_COMMAND, "-version"],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )


def _first_version_line(result: subprocess.CompletedProcess[str]) -> str:
    output = result.stdout or result.stderr or ""
    first = output.splitlines()[0].strip() if output else ""
    return first or "unknown"


def get_ffmpeg_version() -> str:
    try:
        return _first_version_line(_run_ffmpeg_version())
    except Exception:
        return "unknown"


def parse_ffmpeg_semver(line: str) -> tuple[int, int, int] | None:
    m = re.search(r"version\s+(?:n)?(\d+)\.(\d+)(?:\.(\d+))?", line)
    if m:
        major, minor, patch = m.group(1), m.group(2), m.group(3) or "0"
        return int(major), int(minor), int(patch)

    m2 = re.search(r"version\s+(\d{4})-(\d{2})-(\d{2})-git", line)
    if m2:
        year, month, day = m2.group(1), m2.group(2), m2.group(3)
        return int(year), int(month), int(day)

    return None


def preflight_check() -> tuple[bool, str]:
    try:
        result = _run_ffmpeg_version()
        first = _first_version_line(result)
        ver = parse_ffmpeg_semver(first)
        if ver is None:
            return True, first
        ok = ver >= tuple(settings.FFMPEG_MIN_VERSION)
        if not ok:
            min_req = ".".join(map(str, settings.FFMPEG_MIN_VERSION))
            return False, f"ffmpeg too old: found {first}, require >= {min_req}"
        return True, first
    except FileNotFoundError:
        return False, "ffmpeg not found in PATH. Please install ffmpeg."
    except subprocess.CalledProcessError as exc:
        return False, f"ffmpeg invocation failed: {exc}"
    except Exception as exc:
        return False, f"ffmpeg check error: {exc}"


def require_preflight() -> str:
    ok, detail = preflight_check()
    if ok:
        return detail
    if "not found" in detail.lower():
        raise FFmpegNotFoundError(detail)
    raise FFmpegError(detail)
