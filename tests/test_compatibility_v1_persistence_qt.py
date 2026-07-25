from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from openai_tts_gui import config
from openai_tts_gui.gui import TTSWindow
from openai_tts_gui.presets import load_presets
from tests.compatibility_v1_contracts import (
    boolean,
    integer,
    load_manifest,
    mapping,
    string_mapping,
    strings,
)


def test_v1_settings_and_presets_read_unversioned_json(tmp_path: Path) -> None:
    persistence = mapping(load_manifest()["persistence"])
    settings_path = tmp_path / "settings.json"
    presets_path = tmp_path / "presets.json"
    app_settings_defaults = mapping(persistence["app_settings_defaults"])
    app_settings = mapping(persistence["app_settings_v1"])
    presets = string_mapping(persistence["presets_v1"])

    loaded_defaults = config.load_app_settings(str(settings_path))
    assert app_settings_defaults["parallelism"] == "settings.PARALLELISM"
    assert loaded_defaults == {
        "parallelism": config.PARALLELISM,
        "parallelism_warning_shown": boolean(app_settings_defaults["parallelism_warning_shown"]),
        "retain_files": boolean(app_settings_defaults["retain_files"]),
    }
    assert load_presets(str(presets_path)) == {}
    settings_path.write_text(json.dumps(app_settings), encoding="utf-8")
    presets_path.write_text(json.dumps(presets), encoding="utf-8")

    assert config.load_app_settings(str(settings_path)) == {
        "parallelism": integer(app_settings["parallelism"]),
        "parallelism_warning_shown": boolean(app_settings["parallelism_warning_shown"]),
        "retain_files": boolean(app_settings["retain_files"]),
    }
    assert load_presets(str(presets_path)) == presets


def test_v1_sidecar_without_schema_version_remains_visible(
    qtbot, monkeypatch, tmp_path: Path
) -> None:
    persistence = mapping(load_manifest()["persistence"])
    sidecar_payload = mapping(persistence["v1_sidecar"])
    request_ids = strings(persistence["v1_request_ids"])
    output = tmp_path / "v1-output.mp3"
    Path(f"{output}.json").write_text(json.dumps(sidecar_payload), encoding="utf-8")
    clipboard_values: list[str] = []
    clipboard = SimpleNamespace(setText=clipboard_values.append)
    monkeypatch.setattr(QApplication, "clipboard", lambda: clipboard)
    window = TTSWindow()
    qtbot.addWidget(window)
    window.show()
    window.path_entry.setText(str(output))

    window.tts_complete.emit("complete")

    assert window.copy_ids_button.isEnabled()
    parallelism_used = integer(sidecar_payload["parallelism_used"])
    assert window.parallelism_status_label.text().endswith(str(parallelism_used))
    qtbot.mouseClick(window.copy_ids_button, Qt.MouseButton.LeftButton)
    assert clipboard_values == ["\n".join(request_ids)]
