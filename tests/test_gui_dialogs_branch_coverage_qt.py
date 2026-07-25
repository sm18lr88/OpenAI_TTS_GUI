from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox

from openai_tts_gui.gui.dialogs import PresetDialog


def _dialog(qtbot, monkeypatch, presets: dict[str, str]) -> PresetDialog:
    monkeypatch.setattr("openai_tts_gui.gui.dialogs.load_presets", lambda: presets.copy())
    dialog = PresetDialog("current instructions")
    qtbot.addWidget(dialog)
    dialog.show()
    return dialog


def test_selection_state_and_load_action_emit_selected_preset(qtbot, monkeypatch) -> None:
    dialog = _dialog(qtbot, monkeypatch, {"Zulu": "z", "alpha": "a"})

    names: list[str] = []
    for index in range(2):
        item = dialog.preset_list.item(index)
        assert item is not None
        names.append(item.text())
    assert names == ["alpha", "Zulu"]
    assert not dialog.load_button.isEnabled()
    dialog.preset_list.setCurrentRow(0)
    assert dialog.load_button.isEnabled()
    with qtbot.waitSignal(dialog.preset_selected, timeout=1_000) as result:
        qtbot.mouseClick(dialog.load_button, Qt.MouseButton.LeftButton)

    assert result.args == ["a"]
    assert dialog.result() == dialog.DialogCode.Accepted


def test_load_without_selection_displays_warning(qtbot, monkeypatch) -> None:
    dialog = _dialog(qtbot, monkeypatch, {})
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "openai_tts_gui.gui.dialogs.QMessageBox.warning",
        lambda _parent, title, message: warnings.append((title, message)),
    )

    dialog.load_selected()

    assert warnings == [("No Selection", "Please select a preset to load.")]


@pytest.mark.parametrize(
    ("response", "expected_names", "expected_notices"),
    [
        (("", True), ["saved"], [("Invalid Name", "Preset name cannot be empty.")]),
        (("saved", False), ["saved"], []),
    ],
)
def test_save_current_rejects_empty_or_cancelled_names(
    qtbot, monkeypatch, response, expected_names, expected_notices
) -> None:
    dialog = _dialog(qtbot, monkeypatch, {"saved": "old"})
    notices: list[tuple[str, str]] = []
    monkeypatch.setattr("openai_tts_gui.gui.dialogs.QInputDialog.getText", lambda *_args: response)
    monkeypatch.setattr(
        "openai_tts_gui.gui.dialogs.QMessageBox.warning",
        lambda _parent, title, message: notices.append((title, message)),
    )

    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)

    assert sorted(dialog._presets) == expected_names
    assert notices == expected_notices


def test_save_current_handles_overwrite_rejection_success_and_failure(qtbot, monkeypatch) -> None:
    dialog = _dialog(qtbot, monkeypatch, {"saved": "old"})
    records: list[dict[str, str]] = []
    notices: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "openai_tts_gui.gui.dialogs.QInputDialog.getText", lambda *_args: ("saved", True)
    )
    monkeypatch.setattr(
        "openai_tts_gui.gui.dialogs.QMessageBox.question",
        lambda *_args: QMessageBox.StandardButton.No,
    )
    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)

    monkeypatch.setattr(
        "openai_tts_gui.gui.dialogs.QMessageBox.question",
        lambda *_args: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        "openai_tts_gui.gui.dialogs.save_presets",
        lambda presets: records.append(presets.copy()) or True,
    )
    monkeypatch.setattr(
        "openai_tts_gui.gui.dialogs.QMessageBox.information",
        lambda _parent, title, message: notices.append((title, message)),
    )
    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)

    monkeypatch.setattr("openai_tts_gui.gui.dialogs.save_presets", lambda _presets: False)
    monkeypatch.setattr(
        "openai_tts_gui.gui.dialogs.QMessageBox.critical",
        lambda _parent, title, message: notices.append((title, message)),
    )
    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)

    assert records == [{"saved": "current instructions"}]
    assert notices == [
        ("Preset Saved", "Preset 'saved' saved."),
        ("Error", "Failed to save presets file."),
    ]


def test_delete_action_handles_selection_confirmation_and_write_outcomes(
    qtbot, monkeypatch
) -> None:
    dialog = _dialog(qtbot, monkeypatch, {"keep": "one", "remove": "two"})
    notices: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "openai_tts_gui.gui.dialogs.QMessageBox.warning",
        lambda _parent, title, message: notices.append((title, message)),
    )
    dialog.delete_selected()
    dialog.preset_list.setCurrentRow(1)
    monkeypatch.setattr(
        "openai_tts_gui.gui.dialogs.QMessageBox.question",
        lambda *_args: QMessageBox.StandardButton.No,
    )
    qtbot.mouseClick(dialog.delete_button, Qt.MouseButton.LeftButton)

    monkeypatch.setattr(
        "openai_tts_gui.gui.dialogs.QMessageBox.question",
        lambda *_args: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr("openai_tts_gui.gui.dialogs.save_presets", lambda _presets: False)
    monkeypatch.setattr(
        "openai_tts_gui.gui.dialogs.QMessageBox.critical",
        lambda _parent, title, message: notices.append((title, message)),
    )
    qtbot.mouseClick(dialog.delete_button, Qt.MouseButton.LeftButton)

    assert notices == [
        ("No Selection", "Please select a preset to delete."),
        ("Error", "Failed to save presets file after deletion."),
    ]
    assert "remove" not in dialog._presets


def test_delete_selected_persists_and_refreshes_list(qtbot, monkeypatch) -> None:
    dialog = _dialog(qtbot, monkeypatch, {"remove": "two"})
    persisted: list[dict[str, str]] = []
    monkeypatch.setattr(
        "openai_tts_gui.gui.dialogs.QMessageBox.question",
        lambda *_args: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        "openai_tts_gui.gui.dialogs.save_presets",
        lambda presets: persisted.append(presets.copy()) or True,
    )
    dialog.preset_list.setCurrentRow(0)

    qtbot.mouseClick(dialog.delete_button, Qt.MouseButton.LeftButton)

    assert persisted == [{}]
    assert dialog.preset_list.count() == 1


def test_new_preset_and_stale_list_selection_cover_non_membership_paths(qtbot, monkeypatch) -> None:
    dialog = _dialog(qtbot, monkeypatch, {})
    saved: list[dict[str, str]] = []
    monkeypatch.setattr(
        "openai_tts_gui.gui.dialogs.QInputDialog.getText", lambda *_args: ("new", True)
    )
    monkeypatch.setattr(
        "openai_tts_gui.gui.dialogs.save_presets",
        lambda presets: saved.append(presets.copy()) or True,
    )
    monkeypatch.setattr("openai_tts_gui.gui.dialogs.QMessageBox.information", lambda *_args: None)
    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)

    dialog.preset_list.addItem("stale")
    dialog.preset_list.setCurrentRow(0)
    monkeypatch.setattr(
        "openai_tts_gui.gui.dialogs.QMessageBox.question",
        lambda *_args: QMessageBox.StandardButton.Yes,
    )
    dialog.delete_selected()

    assert saved == [{"new": "current instructions"}]
