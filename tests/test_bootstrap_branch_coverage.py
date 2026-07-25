from __future__ import annotations

import io
import logging
import runpy

import pytest

import openai_tts_gui.main as bootstrap


def test_configure_logging_writes_bounded_file_handler_once(monkeypatch, capsys):
    given_root = logging.getLogger()
    given_handlers = given_root.handlers[:]
    given_level = given_root.level
    given_log_stream = io.StringIO()
    handler_calls = 0

    def bounded_handler(*_arguments, **_keywords):
        nonlocal handler_calls
        handler_calls += 1
        return logging.StreamHandler(given_log_stream)

    monkeypatch.setattr(bootstrap, "_LOGGING_CONFIGURED", False)
    monkeypatch.setattr(bootstrap, "ensure_directories", lambda: None)
    monkeypatch.setattr(bootstrap, "BoundedRotatingFileHandler", bounded_handler)

    try:
        bootstrap.configure_logging()
        logging.getLogger("bootstrap-coverage").warning("bootstrap-log")
        bootstrap.configure_logging()

        assert "bootstrap-log" in given_log_stream.getvalue()
        assert handler_calls == 1
        assert capsys.readouterr().out == ""
    finally:
        given_root.handlers.clear()
        given_root.handlers.extend(given_handlers)
        given_root.setLevel(given_level)


def test_load_gui_symbols_imports_theme_and_window_types():
    when_symbols = bootstrap._load_gui_symbols()

    assert all(callable(symbol) for symbol in when_symbols)


def test_run_reports_missing_gui_dependency(monkeypatch, capsys):
    monkeypatch.setattr(bootstrap, "configure_logging", lambda: None)

    def missing_gui_symbols():
        raise ModuleNotFoundError("PyQt6")

    monkeypatch.setattr(bootstrap, "_load_gui_symbols", missing_gui_symbols)

    when_result = bootstrap.run(["openai-tts"])

    assert when_result == 1
    assert "GUI requires" in capsys.readouterr().err


def test_run_wires_successful_preflight_and_releases_worker(monkeypatch):
    record = {}

    class Signal:
        def __init__(self):
            self.callbacks = []

        def connect(self, callback):
            self.callbacks.append(callback)

        def emit(self, *arguments):
            for callback in self.callbacks:
                callback(*arguments)

    class FakeApp:
        def __init__(self, arguments):
            record["arguments"] = arguments
            record["app"] = self
            self.exit_code = 0

        def exit(self, code):
            self.exit_code = code

        def exec(self):
            return self.exit_code

    class FakeWindow:
        def show(self):
            record["shown"] = True

    class FakeMessageBox:
        @staticmethod
        def critical(*_arguments):
            record["dialog"] = True

    class FakeWorker:
        def __init__(self, parent):
            record["worker_parent"] = parent
            self.preflight_finished = Signal()
            self.finished = Signal()

        def deleteLater(self):
            record["deleted"] = True

        def start(self):
            self.preflight_finished.emit(True, "ready")
            self.finished.emit()

    monkeypatch.setattr(bootstrap, "configure_logging", lambda: None)
    monkeypatch.setattr(
        bootstrap,
        "_load_gui_symbols",
        lambda: (
            FakeApp,
            FakeMessageBox,
            lambda app: record.update(themed=app),
            FakeWindow,
            FakeWorker,
        ),
    )

    when_result = bootstrap.run(["openai-tts", "--test"])

    assert when_result == 0
    assert record["shown"] is True
    assert record["worker_parent"] is record["app"]
    assert record["deleted"] is True
    assert record["app"]._ffmpeg_preflight_worker is None


def test_run_exits_when_ffmpeg_preflight_fails(monkeypatch):
    record = {}

    class Signal:
        def __init__(self):
            self.callback = None

        def connect(self, callback):
            self.callback = callback

        def emit(self, *arguments):
            assert self.callback is not None
            self.callback(*arguments)

    class FakeApp:
        def __init__(self, _arguments):
            self.exit_code = 0

        def exit(self, code):
            self.exit_code = code

        def exec(self):
            return self.exit_code

    class FakeWindow:
        def show(self):
            pass

    class FakeMessageBox:
        @staticmethod
        def critical(*arguments):
            record["dialog"] = arguments

    class FakeWorker:
        def __init__(self, _parent):
            self.preflight_finished = Signal()
            self.finished = Signal()

        def deleteLater(self):
            pass

        def start(self):
            self.preflight_finished.emit(False, "ffmpeg unavailable")
            self.finished.emit()

    monkeypatch.setattr(bootstrap, "configure_logging", lambda: None)
    monkeypatch.setattr(
        bootstrap,
        "_load_gui_symbols",
        lambda: (FakeApp, FakeMessageBox, lambda _app: None, FakeWindow, FakeWorker),
    )

    when_result = bootstrap.run(["openai-tts"])

    assert when_result == 2
    assert record["dialog"][2] == "ffmpeg unavailable"


def test_run_translates_qapplication_setup_failure(monkeypatch):
    class BrokenApp:
        def __init__(self, _arguments):
            raise OSError

    monkeypatch.setattr(bootstrap, "configure_logging", lambda: None)
    monkeypatch.setattr(
        bootstrap,
        "_load_gui_symbols",
        lambda: (BrokenApp, None, None, None, None),
    )

    when_result = bootstrap.run(["openai-tts"])

    assert when_result == 1


def test_main_exits_with_run_result(monkeypatch):
    monkeypatch.setattr(bootstrap, "run", lambda: 3)

    with pytest.raises(SystemExit) as when_exit:
        bootstrap.main()

    assert when_exit.value.code == 3


def test_module_entrypoint_invokes_main(monkeypatch):
    called = []
    monkeypatch.setattr(bootstrap, "main", lambda: called.append(True))

    runpy.run_module("openai_tts_gui.__main__", run_name="__main__")

    assert called == [True]
