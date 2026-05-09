from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from ..config import settings
from ..errors import FFmpegError, FFmpegNotFoundError


def _windows_registry_path() -> str:
    if sys.platform != "win32":
        return ""
    try:
        import winreg
    except ImportError:
        return ""

    path_parts: list[str] = []
    keys = [
        (winreg.HKEY_CURRENT_USER, r"Environment"),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        ),
    ]
    for root, key_name in keys:
        try:
            with winreg.OpenKey(root, key_name) as key:
                value, _value_type = winreg.QueryValueEx(key, "Path")
        except OSError:
            continue
        path_parts.append(os.path.expandvars(str(value)))
    return os.pathsep.join(path_parts)


def _packaged_search_dirs() -> list[Path]:
    dirs: list[Path] = []
    if getattr(sys, "frozen", False):
        dirs.append(Path(sys.executable).resolve().parent)
        bundle_dir = getattr(sys, "_MEIPASS", "")
        if bundle_dir:
            dirs.append(Path(bundle_dir).resolve())
    return dirs


def _common_windows_ffmpeg_dirs() -> list[Path]:
    if sys.platform != "win32":
        return []

    home = Path.home()
    local_appdata = os.getenv("LOCALAPPDATA")
    program_files = os.getenv("PROGRAMFILES", r"C:\Program Files")
    program_files_x86 = os.getenv("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    program_data = os.getenv("PROGRAMDATA", r"C:\ProgramData")

    candidates = [
        Path(r"C:\ffmpeg\bin"),
        Path(program_files) / "ffmpeg" / "bin",
        Path(program_files_x86) / "ffmpeg" / "bin",
        Path(program_data) / "chocolatey" / "bin",
        home / "scoop" / "shims",
    ]
    if local_appdata:
        candidates.append(Path(local_appdata) / "Microsoft" / "WinGet" / "Links")
    return candidates


@lru_cache(maxsize=1)
def resolve_ffmpeg_command() -> str:
    configured = settings.FFMPEG_COMMAND
    configured_path = Path(configured)
    if configured_path.is_absolute() and configured_path.exists():
        return str(configured_path)

    live_path = os.environ.get("PATH", "")
    registry_path = _windows_registry_path()
    search_path = os.pathsep.join(part for part in (live_path, registry_path) if part)
    resolved = shutil.which(configured, path=search_path or None)
    if resolved:
        return resolved

    executable_name = configured if configured.lower().endswith(".exe") else f"{configured}.exe"
    for directory in [*_packaged_search_dirs(), *_common_windows_ffmpeg_dirs()]:
        candidate = directory / executable_name
        if candidate.exists():
            return str(candidate)

    return configured


@lru_cache(maxsize=1)
def _run_ffmpeg_version() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [resolve_ffmpeg_command(), "-version"],
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
        return False, "ffmpeg not found. Please install ffmpeg or add it to PATH."
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
