import pytest

pytest.importorskip("PyQt6")

from openai_tts_gui import config
from openai_tts_gui.gui import TTSWindow


def test_update_instructions_toggle(qtbot):
    # Given: a visible TTS window with available models.
    window = TTSWindow()
    qtbot.addWidget(window)
    window.show()

    # When: the selected model changes between instruction-capable and tts-1 models.
    gpt_index = window.model_combo.findText(config.GPT_4O_MINI_TTS_MODEL)
    if gpt_index >= 0:
        window.model_combo.setCurrentIndex(gpt_index)

        # Then: instructions are enabled for the instruction-capable model.
        assert window.instructions_edit.isEnabled()

    tts_index = window.model_combo.findText("tts-1")
    if tts_index >= 0:
        window.model_combo.setCurrentIndex(tts_index)

        # Then: instructions are disabled for tts-1.
        assert not window.instructions_edit.isEnabled()
    window.close()


def test_path_extension_updates(qtbot, tmp_path):
    # Given: a visible window with an MP3 output path.
    window = TTSWindow()
    qtbot.addWidget(window)
    window.show()
    path = tmp_path / "out.mp3"
    window.path_entry.setText(str(path))

    # When: the output format changes to WAV.
    wav_index = window.format_combo.findText("wav")
    window.format_combo.setCurrentIndex(wav_index)

    # Then: the output path extension follows the selected format.
    assert window.path_entry.text().endswith(".wav")
    window.close()


def test_select_save_path_mocked_dialog(qtbot, monkeypatch, tmp_path):
    # Given: a visible window and a save dialog that selects a WAV file.
    window = TTSWindow()
    qtbot.addWidget(window)
    window.show()
    target = str(tmp_path / "chosen.wav")
    monkeypatch.setattr(
        "openai_tts_gui.gui._window_settings.QFileDialog.getSaveFileName",
        lambda *_args, **_kwargs: (target, ""),
    )
    wav_index = window.format_combo.findText("wav")
    window.format_combo.setCurrentIndex(wav_index)

    # When: the save-path action runs.
    window.select_save_path()

    # Then: the selected path is retained without a format rewrite.
    assert window.path_entry.text().endswith("chosen.wav")
    window.close()


def test_parallelism_setting_persists_in_app(qtbot, monkeypatch, tmp_path):
    # Given: isolated application settings and a confirmed parallelism choice.
    settings_path = tmp_path / "app_settings.json"
    monkeypatch.setattr(config, "APP_SETTINGS_FILE", str(settings_path))
    monkeypatch.setattr("openai_tts_gui.config.settings.APP_SETTINGS_FILE", str(settings_path))
    monkeypatch.setattr(
        "openai_tts_gui.gui._window_settings.QInputDialog.getInt",
        lambda *_args, **_kwargs: (3, True),
    )

    window = TTSWindow()
    qtbot.addWidget(window)
    window.show()
    window._notify = lambda *_args, **_kwargs: None

    # When: the user sets parallelism and opens a second window.
    window._set_parallelism()

    # Then: the active window reflects the chosen capacity.
    assert window.parallelism_label.text() == "Parallel workers: 0 (max: 3)"
    window.close()

    restored_window = TTSWindow()
    qtbot.addWidget(restored_window)
    restored_window.show()

    # Then: the saved worker limit and warning state return.
    assert restored_window.parallelism_label.text() == "Parallel workers: 0 (max: 3)"
    assert restored_window._parallelism_warning_shown is True
    restored_window.close()


def test_parallelism_status_label_updates(qtbot):
    # Given: a visible TTS window.
    window = TTSWindow()
    qtbot.addWidget(window)
    window.show()

    # When: parallel chunk-worker activity is reported.
    window._handle_parallelism_update(2, 3)

    # Then: the status label reports active and total workers.
    assert window.parallelism_status_label.text() == "Active chunk workers: 2/3"
    window.close()


def test_stats_line_shows_model_aware_price_estimate(qtbot):
    # Given: a visible window containing one thousand characters.
    window = TTSWindow()
    qtbot.addWidget(window)
    window.show()
    window.text_edit.setPlainText("x" * 1000)

    # When: counts are updated and models change.
    window.update_counts()

    # Then: the default model reports its chunk count and price estimate.
    assert window.chunk_count_label.text() == "Chunks: 1"
    assert window.price_estimate_label.text() == "Estimated price: $0.02"

    hd_index = window.model_combo.findText("tts-1-hd")
    window.model_combo.setCurrentIndex(hd_index)

    # Then: the HD model reports its higher estimate.
    assert window.price_estimate_label.text() == "Estimated price: $0.03"

    gpt_index = window.model_combo.findText(config.GPT_4O_MINI_TTS_MODEL)
    window.model_combo.setCurrentIndex(gpt_index)

    # Then: the GPT model reports its approximate estimate.
    assert window.price_estimate_label.text() == "Estimated price: ~$0.02"
    window.close()


def test_parallelism_label_uses_requested_current_and_max_format(qtbot):
    # Given: a visible window with a requested capacity above the chunk count.
    window = TTSWindow()
    qtbot.addWidget(window)
    window.show()
    window._parallelism = 5
    window.text_edit.setPlainText("x" * (config.MAX_CHUNK_SIZE + 1))

    # When: the chunk count is refreshed.
    window.update_counts()

    # Then: the label shows active workers and the requested maximum.
    assert window.parallelism_label.text() == "Parallel workers: 2 (max: 5)"
    window.close()


def test_parallelism_warning_is_only_shown_once(qtbot, monkeypatch, tmp_path):
    # Given: isolated settings and two confirmed parallelism choices.
    settings_path = tmp_path / "app_settings.json"
    monkeypatch.setattr(config, "APP_SETTINGS_FILE", str(settings_path))
    monkeypatch.setattr("openai_tts_gui.config.settings.APP_SETTINGS_FILE", str(settings_path))
    selected_values = iter([(3, True), (4, True)])
    monkeypatch.setattr(
        "openai_tts_gui.gui._window_settings.QInputDialog.getInt",
        lambda *_args, **_kwargs: next(selected_values),
    )
    messages: list[tuple[str, str, str]] = []

    window = TTSWindow()
    qtbot.addWidget(window)
    window.show()
    window._notify = lambda title, message, level="info": messages.append((title, message, level))

    # When: parallelism is changed twice in the same window.
    window._set_parallelism()
    window._set_parallelism()

    # Then: the risk warning appears once and the second action reports an update.
    assert messages[0][0] == "Parallel Processing Risk"
    assert messages[0][2] == "warning"
    assert messages[1][0] == "Parallelism Updated"
    assert (
        sum(1 for title, _message, _level in messages if title == "Parallel Processing Risk") == 1
    )
    window.close()
