from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace, TracebackType

import pytest

from openai_tts_gui.core import ffmpeg
from openai_tts_gui.errors import FFmpegError, FFmpegNotFoundError


@pytest.fixture(autouse=True)
def clear_ffmpeg_caches() -> Iterator[None]:
    ffmpeg.resolve_ffmpeg_command.cache_clear()
    ffmpeg._run_ffmpeg_version.cache_clear()
    yield
    ffmpeg.resolve_ffmpeg_command.cache_clear()
    ffmpeg._run_ffmpeg_version.cache_clear()


def test_windows_registry_path_skips_failed_key_and_expands_valid_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Key:
        def __enter__(self) -> Key:
            return self

        def __exit__(
            self,
            _exception_type: type[BaseException] | None,
            _exception: BaseException | None,
            _traceback: TracebackType | None,
        ) -> None:
            return None

    def open_key(root: str, _name: str) -> Key:
        if root == "user":
            raise OSError("unavailable")
        return Key()

    registry = SimpleNamespace(
        HKEY_CURRENT_USER="user",
        HKEY_LOCAL_MACHINE="machine",
        OpenKey=open_key,
        QueryValueEx=lambda _key, _name: ("%FFMPEG_TEST_DIR%", 1),
    )
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("FFMPEG_TEST_DIR", r"C:\tools")
    monkeypatch.setitem(sys.modules, "winreg", registry)

    assert ffmpeg._windows_registry_path() == r"C:\tools"


def test_windows_registry_path_returns_empty_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    assert ffmpeg._windows_registry_path() == ""


def test_windows_registry_path_handles_missing_winreg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "winreg", None)

    assert ffmpeg._windows_registry_path() == ""


def test_packaged_and_common_windows_search_directories(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    executable = tmp_path / "app" / "app.exe"
    bundle = tmp_path / "bundle"
    executable.parent.mkdir()
    executable.write_bytes(b"")
    bundle.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "program-files"))
    monkeypatch.setenv("PROGRAMFILES(X86)", str(tmp_path / "program-files-x86"))
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "program-data"))
    monkeypatch.setattr(sys, "platform", "win32")

    assert ffmpeg._packaged_search_dirs() == [executable.parent, bundle]
    candidates = ffmpeg._common_windows_ffmpeg_dirs()
    assert tmp_path / "program-files" / "ffmpeg" / "bin" in candidates
    assert tmp_path / "local" / "Microsoft" / "WinGet" / "Links" in candidates


def test_packaged_and_common_search_are_empty_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sys, "frozen", False, raising=False)

    assert ffmpeg._packaged_search_dirs() == []
    assert ffmpeg._common_windows_ffmpeg_dirs() == []


def test_packaged_and_common_search_skip_empty_optional_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", "", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    assert ffmpeg._packaged_search_dirs() == [Path(sys.executable).resolve().parent]
    assert all("WinGet" not in str(path) for path in ffmpeg._common_windows_ffmpeg_dirs())


def test_resolve_prefers_existing_absolute_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    executable = tmp_path / "ffmpeg.exe"
    executable.write_bytes(b"")
    monkeypatch.setattr(ffmpeg.settings, "FFMPEG_COMMAND", str(executable))
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda *_args, **_kwargs: None)

    assert ffmpeg.resolve_ffmpeg_command() == str(executable)


def test_resolve_uses_path_then_packaged_candidate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    discovered = tmp_path / "path-ffmpeg.exe"
    bundled = tmp_path / "bundle" / "ffmpeg.exe"
    bundled.parent.mkdir()
    bundled.write_bytes(b"")
    monkeypatch.setattr(ffmpeg.settings, "FFMPEG_COMMAND", "ffmpeg.exe")
    monkeypatch.setattr(ffmpeg, "_windows_registry_path", lambda: "")
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda *_args, **_kwargs: str(discovered))

    assert ffmpeg.resolve_ffmpeg_command() == str(discovered)
    ffmpeg.resolve_ffmpeg_command.cache_clear()
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        ffmpeg, "_packaged_search_dirs", lambda: [tmp_path / "missing", bundled.parent]
    )
    monkeypatch.setattr(ffmpeg, "_common_windows_ffmpeg_dirs", lambda: [])

    assert ffmpeg.resolve_ffmpeg_command() == str(bundled)


def test_resolve_returns_configured_name_when_no_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ffmpeg.settings, "FFMPEG_COMMAND", "custom-ffmpeg")
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ffmpeg, "_windows_registry_path", lambda: "")
    monkeypatch.setattr(ffmpeg, "_packaged_search_dirs", lambda: [])
    monkeypatch.setattr(ffmpeg, "_common_windows_ffmpeg_dirs", lambda: [])

    assert ffmpeg.resolve_ffmpeg_command() == "custom-ffmpeg"


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("ffmpeg version 6.1.2\nextra", (6, 1, 2)),
        ("ffmpeg version n4.4", (4, 4, 0)),
        ("ffmpeg version 2025-08-04-git-build", (2025, 8, 4)),
        ("custom build", None),
    ],
)
def test_version_decoding_and_first_line(
    output: str, expected: tuple[int, int, int] | None
) -> None:
    result = subprocess.CompletedProcess(["ffmpeg"], 0, output, "stderr")

    assert ffmpeg._first_version_line(result) == output.splitlines()[0].strip()
    assert ffmpeg.parse_ffmpeg_semver(output) == expected


def test_first_version_line_uses_stderr_or_unknown() -> None:
    stderr_result = subprocess.CompletedProcess([], 0, "", " stderr \nnext")

    assert ffmpeg._first_version_line(stderr_result) == "stderr"
    assert ffmpeg._first_version_line(subprocess.CompletedProcess([], 0, "", "")) == "unknown"


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ("custom build", (True, "custom build")),
        (
            "ffmpeg version 4.2.9",
            (False, "ffmpeg too old: found ffmpeg version 4.2.9, require >= 4.3.0"),
        ),
        ("ffmpeg version 4.3.0", (True, "ffmpeg version 4.3.0")),
    ],
)
def test_preflight_decodes_versions(
    monkeypatch: pytest.MonkeyPatch, result: str, expected: tuple[bool, str]
) -> None:
    monkeypatch.setattr(
        ffmpeg,
        "_run_ffmpeg_version",
        lambda: subprocess.CompletedProcess(["ffmpeg"], 0, result, ""),
    )

    assert ffmpeg.preflight_check() == expected


@pytest.mark.parametrize(
    ("error", "fragment"),
    [
        (FileNotFoundError("missing"), "not found"),
        (subprocess.CalledProcessError(2, ["ffmpeg"]), "invocation failed"),
        (subprocess.TimeoutExpired(["ffmpeg"], 15), "check error"),
        (PermissionError("denied"), "check error"),
        (OSError("device unavailable"), "check error"),
    ],
)
def test_preflight_and_about_translate_probe_failures(
    monkeypatch: pytest.MonkeyPatch, error: OSError | subprocess.CalledProcessError, fragment: str
) -> None:
    def raise_error() -> subprocess.CompletedProcess[str]:
        raise error

    monkeypatch.setattr(ffmpeg, "_run_ffmpeg_version", raise_error)

    assert fragment in ffmpeg.preflight_check()[1]
    assert ffmpeg.get_ffmpeg_version() == "unknown"


@pytest.mark.parametrize("error", [PermissionError("denied"), OSError("device unavailable")])
def test_preflight_translates_operational_os_errors(
    monkeypatch: pytest.MonkeyPatch, error: OSError
) -> None:
    def raise_error() -> subprocess.CompletedProcess[str]:
        raise error

    monkeypatch.setattr(ffmpeg, "_run_ffmpeg_version", raise_error)

    assert ffmpeg.preflight_check() == (False, f"ffmpeg check error: {error}")


def test_get_ffmpeg_version_surfaces_runtime_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    class ProbeRuntimeError(RuntimeError):
        pass

    def raise_error() -> subprocess.CompletedProcess[str]:
        raise ProbeRuntimeError("bad probe seam")

    monkeypatch.setattr(ffmpeg, "_run_ffmpeg_version", raise_error)

    with pytest.raises(ProbeRuntimeError, match="bad probe seam"):
        ffmpeg.get_ffmpeg_version()


def test_require_preflight_returns_or_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ffmpeg, "preflight_check", lambda: (True, "ffmpeg version 7"))
    assert ffmpeg.require_preflight() == "ffmpeg version 7"
    monkeypatch.setattr(ffmpeg, "preflight_check", lambda: (False, "ffmpeg NOT FOUND"))
    with pytest.raises(FFmpegNotFoundError):
        ffmpeg.require_preflight()
    monkeypatch.setattr(ffmpeg, "preflight_check", lambda: (False, "ffmpeg too old"))
    with pytest.raises(FFmpegError):
        ffmpeg.require_preflight()


def test_real_ffmpeg_probe_reports_a_version() -> None:
    result = ffmpeg._run_ffmpeg_version()

    assert result.returncode == 0
    assert ffmpeg.get_ffmpeg_version().startswith("ffmpeg version")
