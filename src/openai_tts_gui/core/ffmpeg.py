import re
import subprocess

from ..config import settings


def get_ffmpeg_version() -> str:
    try:
        result = subprocess.run(
            [settings.FFMPEG_COMMAND, "-version"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.splitlines()[0].strip()
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
        result = subprocess.run(
            [settings.FFMPEG_COMMAND, "-version"],
            capture_output=True,
            text=True,
            check=True,
        )
        first = result.stdout.splitlines()[0].strip()
        ver = parse_ffmpeg_semver(first)
        if ver is None:
            low = first.lower()
            if "git" in low or "gyan.dev" in low or "full_build" in low:
                return True, first
            return True, first
        ok = tuple(ver) >= tuple(settings.FFMPEG_MIN_VERSION)
        if not ok:
            min_req = ".".join(map(str, settings.FFMPEG_MIN_VERSION))
            return (False, f"ffmpeg too old: found {first}, require >= {min_req}")
        return True, first
    except FileNotFoundError:
        return False, "ffmpeg not found in PATH. Please install ffmpeg."
    except subprocess.CalledProcessError as e:
        return False, f"ffmpeg invocation failed: {e}"
    except Exception as e:
        return False, f"ffmpeg check error: {e}"
