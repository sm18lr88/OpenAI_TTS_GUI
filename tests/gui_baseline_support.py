from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from gui_focus_baseline import FocusBaseline, capture_focus_baseline
from gui_lifecycle import GuiLifecycleError, release_qt_resources
from PyQt6 import sip
from PyQt6.QtCore import Qt, QThread
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QWidget

from openai_tts_gui.config.theme import apply_fusion_dark
from openai_tts_gui.gui import TTSWindow

STABLE_OBJECT_NAMES = (
    "textEdit",
    "controlsSplitter",
    "voiceSettingsGroup",
    "modelCombo",
    "voiceCombo",
    "speedInput",
    "formatCombo",
    "instructionsGroup",
    "managePresetsButton",
    "instructionsEdit",
    "outputRunGroup",
    "pathEntry",
    "selectPathButton",
    "progressBar",
    "primaryButton",
    "cancelButton",
    "copyRequestIdsButton",
    "parallelismStatusLabel",
    "aboutText",
    "openLogButton",
    "aboutBackButton",
)
ACCEPTED_PREEXISTING_CLIPPING: frozenset[str] = frozenset({"modelCombo", "statusBarMessage:Ready"})
QTEST_WINDOW_ACTIVE = "qWaitForWindowActive"


class GuiBaselineError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class WidgetBaseline:
    object_name: str
    actual_bounds: tuple[int, int, int, int]
    required_minimum_bounds: tuple[int, int]
    minimum_size_hint: tuple[int, int]
    enabled: bool
    visible: bool
    within_parent_bounds: bool


@dataclass(frozen=True, slots=True)
class ThreadTeardownBaseline:
    object_name: str
    deleted: bool
    running: bool


@dataclass(frozen=True, slots=True)
class StatusMessageBaseline:
    text: str
    status_bar_bounds: tuple[int, int, int, int]
    text_bounds: tuple[int, int, int, int]
    vertical_overflow: bool


@dataclass(frozen=True, slots=True)
class TeardownBaseline:
    remaining_top_level_widgets: tuple[str, ...]
    thread_states: tuple[ThreadTeardownBaseline, ...]
    application_released: bool


@dataclass(frozen=True, slots=True)
class GuiBaseline:
    scale_factor: str
    screenshot_size: tuple[int, int]
    focus: FocusBaseline
    status_message: StatusMessageBaseline
    teardown: TeardownBaseline
    widgets: tuple[WidgetBaseline, ...]
    pre_existing_clipping: tuple[str, ...]
    unaccounted_clipping: tuple[str, ...]


def _widget_baseline(widget: QWidget) -> WidgetBaseline:
    geometry = widget.geometry()
    hint = widget.minimumSizeHint()
    minimum = widget.minimumSize()
    parent = widget.parentWidget()
    return WidgetBaseline(
        object_name=widget.objectName(),
        actual_bounds=(geometry.x(), geometry.y(), geometry.width(), geometry.height()),
        required_minimum_bounds=(
            max(hint.width(), minimum.width(), 0),
            max(hint.height(), minimum.height(), 0),
        ),
        minimum_size_hint=(hint.width(), hint.height()),
        enabled=widget.isEnabled(),
        visible=widget.isVisible(),
        within_parent_bounds=parent is None or parent.contentsRect().contains(geometry),
    )


def _required_widgets(window: TTSWindow) -> tuple[QWidget, ...]:
    return tuple(_required_widget(window, object_name) for object_name in STABLE_OBJECT_NAMES)


def _required_widget(window: TTSWindow, object_name: str) -> QWidget:
    widget = window.findChild(QWidget, object_name)
    if widget is None:
        raise GuiBaselineError(f"Missing stable GUI object name: {object_name}")
    return widget


def _status_message_baseline(window: TTSWindow) -> StatusMessageBaseline:
    status_bar = window.statusBar()
    content_rect = status_bar.contentsRect()
    text_rect = status_bar.fontMetrics().boundingRect(
        content_rect,
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        status_bar.currentMessage(),
    )
    return StatusMessageBaseline(
        text=status_bar.currentMessage(),
        status_bar_bounds=content_rect.getRect(),
        text_bounds=(text_rect.x(), text_rect.y(), text_rect.width(), text_rect.height()),
        vertical_overflow=not content_rect.contains(text_rect),
    )


def capture_gui_baseline(
    screenshot_path: Path, *, inject_primary_undersize: bool = False
) -> GuiBaseline:
    app = QApplication(["gui-baseline"])
    window = None
    pixmap = None
    threads: tuple[tuple[str, QThread], ...] = ()
    remaining_top_level_widgets: tuple[str, ...] = ()
    try:
        apply_fusion_dark(app)
        window = TTSWindow()
        window.resize(700, 500)
        window.show()
        if app.platformName() != "offscreen":
            window.activateWindow()
            window_handle = window.windowHandle()
            if window_handle is None or not getattr(QTest, QTEST_WINDOW_ACTIVE)(
                window_handle, 1000
            ):
                raise GuiBaselineError("Native GUI baseline window did not become active")
        app.processEvents()
        if inject_primary_undersize:
            window.create_button.setFixedWidth(1)
            app.processEvents()
        focus = capture_focus_baseline(window, app, STABLE_OBJECT_NAMES)
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        pixmap = window.grab()
        if not pixmap.save(str(screenshot_path)):
            raise GuiBaselineError(f"Unable to save screenshot: {screenshot_path}")
        screenshot_size = (pixmap.width(), pixmap.height())
        widgets = tuple(_widget_baseline(widget) for widget in _required_widgets(window))
        status_message = _status_message_baseline(window)
        status_clipping = ("statusBarMessage:Ready",) if status_message.vertical_overflow else ()
        clipping = (
            tuple(
                baseline.object_name
                for baseline in (_widget_baseline(widget) for widget in _required_widgets(window))
                if baseline.visible
                and (
                    baseline.actual_bounds[2] < baseline.required_minimum_bounds[0]
                    or baseline.actual_bounds[3] < baseline.required_minimum_bounds[1]
                )
            )
            + status_clipping
        )
        threads = tuple((thread.objectName(), thread) for thread in window.findChildren(QThread))
    finally:
        primary_error = sys.exception()
        pixmap = None
        if primary_error is None:
            try:
                remaining_top_level_widgets = release_qt_resources(
                    app, window, tuple(thread for _, thread in threads)
                )
            finally:
                window = None
                app = None
        else:
            try:
                release_qt_resources(app, window, tuple(thread for _, thread in threads))
            except GuiLifecycleError as cleanup_error:
                primary_error.add_note(f"Qt cleanup failed: {cleanup_error}")
            window = None
            app = None
    application_released = QApplication.instance() is None
    if not application_released:
        raise GuiBaselineError("QApplication remained alive after baseline teardown")
    thread_states = tuple(
        ThreadTeardownBaseline(
            name,
            sip.isdeleted(thread),
            not sip.isdeleted(thread) and thread.isRunning(),
        )
        for name, thread in threads
    )
    return GuiBaseline(
        scale_factor=os.environ.get("QT_SCALE_FACTOR", ""),
        screenshot_size=screenshot_size,
        focus=focus,
        status_message=status_message,
        teardown=TeardownBaseline(
            remaining_top_level_widgets=remaining_top_level_widgets,
            thread_states=thread_states,
            application_released=application_released,
        ),
        widgets=widgets,
        pre_existing_clipping=tuple(
            name for name in clipping if name in ACCEPTED_PREEXISTING_CLIPPING
        ),
        unaccounted_clipping=tuple(
            name for name in clipping if name not in ACCEPTED_PREEXISTING_CLIPPING
        ),
    )


def write_gui_baseline(
    json_path: Path, screenshot_path: Path, *, inject_primary_undersize: bool = False
) -> GuiBaseline:
    baseline = capture_gui_baseline(
        screenshot_path, inject_primary_undersize=inject_primary_undersize
    )
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(asdict(baseline), indent=2), encoding="utf-8")
    return baseline


if __name__ == "__main__":
    from gui_baseline_capture import main

    raise SystemExit(main())
