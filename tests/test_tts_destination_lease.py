from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from openai_tts_gui.tts._destination import (
    ExistingResource,
    MissingResource,
    destination_paths,
    observe_destination,
)
from openai_tts_gui.tts._lease import acquire_lease

_LOCK_HOLDER = """
import sys
from pathlib import Path

from openai_tts_gui.tts._destination import destination_paths
from openai_tts_gui.tts._lease import acquire_lease

lease = acquire_lease(destination_paths(sys.argv[1]), Path(sys.argv[2]))
if lease is None:
    raise SystemExit(2)
print('ready', flush=True)
sys.stdin.read()
lease.release()
"""

_RAW_LOCK_HOLDER = """
import os
import sys
from pathlib import Path

from openai_tts_gui.tts._lease import _try_lock, _unlock

descriptor = _try_lock(Path(sys.argv[1]))
if descriptor is None:
    raise SystemExit(2)
print('ready', flush=True)
sys.stdin.read()
_unlock(descriptor)
os.close(descriptor)
"""

_BARRIERED_LEASE_WORKER = """
import sys
from pathlib import Path

from openai_tts_gui.tts._destination import destination_paths
from openai_tts_gui.tts._lease import acquire_lease

print('ready', flush=True)
sys.stdin.readline()
lease = acquire_lease(destination_paths(sys.argv[1]), Path(sys.argv[2]))
print('acquired' if lease is not None else 'busy', flush=True)
sys.stdin.readline()
if lease is not None:
    lease.release()
"""


def test_destination_observation_normalizes_aliases_and_tracks_missing_pair(tmp_path: Path) -> None:
    # Given: two lexical aliases for an absent canonical output pair.
    target = tmp_path / "nested" / ".." / "nested" / "speech.wav"

    # When: the destination contract derives identities and takes its one-pass snapshot.
    paths = destination_paths(str(target))
    observation = observe_destination(paths)

    # Then: audio and sidecar identities are stable, unique, and both report missing.
    assert paths.audio.normalized == (tmp_path / "nested" / "speech.wav").as_posix().casefold()
    assert paths.resources == tuple(
        sorted(paths.resources, key=lambda item: (item.digest, item.normalized))
    )
    assert all(isinstance(item.state, MissingResource) for item in observation.resources)


def test_destination_observation_tracks_exact_lstat_state(tmp_path: Path) -> None:
    # Given: an existing audio file and an absent sidecar.
    target = tmp_path / "speech.wav"
    target.write_bytes(b"audio")

    # When: the destination state is sampled once.
    paths = destination_paths(str(target))
    observation = observe_destination(paths)

    # Then: the audio uses the exact lstat identity while the sidecar remains missing.
    audio = next(item for item in observation.resources if item.identity == paths.audio)
    sidecar = next(item for item in observation.resources if item.identity == paths.sidecar)
    assert isinstance(audio.state, ExistingResource)
    assert audio.state.st_size == len(b"audio")
    assert isinstance(sidecar.state, MissingResource)


def test_destination_identity_normalizes_after_casefold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "E\u0301cho.wav"
    monkeypatch.setattr("openai_tts_gui.tts._destination.sys.platform", "darwin")

    paths = destination_paths(str(target))

    assert paths.audio.normalized.endswith("\u00e9cho.wav")


def test_lease_nonblocking_overlap_and_release(tmp_path: Path) -> None:
    # Given: canonical paths where the second request targets the first sidecar resource.
    lock_root = tmp_path / "locks"
    first = destination_paths(str(tmp_path / "speech.wav"))
    overlapping = destination_paths(str(tmp_path / "speech.wav.json"))

    # When: the first request holds the complete resource lease.
    held = acquire_lease(first, lock_root)
    assert held is not None
    blocked = acquire_lease(overlapping, lock_root)
    held.release()
    acquired_after_release = acquire_lease(overlapping, lock_root)
    assert acquired_after_release is not None
    acquired_after_release.release()

    # Then: overlapping publication never blocks and becomes available after release.
    assert blocked is None
    assert acquired_after_release is not None
    assert {f"publication-{resource.digest}.lock" for resource in first.resources}.issubset(
        {path.name for path in lock_root.iterdir()}
    )


@pytest.mark.parametrize(
    "held_name, contender_name, expected_busy",
    [
        ("speech.wav", "speech.wav", True),
        ("speech.wav", "speech.wav.json", True),
        ("speech.wav", "other.wav", False),
    ],
)
def test_lease_coordinates_real_processes_and_releases_after_exit(
    tmp_path: Path, held_name: str, contender_name: str, expected_busy: bool
) -> None:
    # Given: a separately spawned Python process holding the complete first resource set.
    lock_root = tmp_path / "persistent-locks"
    held_output = tmp_path / held_name
    holder = subprocess.Popen(
        [sys.executable, "-c", _LOCK_HOLDER, str(held_output), str(lock_root)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "ready"

        # When: this process asks for the contender resource set while the holder is alive.
        contender = acquire_lease(destination_paths(str(tmp_path / contender_name)), lock_root)

        # Then: overlapping paths are busy, while disjoint paths acquire and release independently.
        assert (contender is None) is expected_busy
        if contender is not None:
            contender.release()
    finally:
        assert holder.stdin is not None
        holder.stdin.close()
        assert holder.wait(timeout=5) == 0

    # Then: child exit makes the contender immediately available and retains persistent lock files.
    after_exit = acquire_lease(destination_paths(str(tmp_path / contender_name)), lock_root)
    assert after_exit is not None
    after_exit.release()
    assert list(lock_root.glob("publication-*.lock"))


def test_real_partial_acquisition_unwinds_first_resource_for_third_process(tmp_path: Path) -> None:
    # Given: a child holding the contender's second digest-sorted lock resource.
    lock_root = tmp_path / "partial-unwind-locks"
    paths = destination_paths(str(tmp_path / "speech.wav"))
    first, second = paths.resources
    second_lock = lock_root / f"publication-{second.digest}.lock"
    first_lock = lock_root / f"publication-{first.digest}.lock"
    lock_root.mkdir()
    holder = subprocess.Popen(
        [sys.executable, "-c", _RAW_LOCK_HOLDER, str(second_lock)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "ready"

        # When: the contender acquires first and fails at the held second resource.
        assert acquire_lease(paths, lock_root) is None
        third = subprocess.Popen(
            [sys.executable, "-c", _RAW_LOCK_HOLDER, str(first_lock)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        try:
            assert third.stdout is not None
            assert third.stdout.readline().strip() == "ready"
        finally:
            assert third.stdin is not None
            third.stdin.close()
            assert third.wait(timeout=5) == 0
    finally:
        assert holder.stdin is not None
        holder.stdin.close()
        assert holder.wait(timeout=5) == 0


def test_real_inverse_order_overlap_workers_finish_without_deadlock(tmp_path: Path) -> None:
    # Given: two foreground workers synchronized before overlapping lease acquisition.
    lock_root = tmp_path / "inverse-order-locks"
    first_output = tmp_path / "speech.wav"
    second_output = tmp_path / "speech.wav.json"
    workers = [
        subprocess.Popen(
            [sys.executable, "-c", _BARRIERED_LEASE_WORKER, str(output), str(lock_root)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        for output in (second_output, first_output)
    ]
    try:
        for worker in workers:
            assert worker.stdout is not None
            assert worker.stdout.readline().strip() == "ready"

        # When: the barrier releases inverse requesters together.
        for worker in workers:
            assert worker.stdin is not None
            worker.stdin.write("go\n")
            worker.stdin.flush()
        results = [
            worker.stdout.readline().strip() for worker in workers if worker.stdout is not None
        ]

        # Then: native nonblocking acquisition completes without an inverse-order deadlock.
        assert set(results).issubset({"acquired", "busy"})
    finally:
        for worker in workers:
            if worker.stdin is not None and not worker.stdin.closed:
                worker.stdin.write("stop\n")
                worker.stdin.close()
        for worker in workers:
            assert worker.wait(timeout=5) == 0
