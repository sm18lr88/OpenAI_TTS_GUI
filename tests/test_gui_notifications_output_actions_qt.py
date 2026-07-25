import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QLabel, QMessageBox

from openai_tts_gui import config
from openai_tts_gui.gui import TTSWindow


def test_about_page_shows_current_version(qtbot):
    # Given: a visible TTS window.
    window = TTSWindow()
    qtbot.addWidget(window)
    window.show()

    # When: the about page is displayed.
    window._show_about_page()

    # Then: the current version and parallelism guidance are visible.
    assert config.APP_VERSION in window.about_text.toHtml()
    assert "Parallel Processing Risks" in window.about_text.toPlainText()
    window.close()


def test_about_page_includes_appreciation_link(qtbot):
    # Given: a visible TTS window.
    window = TTSWindow()
    qtbot.addWidget(window)
    window.show()

    # When: the about page is displayed.
    window._show_about_page()
    html = window.about_text.toHtml()
    text = window.about_text.toPlainText()

    # Then: the appreciation action is represented in plain and rich text.
    assert "Show appreciation" in text
    assert "https://paypal.me/LeoRiera" in html
    assert "appreciation" in html
    window.close()


def test_about_page_explains_chunk_limit_outside_stats_line(qtbot):
    # Given: a visible window with the normal compact stats line.
    window = TTSWindow()
    qtbot.addWidget(window)
    window.show()

    # When: the about page is displayed.
    assert "max 4096 chars" not in window.chunk_count_label.text()
    window._show_about_page()

    # Then: the detailed chunk limit is documented on the about page.
    assert f"chunks of up to {config.MAX_CHUNK_SIZE} characters" in window.about_text.toPlainText()
    window.close()


def test_tts_success_notification_includes_appreciation_link_and_preserves_open_folder(
    qtbot, monkeypatch
):
    # Given: a visible window, an output path, and affirmative folder-open confirmation.
    window = TTSWindow()
    qtbot.addWidget(window)
    window.show()
    window.path_entry.setText("C:/tmp/output.mp3")
    window._dialogs_suppressed = lambda: False
    messages: list[tuple[str, str, str, bool]] = []
    opened: list[str] = []
    window._notify = lambda title, message, level="info", *, rich_text=False: messages.append(
        (title, message, level, rich_text)
    )
    monkeypatch.setattr(
        "openai_tts_gui.gui.main_window.QMessageBox.question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    window._open_containing_folder = opened.append

    # When: TTS completion is handled.
    window._handle_tts_success("TTS audio saved successfully.")

    # Then: the rich notification and original output path are preserved.
    assert messages == [
        (
            "TTS Complete",
            'TTS audio saved successfully.\n\nShow <a href="https://paypal.me/LeoRiera">appreciation</a>.',
            "info",
            True,
        )
    ]
    assert opened == ["C:/tmp/output.mp3"]
    window.close()


def test_tts_completion_message_escapes_generated_text(qtbot):
    # Given: a visible TTS window.
    window = TTSWindow()
    qtbot.addWidget(window)
    window.show()

    # When: a completion message is created from generated text containing HTML characters.
    message = window._completion_message("Saved <danger> & done.")

    # Then: generated content is escaped while the appreciation link remains rich text.
    assert "Saved &lt;danger&gt; &amp; done." in message
    assert '<a href="https://paypal.me/LeoRiera">appreciation</a>' in message
    window.close()


def test_notification_rich_text_links_open_externally(qtbot, monkeypatch):
    # Given: a visible window that permits notification dialogs.
    window = TTSWindow()
    qtbot.addWidget(window)
    window.show()
    window._dialogs_suppressed = lambda: False
    captured: list[list[bool]] = []

    def fake_exec(box):
        captured.append([label.openExternalLinks() for label in box.findChildren(QLabel)])
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr("openai_tts_gui.gui.main_window.QMessageBox.exec", fake_exec)

    # When: a rich-text notification is displayed.
    window._notify("TTS Complete", window._completion_message("Saved."), rich_text=True)

    # Then: at least one notification label opens links externally.
    assert captured
    assert any(captured[0])
    window.close()
