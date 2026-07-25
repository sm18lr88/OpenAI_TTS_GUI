from __future__ import annotations

from pathlib import Path

from openai_tts_gui.errors import DestinationObservationError
from openai_tts_gui.tts import TTSService, _execution
from openai_tts_gui.tts._contracts import GenerationConfig, GenerationRequest
from openai_tts_gui.tts._destination import destination_paths, observe_destination
from openai_tts_gui.tts._lease import DestinationLease
from openai_tts_gui.tts._outcomes import DestinationChangedOutcome, OutputBusyOutcome


def _request(output: Path) -> GenerationRequest:
    return GenerationRequest("text", str(output), GenerationConfig(response_format="wav"))


def test_execute_reports_busy_before_provider_work(monkeypatch, tmp_path: Path) -> None:
    # Given: the destination lease is unavailable after successful preflight and splitting.
    monkeypatch.setattr("openai_tts_gui.tts._service.require_preflight", lambda: "ffmpeg OK")
    monkeypatch.setattr("openai_tts_gui.tts._service.split_text", lambda _text, _size: ["text"])
    monkeypatch.setattr(_execution, "acquire_lease", lambda _paths, _root: None)

    # When: execution reaches lease acquisition.
    outcome = TTSService(api_key="sk-test").execute(_request(tmp_path / "busy.wav"))

    # Then: it returns the explicit busy outcome without contacting a provider.
    assert isinstance(outcome, OutputBusyOutcome)
    assert outcome.output_path == str(tmp_path / "busy.wav")


def test_execute_reports_initial_observation_failure(monkeypatch, tmp_path: Path) -> None:
    # Given: the destination cannot be observed before a lease is requested.
    monkeypatch.setattr("openai_tts_gui.tts._service.require_preflight", lambda: "ffmpeg OK")
    monkeypatch.setattr("openai_tts_gui.tts._service.split_text", lambda _text, _size: ["text"])

    def fail_observation(_paths) -> None:
        raise DestinationObservationError("blocked.wav", "access denied")

    monkeypatch.setattr(_execution, "observe_destination", fail_observation)

    # When: execution samples the requested destination.
    outcome = TTSService(api_key="sk-test").execute(_request(tmp_path / "blocked.wav"))

    # Then: it returns a destination-change outcome with the sampling error.
    assert isinstance(outcome, DestinationChangedOutcome)
    assert outcome.reason == "Cannot observe destination blocked.wav: access denied"


def test_execute_reports_stale_destination_after_lease(monkeypatch, tmp_path: Path) -> None:
    # Given: the caller snapshot predates a destination change and lease acquisition succeeds.
    output = tmp_path / "stale.wav"
    expected = observe_destination(destination_paths(str(output)))
    output.write_bytes(b"changed-after-observation")
    monkeypatch.setattr("openai_tts_gui.tts._service.require_preflight", lambda: "ffmpeg OK")
    monkeypatch.setattr("openai_tts_gui.tts._service.split_text", lambda _text, _size: ["text"])
    monkeypatch.setattr(
        _execution,
        "acquire_lease",
        lambda _paths, _root: DestinationLease(tmp_path / "locks", ()),
    )

    # When: execution re-observes the destination while holding its lease.
    outcome = TTSService(api_key="sk-test").execute(
        GenerationRequest("text", str(output), GenerationConfig(response_format="wav"), expected)
    )

    # Then: it declines to publish over the changed destination.
    assert isinstance(outcome, DestinationChangedOutcome)
    assert outcome.reason == "observation changed"


def test_execute_reports_observation_failure_after_lease(monkeypatch, tmp_path: Path) -> None:
    # Given: a caller snapshot exists, the lease succeeds, and the re-observation is denied.
    output = tmp_path / "recheck.wav"
    expected = observe_destination(destination_paths(str(output)))
    monkeypatch.setattr("openai_tts_gui.tts._service.require_preflight", lambda: "ffmpeg OK")
    monkeypatch.setattr("openai_tts_gui.tts._service.split_text", lambda _text, _size: ["text"])
    monkeypatch.setattr(
        _execution,
        "acquire_lease",
        lambda _paths, _root: DestinationLease(tmp_path / "locks", ()),
    )

    def fail_reobservation(_paths) -> None:
        raise DestinationObservationError("recheck.wav", "access denied")

    monkeypatch.setattr(_execution, "observe_destination", fail_reobservation)

    # When: execution samples the destination while holding the lease.
    outcome = TTSService(api_key="sk-test").execute(
        GenerationRequest("text", str(output), GenerationConfig(response_format="wav"), expected)
    )

    # Then: the result preserves the observed recheck failure.
    assert isinstance(outcome, DestinationChangedOutcome)
    assert outcome.reason == "Cannot observe destination recheck.wav: access denied"
