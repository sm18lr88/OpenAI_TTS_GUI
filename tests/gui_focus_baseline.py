from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QWidget

from openai_tts_gui.gui import TTSWindow

QTEST_KEY_CLICK = "keyClick"


class GuiFocusBaselineError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class FocusBaseline:
    tab_changes_focus: bool
    keyboard_initial_owner: str
    keyboard_tab_owner: str
    keyboard_shift_tab_owner: str
    focus_chain_next_named_owner: str
    focus_chain_previous_named_owner: str


def capture_focus_baseline(
    window: TTSWindow, app: QApplication, stable_object_names: tuple[str, ...]
) -> FocusBaseline:
    window.text_edit.setFocus()
    app.processEvents()
    initial = _focused_widget(app)
    getattr(QTest, QTEST_KEY_CLICK)(initial, Qt.Key.Key_Tab)
    app.processEvents()
    after_tab = _focused_widget(app)
    getattr(QTest, QTEST_KEY_CLICK)(after_tab, Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier)
    app.processEvents()
    after_shift_tab = _focused_widget(app)
    return FocusBaseline(
        tab_changes_focus=window.text_edit.tabChangesFocus(),
        keyboard_initial_owner=initial.objectName(),
        keyboard_tab_owner=after_tab.objectName(),
        keyboard_shift_tab_owner=after_shift_tab.objectName(),
        focus_chain_next_named_owner=_named_focus_chain_owner(
            window.text_edit, stable_object_names, True
        ),
        focus_chain_previous_named_owner=_named_focus_chain_owner(
            window.text_edit, stable_object_names, False
        ),
    )


def _focused_widget(app: QApplication) -> QWidget:
    widget = app.focusWidget()
    if widget is None:
        raise GuiFocusBaselineError("QTest key sequence lost focus")
    return widget


def _named_focus_chain_owner(
    widget: QWidget, stable_object_names: tuple[str, ...], forward: bool
) -> str:
    current = widget
    for _ in range(64):
        next_widget = current.nextInFocusChain() if forward else current.previousInFocusChain()
        if next_widget is None:
            raise GuiFocusBaselineError("Focus chain ended unexpectedly")
        current = next_widget
        if (
            current.objectName() in stable_object_names
            and current.isVisible()
            and current.isEnabled()
            and current.focusPolicy() != Qt.FocusPolicy.NoFocus
        ):
            return current.objectName()
    raise GuiFocusBaselineError("No named focus-chain neighbor was found")
