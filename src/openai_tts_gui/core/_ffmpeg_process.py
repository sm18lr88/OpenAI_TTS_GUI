from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from ..errors import FFmpegError, FFmpegNotFoundError

_STOP_GRACE_SECONDS: Final[float] = 1.0


@dataclass(frozen=True, slots=True)
class ProcessOutput:
    stdout: str
    stderr: str
    returncode: int
    cancelled_before_attach: bool
    stop_requested: bool


class FfmpegProcess:
    """Owns one ffmpeg process group until its process is reaped."""

    def __init__(self, command: list[str]) -> None:
        self._command = command
        self._process: subprocess.Popen[str] | None = None
        self._stop_requested = False

    def run(self, on_started: Callable[[FfmpegProcess], bool] | None = None) -> ProcessOutput:
        try:
            self._process = subprocess.Popen(
                self._command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=os.name != "nt",
                creationflags=(
                    subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
                ),
            )
        except FileNotFoundError as exc:
            raise FFmpegNotFoundError(f"{self._command[0]} not found.") from exc
        cancelled_before_attach = on_started is not None and not on_started(self)
        if cancelled_before_attach:
            self.request_stop()
        stdout, stderr = self._communicate()
        return ProcessOutput(
            stdout,
            stderr,
            self._process.returncode,
            cancelled_before_attach,
            self._stop_requested,
        )

    def request_stop(self) -> None:
        process = self._process
        if process is None:
            return
        self._stop_requested = True
        if process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T"],
                capture_output=True,
                check=False,
                text=True,
            )
        else:
            self._signal_group("TERM", process.pid)

    def _communicate(self) -> tuple[str, str]:
        process = self._process
        if process is None:
            raise FFmpegError("ffmpeg process was not started")
        try:
            return process.communicate(timeout=_STOP_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            if not self._stop_requested:
                return process.communicate()
            self._escalate_stop(process.pid)
            return process.communicate()

    @staticmethod
    def _escalate_stop(pid: int) -> None:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                check=False,
                text=True,
            )
        else:
            FfmpegProcess._signal_group("KILL", pid)

    @staticmethod
    def _signal_group(signal_name: str, pid: int) -> None:
        subprocess.run(
            ["/bin/kill", f"-{signal_name}", "--", f"-{pid}"],
            capture_output=True,
            check=False,
            text=True,
        )
