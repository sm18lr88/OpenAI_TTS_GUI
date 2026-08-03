from __future__ import annotations

import importlib.abc
import importlib.util
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType

import pytest

from openai_tts_gui.tts import _service as service_module


class _DenyOpenAI(importlib.abc.MetaPathFinder):
    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None,
        target: ModuleType | None = None,
    ) -> ModuleSpec | None:
        if fullname == "openai":
            raise ModuleNotFoundError("openai disabled for isolated fallback coverage")
        return None


def test_tts_service_reports_missing_optional_openai_dependency_without_cache_pollution() -> None:
    # Given: an isolated module import that denies the installed optional dependency.
    alias = "openai_tts_gui.tts._service_without_openai"
    assert service_module.__file__ is not None
    source = Path(service_module.__file__)
    finder = _DenyOpenAI()
    original_openai = sys.modules.pop("openai")
    spec = importlib.util.spec_from_file_location(alias, source)
    assert spec is not None
    assert spec.loader is not None
    fallback_module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = fallback_module
    sys.meta_path.insert(0, finder)

    try:
        # When: the public service client is requested under the missing-dependency fallback.
        spec.loader.exec_module(fallback_module)
        service = fallback_module.TTSService(api_key="synthetic")
        with pytest.raises(ModuleNotFoundError, match="TTSService requires.*openai"):
            service._get_client()
        status_error = fallback_module.APIStatusError(
            "unavailable", status_code=503, request_id="req-fallback"
        )
    finally:
        # Then: the parent interpreter restores its original dependency and import cache.
        sys.meta_path.remove(finder)
        sys.modules.pop(alias)
        sys.modules["openai"] = original_openai

    assert service_module.__name__ == "openai_tts_gui.tts._service"
    assert (status_error.status_code, status_error.request_id) == (503, "req-fallback")


def test_public_tts_facade_reports_optional_dependency_denial_in_clean_subprocess() -> None:
    # Given: a child interpreter that rejects OpenAI before importing the public facade.
    source = Path(__file__).parents[1] / "src"
    code = """
import builtins
import json

real_import = builtins.__import__

def deny_openai(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "openai" or name.startswith("openai."):
        raise ModuleNotFoundError("blocked by isolated test")
    return real_import(name, globals, locals, fromlist, level)

builtins.__import__ = deny_openai
from openai_tts_gui.tts import TTSService, compute_backoff
result = {
    "service": TTSService(api_key="synthetic").__class__.__name__,
    "backoff": callable(compute_backoff),
}
try:
    TTSService(api_key="synthetic")._get_client()
except ModuleNotFoundError as error:
    result.update(
        error_type=type(error).__name__,
        message=str(error),
        cause_type=type(error.__cause__).__name__,
    )
print(json.dumps(result, sort_keys=True))
"""
    environment = os.environ | {"PYTHONPATH": str(source)}

    # When: the public TTS service resolves its client without the optional dependency.
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )

    # Then: the fallback is observable without parent process imports or network activity.
    assert json.loads(result.stdout) == {
        "backoff": True,
        "cause_type": "ModuleNotFoundError",
        "error_type": "ModuleNotFoundError",
        "message": "TTSService requires the 'openai' package.",
        "service": "TTSService",
    }
    assert result.stderr == ""
