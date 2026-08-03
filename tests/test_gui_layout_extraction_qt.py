from __future__ import annotations

import pytest
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget

from openai_tts_gui.gui import TTSWindow, _layout
from openai_tts_gui.gui._menu import build_menu


class LayoutFixture(TTSWindow):
    def __init__(self) -> None:
        QMainWindow.__init__(self)

    def closeEvent(self, event: QCloseEvent | None) -> None:
        if event is not None:
            event.accept()

    def _copy_request_ids(self) -> None:
        pass

    def _open_containing_folder(self, _path: str) -> None:
        pass

    def _show_main_page(self) -> None:
        pass

    def _set_parallelism(self) -> None:
        pass

    def _load_api_key_from_file(self) -> None:
        pass

    def _set_custom_api_key(self) -> None:
        pass

    def _show_about_page(self) -> None:
        pass


def _require_named_widget(window: QWidget, object_name: str) -> QWidget:
    widgets = window.findChildren(QWidget, object_name)
    if not widgets:
        raise AssertionError(f"Missing stable GUI object name: {object_name}")
    return widgets[0]


def test_text_panel_preserves_pre_extraction_editor_placeholder_and_defaults(qtbot) -> None:
    # Given: a window built through the layout builder.
    window = TTSWindow()
    qtbot.addWidget(window)
    window.show()
    QApplication.processEvents()

    # When: the initial text panel is inspected through its real widgets.
    text_edit = window.text_edit

    # Then: the shipped placeholder and initial counter defaults remain unchanged.
    assert text_edit.placeholderText() == "Enter the text you want to convert to speech..."
    assert text_edit.minimumHeight() == 280
    assert window.char_count_label.text() == "Character Count: 0"
    assert window.chunk_count_label.text() == "Chunks: 0"
    assert window.price_estimate_label.text() == "Estimated price: $0.00"


@pytest.mark.parametrize(
    ("builder_name", "object_name"),
    (
        ("build_text_panel", "textEdit"),
        ("build_controls_panel", "controlsSplitter"),
        ("build_about_page", "aboutText"),
    ),
)
def test_layout_smoke_reports_missing_named_widget_when_panel_builder_is_omitted(
    qtbot, monkeypatch: pytest.MonkeyPatch, builder_name: str, object_name: str
) -> None:
    # Given: a composition fixture with one panel builder omitted.
    window = LayoutFixture()
    qtbot.addWidget(window)
    monkeypatch.setattr(_layout, builder_name, lambda _window: QWidget())

    # When: the central layout composition is constructed and processed by Qt.
    stack = _layout.build_central_widget(window)
    window.setCentralWidget(stack)
    window.show()
    QApplication.processEvents()

    # Then: the smoke test finds the missing panel by its object name.
    with pytest.raises(AssertionError, match=f"Missing stable GUI object name: {object_name}"):
        _require_named_widget(window, object_name)


def test_menu_smoke_reports_missing_action_when_menu_builder_is_omitted(
    qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a composition fixture with the menu builder omitted.
    window = LayoutFixture()
    qtbot.addWidget(window)
    monkeypatch.setattr(_layout, "build_menu", lambda _window: None)

    # When: the retained menu facade is invoked and Qt processes the window.
    _layout.build_menubar(window)
    QApplication.processEvents()

    # Then: the smoke test reports the missing action instead of passing.
    with pytest.raises(AttributeError, match="retain_files_action"):
        _ = window.retain_files_action


def test_menu_builder_returns_without_a_menubar(qtbot, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a window whose platform menu bar is unavailable.
    window = LayoutFixture()
    qtbot.addWidget(window)
    monkeypatch.setattr(LayoutFixture, "menuBar", lambda _window: None)

    # When: the extracted menu builder is invoked.
    build_menu(window)

    # Then: it returns without creating actions against a missing menu bar.
    assert not hasattr(window, "retain_files_action")
