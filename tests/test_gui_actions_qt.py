import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QLabel, QMessageBox

from openai_tts_gui import config
from openai_tts_gui.gui import TTSWindow


class _DummySignal:
    def __init__(self):
        self.slot = None

    def connect(self, slot):
        self.slot = slot


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
    assert w.parallelism_label.text() == "Parallel workers: 0 (max: 3)"
    w.close()

    w2 = TTSWindow()
    qtbot.addWidget(w2)
    w2.show()
    assert w2.parallelism_label.text() == "Parallel workers: 0 (max: 3)"
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


def test_about_page_includes_appreciation_link(qtbot):
    w = TTSWindow()
    qtbot.addWidget(w)
    w.show()

    w._show_about_page()
    html = w.about_text.toHtml()
    text = w.about_text.toPlainText()

    assert "Show appreciation" in text
    assert "https://paypal.me/LeoRiera" in html
    assert "appreciation" in html
    w.close()


def test_tts_success_notification_includes_appreciation_link_and_preserves_open_folder(
    qtbot, monkeypatch
):
    w = TTSWindow()
    qtbot.addWidget(w)
    w.show()
    w.path_entry.setText("C:/tmp/output.mp3")
    w._dialogs_suppressed = lambda: False
    messages: list[tuple[str, str, str, bool]] = []
    opened: list[str] = []

    w._notify = lambda title, message, level="info", *, rich_text=False: messages.append(
        (title, message, level, rich_text)
    )
    monkeypatch.setattr(
        "openai_tts_gui.gui.main_window.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    w._open_containing_folder = opened.append

    w._handle_tts_success("TTS audio saved successfully.")

    assert messages == [
        (
            "TTS Complete",
            'TTS audio saved successfully.\n\nShow <a href="https://paypal.me/LeoRiera">appreciation</a>.',
            "info",
            True,
        )
    ]
    assert opened == ["C:/tmp/output.mp3"]
    w.close()


def test_tts_completion_message_escapes_generated_text(qtbot):
    w = TTSWindow()
    qtbot.addWidget(w)
    w.show()

    message = w._completion_message("Saved <danger> & done.")

    assert "Saved &lt;danger&gt; &amp; done." in message
    assert '<a href="https://paypal.me/LeoRiera">appreciation</a>' in message
    w.close()


def test_notification_rich_text_links_open_externally(qtbot, monkeypatch):
    w = TTSWindow()
    qtbot.addWidget(w)
    w.show()
    w._dialogs_suppressed = lambda: False
    captured: list[list[bool]] = []

    def fake_exec(box):
        captured.append([label.openExternalLinks() for label in box.findChildren(QLabel)])
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr("openai_tts_gui.gui.main_window.QMessageBox.exec", fake_exec)

    w._notify("TTS Complete", w._completion_message("Saved."), rich_text=True)

    assert captured
    assert any(captured[0])
    w.close()


def test_parallelism_status_label_updates(qtbot):
    w = TTSWindow()
    qtbot.addWidget(w)
    w.show()
    w._handle_parallelism_update(2, 3)
    assert w.parallelism_status_label.text() == "Active chunk workers: 2/3"
    w.close()


def test_stats_line_shows_model_aware_price_estimate(qtbot):
    w = TTSWindow()
    qtbot.addWidget(w)
    w.show()

    w.text_edit.setPlainText("x" * 1000)
    w.update_counts()
    assert w.chunk_count_label.text() == "Chunks: 1"
    assert w.price_estimate_label.text() == "Estimated price: $0.02"

    hd_index = w.model_combo.findText("tts-1-hd")
    w.model_combo.setCurrentIndex(hd_index)
    assert w.price_estimate_label.text() == "Estimated price: $0.03"

    gpt_index = w.model_combo.findText(config.GPT_4O_MINI_TTS_MODEL)
    w.model_combo.setCurrentIndex(gpt_index)
    assert w.price_estimate_label.text() == "Estimated price: ~$0.02"
    w.close()


def test_parallelism_label_uses_requested_current_and_max_format(qtbot):
    w = TTSWindow()
    qtbot.addWidget(w)
    w.show()

    w._parallelism = 5
    w.text_edit.setPlainText("x" * (config.MAX_CHUNK_SIZE + 1))
    w.update_counts()

    assert w.parallelism_label.text() == "Parallel workers: 2 (max: 5)"
    w.close()


def test_about_page_explains_chunk_limit_outside_stats_line(qtbot):
    w = TTSWindow()
    qtbot.addWidget(w)
    w.show()

    assert "max 4096 chars" not in w.chunk_count_label.text()
    w._show_about_page()
    assert f"chunks of up to {config.MAX_CHUNK_SIZE} characters" in w.about_text.toPlainText()
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


def test_close_event_waits_for_slow_tts_cancellation(qtbot, monkeypatch):
    class SlowWorker:
        def __init__(self):
            self.cancelled = False
            self.finished = _DummySignal()

        def isRunning(self):
            return True

        def cancel(self):
            self.cancelled = True

        def wait(self, _timeout):
            return False

    w = TTSWindow()
    qtbot.addWidget(w)
    w.show()
    worker = SlowWorker()
    w.tts_processor = worker
    monkeypatch.setattr(
        "openai_tts_gui.gui.main_window.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    event = QCloseEvent()
    w.closeEvent(event)

    assert worker.cancelled is True
    assert event.isAccepted() is False
    assert w._close_after_tts_cancel is True
    assert worker.finished.slot == w.close
    w.tts_processor = None
    w.close()
