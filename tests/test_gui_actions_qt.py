import pytest

pytest.importorskip("PyQt6")

from openai_tts_gui import config
from openai_tts_gui.gui import TTSWindow


def test_update_instructions_toggle(qtbot):
    w = TTSWindow()
    qtbot.addWidget(w)
    w.show()
    # Default is dark theme + a default model (first in list)
    # Switch to gpt-4o-mini-tts to enable instructions
    idx = w.model_combo.findText(config.GPT_4O_MINI_TTS_MODEL)
    if idx >= 0:
        w.model_combo.setCurrentIndex(idx)
        assert w.instructions_edit.isEnabled()
    # Switch back to "tts-1"
    idx2 = w.model_combo.findText("tts-1")
    if idx2 >= 0:
        w.model_combo.setCurrentIndex(idx2)
        assert not w.instructions_edit.isEnabled()
    w.close()


def test_path_extension_updates(qtbot, tmp_path):
    w = TTSWindow()
    qtbot.addWidget(w)
    w.show()
    # Seed a path
    p = tmp_path / "out.mp3"
    w.path_entry.setText(str(p))
    # Change format to wav and ensure extension updates
    idx = w.format_combo.findText("wav")
    w.format_combo.setCurrentIndex(idx)
    assert w.path_entry.text().endswith(".wav")
    w.close()


def test_select_save_path_mocked_dialog(qtbot, monkeypatch, tmp_path):
    w = TTSWindow()
    qtbot.addWidget(w)
    w.show()
    # Mock the dialog to return a specific path
    target = str(tmp_path / "chosen.wav")
    monkeypatch.setattr(
        "openai_tts_gui.gui.main_window.QFileDialog.getSaveFileName", lambda *a, **k: (target, "")
    )
    # Ensure format is wav so extension isn't changed
    idx = w.format_combo.findText("wav")
    w.format_combo.setCurrentIndex(idx)
    w.select_save_path()
    assert w.path_entry.text().endswith("chosen.wav")
    w.close()


def test_parallelism_setting_persists_in_app(qtbot, monkeypatch, tmp_path):
    settings_path = tmp_path / "app_settings.json"
    monkeypatch.setattr(config, "APP_SETTINGS_FILE", str(settings_path))
    monkeypatch.setattr("openai_tts_gui.config.settings.APP_SETTINGS_FILE", str(settings_path))
    monkeypatch.setattr(
        "openai_tts_gui.gui.main_window.QInputDialog.getInt", lambda *a, **k: (3, True)
    )

    w = TTSWindow()
    qtbot.addWidget(w)
    w.show()
    w._notify = lambda *args, **kwargs: None
    w._set_parallelism()
    assert "up to 3" in w.parallelism_label.text()
    w.close()

    w2 = TTSWindow()
    qtbot.addWidget(w2)
    w2.show()
    assert "up to 3" in w2.parallelism_label.text()
    assert w2._parallelism_warning_shown is True
    w2.close()


def test_about_page_shows_current_version(qtbot):
    w = TTSWindow()
    qtbot.addWidget(w)
    w.show()
    w._show_about_page()
    assert config.APP_VERSION in w.about_text.toHtml()
    assert "Parallel Processing Risks" in w.about_text.toPlainText()
    w.close()


def test_parallelism_status_label_updates(qtbot):
    w = TTSWindow()
    qtbot.addWidget(w)
    w.show()
    w._handle_parallelism_update(2, 3)
    assert w.parallelism_status_label.text() == "Active chunk workers: 2/3"
    w.close()


def test_parallelism_warning_is_only_shown_once(qtbot, monkeypatch, tmp_path):
    settings_path = tmp_path / "app_settings.json"
    monkeypatch.setattr(config, "APP_SETTINGS_FILE", str(settings_path))
    monkeypatch.setattr("openai_tts_gui.config.settings.APP_SETTINGS_FILE", str(settings_path))

    selected_values = iter([(3, True), (4, True)])
    monkeypatch.setattr(
        "openai_tts_gui.gui.main_window.QInputDialog.getInt",
        lambda *a, **k: next(selected_values),
    )

    messages: list[tuple[str, str, str]] = []

    w = TTSWindow()
    qtbot.addWidget(w)
    w.show()
    w._notify = lambda title, message, level="info": messages.append((title, message, level))

    w._set_parallelism()
    w._set_parallelism()

    assert messages[0][0] == "Parallel Processing Risk"
    assert messages[0][2] == "warning"
    assert messages[1][0] == "Parallelism Updated"
    assert (
        sum(1 for title, _message, _level in messages if title == "Parallel Processing Risk") == 1
    )
    w.close()
