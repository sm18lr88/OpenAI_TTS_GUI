# PyInstaller spec for OpenAI TTS GUI (native PyQt6 only)
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

PROJECT_ROOT = Path(SPECPATH).parents[1]

# Restrict to the Qt modules we actually use to avoid pulling in optional
# plugins that emit missing-DLL warnings on Windows runners.
REQUIRED_QT_MODULES = [
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
]

hidden = REQUIRED_QT_MODULES + [
    "openai_tts_gui.config",
    "openai_tts_gui.config.settings",
    "openai_tts_gui.config.theme",
    "openai_tts_gui.config._palette",
    "openai_tts_gui.config._stylesheet",
    "openai_tts_gui.core",
    "openai_tts_gui.core.text",
    "openai_tts_gui.core.audio",
    "openai_tts_gui.core.ffmpeg",
    "openai_tts_gui.core.metadata",
    "openai_tts_gui.tts",
    "openai_tts_gui.tts._service",
    "openai_tts_gui.tts._execution",
    "openai_tts_gui.tts._contracts",
    "openai_tts_gui.tts._provider",
    "openai_tts_gui.tts._run_state",
    "openai_tts_gui.tts._retry",
    "openai_tts_gui.tts._scheduler",
    "openai_tts_gui.tts._publication",
    "openai_tts_gui.tts._publication_plan",
    "openai_tts_gui.tts._publication_types",
    "openai_tts_gui.tts._destination",
    "openai_tts_gui.tts._lease",
    "openai_tts_gui.tts._outcomes",
    "openai_tts_gui.keystore",
    "openai_tts_gui.presets",
    "openai_tts_gui.gui",
    "openai_tts_gui.gui.main_window",
    "openai_tts_gui.gui.dialogs",
    "openai_tts_gui.gui.workers",
    "openai_tts_gui.gui._layout",
    "openai_tts_gui.gui._text_panel",
    "openai_tts_gui.gui._controls_panel",
    "openai_tts_gui.gui._about_page",
    "openai_tts_gui.gui._menu",
    "openai_tts_gui.gui._result_actions",
    "openai_tts_gui.gui._run_wiring",
    "openai_tts_gui.gui._window_settings",
    "openai_tts_gui.errors",
]
# Only bundle the Qt plugin categories required for widget apps; avoid heavy/optional
# plugins (3D, multimedia, QML) that trigger missing-DLL warnings on CI.
datas = collect_data_files(
    "PyQt6",
    includes=[
        "Qt6/plugins/platforms/*",
        "Qt6/plugins/styles/*",
        "Qt6/plugins/iconengines/*",
        "Qt6/plugins/imageformats/qgif.dll",
        "Qt6/plugins/imageformats/qico.dll",
        "Qt6/plugins/imageformats/qjpeg.dll",
        "Qt6/plugins/imageformats/qsvg.dll",
        "Qt6/plugins/imageformats/qwebp.dll",
    ],
)

block_cipher = None

a = Analysis(
    [str(PROJECT_ROOT / "scripts" / "pyinstaller_entry.py")],
    pathex=[str(PROJECT_ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    excludes=[],
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    name="openai_tts_bin",
    console=False,
    manifest=str(PROJECT_ROOT / "packaging" / "windows" / "openai_tts_bin.exe.manifest"),
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="OpenAI-TTS")
