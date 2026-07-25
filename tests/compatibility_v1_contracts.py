from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Final, Literal, TypedDict

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
type ValidationCase = Literal["empty_text", "invalid_model", "invalid_speed"]


class ValidationErrorName(StrEnum):
    TTS_CHUNK = "TTSChunkError"
    CONFIG = "ConfigError"


class ValidationErrors(TypedDict):
    empty_text: ValidationErrorName
    invalid_model: ValidationErrorName
    invalid_speed: ValidationErrorName


FIXTURE: Final = Path(__file__).with_name("fixtures") / "compatibility_v1.json"
TOP_LEVEL_KEYS: Final = frozenset(
    {"schema_version", "facades", "service", "cli", "persistence", "worker"}
)
FACADE_MODULES: Final = frozenset(
    {
        "openai_tts_gui",
        "openai_tts_gui.tts",
        "openai_tts_gui.core",
        "openai_tts_gui.keystore",
        "openai_tts_gui.presets",
        "openai_tts_gui.utils",
    }
)
VALIDATION_ERROR_KEYS: Final = frozenset({"empty_text", "invalid_model", "invalid_speed"})


def load_manifest() -> dict[str, JsonValue]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    match payload:
        case dict():
            _validate_manifest(payload)
            return payload
        case _:
            raise AssertionError("compatibility fixture must be an object")


def mapping(value: JsonValue) -> dict[str, JsonValue]:
    match value:
        case dict():
            return value
        case _:
            raise AssertionError("compatibility fixture value must be an object")


def strings(value: JsonValue) -> list[str]:
    match value:
        case list() if all(isinstance(item, str) for item in value):
            return [item for item in value if isinstance(item, str)]
        case _:
            raise AssertionError("compatibility fixture value must be strings")


def string_mapping(value: JsonValue) -> dict[str, str]:
    match value:
        case dict() if all(isinstance(item, str) for item in value.values()):
            return {key: item for key, item in value.items() if isinstance(item, str)}
        case _:
            raise AssertionError("compatibility fixture value must map strings to strings")


def integer_mapping(value: JsonValue) -> dict[str, int]:
    match value:
        case dict() if all(type(item) is int for item in value.values()):
            return {key: item for key, item in value.items() if type(item) is int}
        case _:
            raise AssertionError("compatibility fixture value must map strings to integers")


def integer(value: JsonValue) -> int:
    match value:
        case int() if type(value) is int:
            return value
        case _:
            raise AssertionError("compatibility fixture value must be an integer")


def number(value: JsonValue) -> int | float:
    match value:
        case int() if type(value) is int:
            return value
        case float():
            return value
        case _:
            raise AssertionError("compatibility fixture value must be numeric")


def boolean(value: JsonValue) -> bool:
    match value:
        case bool():
            return value
        case _:
            raise AssertionError("compatibility fixture value must be boolean")


def _require_keys(value: dict[str, JsonValue], expected: frozenset[str]) -> None:
    if set(value) != expected:
        raise AssertionError("compatibility fixture keys differ from the v1 schema")


def _validate_manifest(payload: dict[str, JsonValue]) -> None:
    _require_keys(payload, TOP_LEVEL_KEYS)
    if integer(payload["schema_version"]) != 1:
        raise AssertionError("compatibility fixture schema version is unsupported")
    _validate_facades(mapping(payload["facades"]))
    _validate_service(mapping(payload["service"]))
    _validate_cli(mapping(payload["cli"]))
    _validate_persistence(mapping(payload["persistence"]))
    _validate_worker(mapping(payload["worker"]))


def _validate_facades(facades: dict[str, JsonValue]) -> None:
    _require_keys(facades, FACADE_MODULES)
    for module_name, contract_value in facades.items():
        contract = mapping(contract_value)
        expected = (
            frozenset({"all", "aliases"}) if module_name.endswith(".tts") else frozenset({"all"})
        )
        _require_keys(contract, expected)
        strings(contract["all"])
        if module_name.endswith(".tts"):
            string_mapping(contract["aliases"])


def _validate_service(service: dict[str, JsonValue]) -> None:
    _require_keys(service, frozenset({"constructor", "generate"}))
    constructor = mapping(service["constructor"])
    _require_keys(constructor, frozenset({"parameters", "defaults"}))
    strings(constructor["parameters"])
    constructor_defaults = mapping(constructor["defaults"])
    _require_keys(constructor_defaults, frozenset({"base_url", "timeout"}))
    if constructor_defaults["base_url"] is not None:
        raise AssertionError("constructor base_url default must be null")
    number(constructor_defaults["timeout"])
    generate = mapping(service["generate"])
    _require_keys(
        generate, frozenset({"keyword_only", "defaults", "return_type", "validation_errors"})
    )
    strings(generate["keyword_only"])
    if generate["return_type"] != "str":
        raise AssertionError("generate return type must be str")
    defaults = mapping(generate["defaults"])
    _require_keys(
        defaults,
        frozenset(
            {
                "model",
                "voice",
                "response_format",
                "speed",
                "instructions",
                "parallelism",
                "retain_files",
                "on_progress",
                "on_status",
                "on_parallelism",
                "cancel_event",
            }
        ),
    )
    number(defaults["speed"])
    boolean(defaults["retain_files"])
    for name in ("parallelism", "on_progress", "on_status", "on_parallelism", "cancel_event"):
        if defaults[name] is not None:
            raise AssertionError("nullable generate default must be null")
    validation_errors(generate["validation_errors"])


def validation_errors(value: JsonValue) -> ValidationErrors:
    errors = mapping(value)
    _require_keys(errors, VALIDATION_ERROR_KEYS)
    return {
        "empty_text": _validation_error_name(errors["empty_text"]),
        "invalid_model": _validation_error_name(errors["invalid_model"]),
        "invalid_speed": _validation_error_name(errors["invalid_speed"]),
    }


def _validation_error_name(value: JsonValue) -> ValidationErrorName:
    match value:
        case str() as name:
            match name:
                case "TTSChunkError":
                    return ValidationErrorName.TTS_CHUNK
                case "ConfigError":
                    return ValidationErrorName.CONFIG
                case _:
                    raise AssertionError("unsupported validation error type")
        case _:
            raise AssertionError("unsupported validation error type")


def _validate_cli(cli: dict[str, JsonValue]) -> None:
    _require_keys(cli, frozenset({"flags", "exit_codes"}))
    strings(cli["flags"])
    integer_mapping(cli["exit_codes"])


def _validate_persistence(persistence: dict[str, JsonValue]) -> None:
    _require_keys(
        persistence,
        frozenset(
            {
                "app_settings_defaults",
                "app_settings_v1",
                "presets_v1",
                "v1_sidecar",
                "v1_request_ids",
            }
        ),
    )
    for name in ("app_settings_defaults", "app_settings_v1"):
        settings = mapping(persistence[name])
        _require_keys(
            settings, frozenset({"parallelism", "parallelism_warning_shown", "retain_files"})
        )
        boolean(settings["parallelism_warning_shown"])
        boolean(settings["retain_files"])
    if mapping(persistence["app_settings_defaults"])["parallelism"] != "settings.PARALLELISM":
        raise AssertionError("app settings default parallelism must track settings")
    integer(mapping(persistence["app_settings_v1"])["parallelism"])
    string_mapping(persistence["presets_v1"])
    sidecar = mapping(persistence["v1_sidecar"])
    _require_keys(sidecar, frozenset({"parallelism_used", "request_meta"}))
    integer(sidecar["parallelism_used"])
    for request in mapping_list(sidecar["request_meta"]):
        _require_keys(request, frozenset({"request_id"}))
        if not isinstance(request["request_id"], str):
            raise AssertionError("request id must be a string")
    strings(persistence["v1_request_ids"])


def _validate_worker(worker: dict[str, JsonValue]) -> None:
    _require_keys(
        worker, frozenset({"constructor", "signals", "terminal_signals", "processor_base"})
    )
    constructor = mapping(worker["constructor"])
    _require_keys(constructor, frozenset({"parameters", "parent_default"}))
    strings(constructor["parameters"])
    if constructor["parent_default"] is not None:
        raise AssertionError("worker parent default must be null")
    integer_mapping(worker["signals"])
    strings(worker["terminal_signals"])
    if worker["processor_base"] != "TTSWorker":
        raise AssertionError("worker processor base must be TTSWorker")


def mapping_list(value: JsonValue) -> list[dict[str, JsonValue]]:
    match value:
        case list() if all(isinstance(item, dict) for item in value):
            return [item for item in value if isinstance(item, dict)]
        case _:
            raise AssertionError("compatibility fixture value must be objects")
