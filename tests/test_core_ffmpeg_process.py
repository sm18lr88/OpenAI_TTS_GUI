from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading

import pytest

from openai_tts_gui.core import _ffmpeg_process as process_module
from openai_tts_gui.core._ffmpeg_process import FfmpegProcess
from openai_tts_gui.tts._contracts import CancellationStage
from openai_tts_gui.tts._run_state import RunState


def test_process_attaches_before_cancel_and_is_reaped() -> None:
    # Given: a long-running process whose concrete stopper is attached to a run state.
    state = RunState(1, None)
    attached = threading.Event()
    completed = threading.Event()
    process = FfmpegProcess([sys.executable, "-c", "import time; time.sleep(60)"])
    output: list[int] = []

    def run_process() -> None:
        result = process.run(lambda stopper: _attach(state, stopper, attached))
        output.append(result.returncode)
        state.finish_ffmpeg()
        completed.set()

    worker = threading.Thread(target=run_process)
    worker.start()
    assert attached.wait(timeout=5)

    # When: cancellation arrives while the process is running.
    stage = state.request_cancel()
    assert completed.wait(timeout=5)
    worker.join(timeout=5)

    # Then: cancellation observed ffmpeg, the process exited, and terminal accounting can freeze.
    assert stage is CancellationStage.DURING_FFMPEG
    assert output and output[0] != 0
    assert process._process is not None
    assert process._process.poll() is not None
    assert state.freeze().cancellation_stage is CancellationStage.DURING_FFMPEG


def _attach(state: RunState, stopper: FfmpegProcess, attached: threading.Event) -> bool:
    accepted = state.begin_ffmpeg(stopper)
    attached.set()
    return accepted


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as error:
        return getattr(error, "winerror", None) not in {87, 1168}
    return True


def test_process_tree_cancel_reaps_only_the_owned_root_and_child() -> None:
    # Given: an owned root that announces its child PID and an unrelated same-runtime sentinel.
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(5.0)
    port = int(listener.getsockname()[1])
    child_script = "import threading; threading.Event().wait()"
    root_script = (
        "import socket, subprocess, sys; "
        f"child = subprocess.Popen([sys.executable, '-u', '-c', {child_script!r}]); "
        f"connection = socket.create_connection(('127.0.0.1', {port})); "
        "connection.sendall(str(child.pid).encode()); connection.close(); child.wait()"
    )
    state = RunState(1, None)
    attached = threading.Event()
    completed = threading.Event()
    process = FfmpegProcess([sys.executable, "-u", "-c", root_script])
    sentinel = subprocess.Popen([sys.executable, "-u", "-c", child_script])
    output: list[int] = []

    def run_process() -> None:
        result = process.run(lambda stopper: _attach(state, stopper, attached))
        output.append(result.returncode)
        state.finish_ffmpeg()
        completed.set()

    worker = threading.Thread(target=run_process)
    worker.start()
    try:
        assert attached.wait(timeout=5.0)
        connection, _ = listener.accept()
        with connection:
            child_pid = int(connection.recv(32).decode())

        # When: cancellation targets the attached root process group/tree by exact PID.
        assert state.request_cancel() is CancellationStage.DURING_FFMPEG

        # Then: root and announced child exit, while the unrelated sentinel remains running.
        assert completed.wait(timeout=5.0)
        worker.join(timeout=5.0)
        assert output and output[0] != 0
        assert process._process is not None and process._process.poll() is not None
        assert not _pid_exists(child_pid)
        assert sentinel.poll() is None
        assert state.freeze().cancellation_stage is CancellationStage.DURING_FFMPEG
    finally:
        listener.close()
        process.request_stop()
        worker.join(timeout=5.0)
        if sentinel.poll() is None:
            sentinel.terminate()
        sentinel.wait(timeout=5.0)


def test_request_stop_signals_an_owned_windows_process_tree(monkeypatch) -> None:
    # Given: an owned process whose reaping remains the communicate owner's responsibility.
    class StillRunningProcess:
        pid = 41

        def poll(self) -> None:
            return None

    commands: list[list[str]] = []
    process = FfmpegProcess(["ffmpeg"])
    monkeypatch.setattr(process, "_process", StillRunningProcess())
    monkeypatch.setattr(process_module.os, "name", "nt")
    monkeypatch.setattr(
        process_module.subprocess,
        "run",
        lambda command, **_kwargs: commands.append(command),
    )

    # When: cancellation requests the GUI-safe graceful stop.
    process.request_stop()

    # Then: the exact root PID and tree flag are retained without blocking escalation.
    assert commands == [["taskkill", "/PID", "41", "/T"]]


def test_posix_group_signal_terminates_kill_options(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a captured POSIX kill invocation for an owned process group.
    commands: list[list[str]] = []
    monkeypatch.setattr(
        process_module.subprocess,
        "run",
        lambda command, **_kwargs: commands.append(command),
    )

    # When: the process owner signals the negative group identifier.
    FfmpegProcess._signal_group("TERM", 41)

    # Then: the negative PID cannot be parsed as another command option.
    assert commands == [["/bin/kill", "-TERM", "--", "-41"]]
