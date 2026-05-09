import pytest

pytest.importorskip("PyQt6")

from openai_tts_gui.gui import TTSWindow
from openai_tts_gui.gui.dialogs import PresetDialog


def test_window_boots(qtbot):
    w = TTSWindow()
    qtbot.addWidget(w)
    w.show()
    assert w.isVisible()
    w.close()


def test_window_can_grab_pixmap(qtbot, tmp_path):
    w = TTSWindow()
    qtbot.addWidget(w)
    w.show()
    pix = w.grab()
    assert pix.width() > 0 and pix.height() > 0
    # ensure saving works
    out = tmp_path / "snap.png"
    pix.save(str(out))
    assert out.exists() and out.stat().st_size > 0
    w.close()


def test_main_window_widgets_have_stable_object_names(qtbot):
    w = TTSWindow()
    qtbot.addWidget(w)
    w.show()

    widgets = [
        w.text_edit,
        w.model_combo,
        w.voice_combo,
        w.speed_input,
        w.format_combo,
        w.manage_presets_button,
        w.instructions_edit,
        w.path_entry,
        w.select_path_button,
        w.progress_bar,
        w.create_button,
        w.cancel_button,
        w.copy_ids_button,
        w.parallelism_status_label,
        w.about_text,
        w.open_log_button,
        w.about_back_button,
    ]

    assert all(widget.objectName() for widget in widgets)
    w.close()


def test_preset_dialog_widgets_have_stable_object_names(qtbot):
    dialog = PresetDialog("test instructions")
    qtbot.addWidget(dialog)
    dialog.show()

    widgets = [
        dialog.preset_list,
        dialog.load_button,
        dialog.save_button,
        dialog.delete_button,
    ]

    assert all(widget.objectName() for widget in widgets)
    dialog.close()
