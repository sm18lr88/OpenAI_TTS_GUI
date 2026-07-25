from __future__ import annotations

from importlib import import_module
from types import ModuleType

import pytest

from tests.compatibility_v1_contracts import load_manifest, mapping, string_mapping, strings


def _assert_facade_exports(facade: ModuleType, expected: list[str]) -> None:
    assert tuple(getattr(facade, "__all__", ())) == tuple(expected)
    for name in expected:
        assert hasattr(facade, name)


def test_v1_facades_expose_manifested_names() -> None:
    facades = mapping(load_manifest()["facades"])

    for module_name, contract in facades.items():
        _assert_facade_exports(import_module(module_name), strings(mapping(contract)["all"]))


def test_core_facade_does_not_add_unshipped_preflight_requirement() -> None:
    core = import_module("openai_tts_gui.core")

    assert "require_preflight" not in core.__all__
    with pytest.raises(AttributeError):
        core.__getattr__("require_preflight")


def test_v1_tts_backoff_alias_is_the_shipped_callable() -> None:
    facades = mapping(load_manifest()["facades"])
    aliases = string_mapping(mapping(facades["openai_tts_gui.tts"])["aliases"])
    facade = import_module("openai_tts_gui.tts")

    for alias, canonical_name in aliases.items():
        assert getattr(facade, alias) is getattr(facade, canonical_name)


def test_v1_facade_check_rejects_missing_manifest_export() -> None:
    facade = ModuleType("missing_v1_export")
    facade.__dict__["__all__"] = ["TTSService"]

    with pytest.raises(AssertionError):
        _assert_facade_exports(facade, ["TTSService"])
