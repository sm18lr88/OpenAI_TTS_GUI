from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import compatibility_v1_contracts as contracts


def _fixture_copy(tmp_path: Path, payload: dict[str, contracts.JsonValue]) -> Path:
    path = tmp_path / "compatibility.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_fixture_rejects_missing_required_top_level_section(monkeypatch, tmp_path: Path) -> None:
    payload = contracts.load_manifest()
    del payload["worker"]
    monkeypatch.setattr(contracts, "FIXTURE", _fixture_copy(tmp_path, payload))

    with pytest.raises(AssertionError):
        contracts.load_manifest()


def test_fixture_rejects_wrong_schema_version_type(monkeypatch, tmp_path: Path) -> None:
    payload = contracts.load_manifest()
    payload["schema_version"] = "1"
    monkeypatch.setattr(contracts, "FIXTURE", _fixture_copy(tmp_path, payload))

    with pytest.raises(AssertionError):
        contracts.load_manifest()


def test_fixture_rejects_unknown_top_level_section(monkeypatch, tmp_path: Path) -> None:
    payload = contracts.load_manifest()
    payload["unexpected"] = True
    monkeypatch.setattr(contracts, "FIXTURE", _fixture_copy(tmp_path, payload))

    with pytest.raises(AssertionError):
        contracts.load_manifest()


def test_fixture_rejects_unknown_nested_section(monkeypatch, tmp_path: Path) -> None:
    payload = contracts.load_manifest()
    service = contracts.mapping(payload["service"])
    service["unexpected"] = True
    monkeypatch.setattr(contracts, "FIXTURE", _fixture_copy(tmp_path, payload))

    with pytest.raises(AssertionError):
        contracts.load_manifest()


@pytest.mark.parametrize(
    ("field", "value"),
    [("changed", "Changed"), ("empty_text", "Changed")],
)
def test_fixture_rejects_changed_validation_error_mapping(
    monkeypatch, tmp_path: Path, field: str, value: str
) -> None:
    payload = contracts.load_manifest()
    service = contracts.mapping(payload["service"])
    generate = contracts.mapping(service["generate"])
    validation_errors = contracts.mapping(generate["validation_errors"])
    validation_errors.clear()
    validation_errors[field] = value
    monkeypatch.setattr(contracts, "FIXTURE", _fixture_copy(tmp_path, payload))

    with pytest.raises(AssertionError):
        contracts.load_manifest()
