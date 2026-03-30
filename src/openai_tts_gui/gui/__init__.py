__all__ = [
    "PresetDialog",
    "TTSWindow",
    "TTSWorker",
]


def __getattr__(name: str):
    if name == "PresetDialog":
        from .dialogs import PresetDialog

        return PresetDialog
    if name == "TTSWindow":
        from .main_window import TTSWindow

        return TTSWindow
    if name == "TTSWorker":
        from .workers import TTSWorker

        return TTSWorker
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
