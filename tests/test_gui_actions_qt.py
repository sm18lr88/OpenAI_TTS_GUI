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
        "openai_tts_gui.gui.QFileDialog.getSaveFileName", lambda *a, **k: (target, "")
    )
    # Ensure format is wav so extension isn't changed
    idx = w.format_combo.findText("wav")
    w.format_combo.setCurrentIndex(idx)
    w.select_save_path()
    assert w.path_entry.text().endswith("chosen.wav")
    w.close()
