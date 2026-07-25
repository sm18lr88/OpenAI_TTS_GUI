from __future__ import annotations

import inspect
from pathlib import Path
from typing import Final, get_type_hints

import pytest

from openai_tts_gui import ConfigError, TTSChunkError, cli
from openai_tts_gui.tts import TTSService, _compute_backoff, compute_backoff
from tests.compatibility_v1_contracts import (
    ValidationErrorName,
    ValidationErrors,
    integer_mapping,
    load_manifest,
    mapping,
    number,
    strings,
    validation_errors,
)

VALIDATION_ERROR_TYPES: Final[dict[ValidationErrorName, type[ConfigError | TTSChunkError]]] = {
    ValidationErrorName.CONFIG: ConfigError,
    ValidationErrorName.TTS_CHUNK: TTSChunkError,
}


def test_v1_tts_service_constructor_and_keyword_generate_signature() -> None:
    service_contract = mapping(load_manifest()["service"])
    constructor_contract = mapping(service_contract["constructor"])
    generate_contract = mapping(service_contract["generate"])

    constructor = inspect.signature(TTSService)
    generate = inspect.signature(TTSService.generate)
    constructor_parameters = strings(constructor_contract["parameters"])
    keyword_only = strings(generate_contract["keyword_only"])
    defaults = mapping(generate_contract["defaults"])

    assert list(constructor.parameters) == constructor_parameters[1:]
    assert constructor.parameters["base_url"].default is None
    constructor_defaults = mapping(constructor_contract["defaults"])
    assert constructor.parameters["timeout"].default == number(constructor_defaults["timeout"])
    assert [
        parameter.name
        for parameter in generate.parameters.values()
        if parameter.kind is inspect.Parameter.KEYWORD_ONLY
    ] == keyword_only
    assert generate.parameters["model"].default == defaults["model"]
    assert generate.parameters["voice"].default == defaults["voice"]
    assert generate.parameters["response_format"].default == defaults["response_format"]
    assert generate.parameters["speed"].default == number(defaults["speed"])
    assert generate.parameters["instructions"].default == defaults["instructions"]
    assert generate.parameters["parallelism"].default is None
    assert generate.parameters["retain_files"].default is False
    nullable_defaults = ("on_progress", "on_status", "on_parallelism", "cancel_event")
    assert all(generate.parameters[name].default is None for name in nullable_defaults)
    runtime_return_type = get_type_hints(TTSService.generate)["return"]
    assert runtime_return_type is str
    assert generate_contract["return_type"] == runtime_return_type.__name__
    assert TTSService(api_key="compatibility-key")


def _validation_errors() -> ValidationErrors:
    service_contract = mapping(load_manifest()["service"])
    generate_contract = mapping(service_contract["generate"])
    return validation_errors(generate_contract["validation_errors"])


def test_v1_tts_service_preserves_empty_text_fixture_validation_error() -> None:
    with pytest.raises(VALIDATION_ERROR_TYPES[_validation_errors()["empty_text"]]):
        TTSService(api_key="compatibility-key").generate(text=" ", output_path="out.mp3")


def test_v1_tts_service_preserves_invalid_model_fixture_validation_error() -> None:
    with pytest.raises(VALIDATION_ERROR_TYPES[_validation_errors()["invalid_model"]]):
        TTSService(api_key="compatibility-key").generate(
            text="text", output_path="out.mp3", model="not-a-model"
        )


def test_v1_tts_service_preserves_invalid_speed_fixture_validation_error() -> None:
    with pytest.raises(VALIDATION_ERROR_TYPES[_validation_errors()["invalid_speed"]]):
        TTSService(api_key="compatibility-key").generate(
            text="text", output_path="out.mp3", speed=4.01
        )


def test_v1_tts_generate_rejects_positional_arguments_and_backoff_alias() -> None:
    with pytest.raises(TypeError):
        TTSService(api_key="compatibility-key").generate("text", "out.mp3")

    assert _compute_backoff is compute_backoff


def test_v1_cli_flags_and_exit_classes(monkeypatch, capsys, tmp_path: Path) -> None:
    cli_contract = mapping(load_manifest()["cli"])
    flags = strings(cli_contract["flags"])
    exit_codes = integer_mapping(cli_contract["exit_codes"])
    monkeypatch.setattr(cli.settings, "ensure_directories", lambda: None)

    with pytest.raises(SystemExit) as help_exit:
        cli.main(["--help"])
    assert help_exit.value.code == exit_codes["success"]
    help_output = capsys.readouterr().out
    assert all(flag in help_output for flag in flags)

    assert cli.main([]) == exit_codes["usage"]
    capsys.readouterr()
    assert (
        cli.main(["--in", "input.txt", "--out", "out.mp3", "--speed", "4.01"])
        == exit_codes["usage"]
    )
    capsys.readouterr()
    monkeypatch.setenv("OPENAI_API_KEY", "compatibility-key")
    assert (
        cli.main(["--in", str(tmp_path / "missing.txt"), "--out", "out.mp3"])
        == exit_codes["failure"]
    )
    assert "Traceback" not in capsys.readouterr().err
