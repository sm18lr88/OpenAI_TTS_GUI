import builtins
import importlib
import sys


def test_non_gui_imports_do_not_require_pyqt6_or_openai(monkeypatch):
    original_import = builtins.__import__
    saved_modules = {
        module_name: module
        for module_name, module in sys.modules.items()
        if module_name.startswith("openai_tts_gui")
    }

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.startswith("PyQt6") or name == "openai":
            raise AssertionError(f"Unexpected optional dependency import: {name}")
        return original_import(name, globals, locals, fromlist, level)

    try:
        for module_name in list(sys.modules):
            if module_name.startswith("openai_tts_gui"):
                sys.modules.pop(module_name, None)

        monkeypatch.setattr(builtins, "__import__", guarded_import)

        importlib.import_module("openai_tts_gui")
        importlib.import_module("openai_tts_gui.cli")
        importlib.import_module("openai_tts_gui.config")
        importlib.import_module("openai_tts_gui.main")
        importlib.import_module("openai_tts_gui.utils")
    finally:
        for module_name in list(sys.modules):
            if module_name.startswith("openai_tts_gui"):
                sys.modules.pop(module_name, None)
        sys.modules.update(saved_modules)


def test_top_level_import_defers_nonessential_core_modules():
    saved_modules = {
        module_name: module
        for module_name, module in sys.modules.items()
        if module_name.startswith("openai_tts_gui")
    }

    try:
        for module_name in list(sys.modules):
            if module_name.startswith("openai_tts_gui"):
                sys.modules.pop(module_name, None)

        package = importlib.import_module("openai_tts_gui")

        assert "openai_tts_gui.core.audio" not in sys.modules
        assert "openai_tts_gui.core.metadata" not in sys.modules

        split_text = package.split_text
        assert callable(split_text)
        assert "openai_tts_gui.core.text" in sys.modules
        assert "openai_tts_gui.core.audio" not in sys.modules
        assert "openai_tts_gui.core.metadata" not in sys.modules
    finally:
        for module_name in list(sys.modules):
            if module_name.startswith("openai_tts_gui"):
                sys.modules.pop(module_name, None)
        sys.modules.update(saved_modules)


def test_main_window_import_defers_openai_client():
    saved_modules = {
        module_name: module
        for module_name, module in sys.modules.items()
        if module_name.startswith(("openai_tts_gui", "openai"))
    }

    try:
        for module_name in list(sys.modules):
            if module_name.startswith(("openai_tts_gui", "openai")):
                sys.modules.pop(module_name, None)

        importlib.import_module("openai_tts_gui.gui.main_window")

        assert "openai" not in sys.modules
        assert "openai_tts_gui.gui.workers" not in sys.modules
    finally:
        for module_name in list(sys.modules):
            if module_name.startswith(("openai_tts_gui", "openai")):
                sys.modules.pop(module_name, None)
        sys.modules.update(saved_modules)
