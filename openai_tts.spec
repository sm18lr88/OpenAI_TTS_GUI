# PyInstaller spec for OpenAI TTS GUI (native PyQt6 only)
from PyInstaller.utils.hooks import collect_data_files

# Restrict to the Qt modules we actually use to avoid pulling in optional
# plugins that emit missing-DLL warnings on Windows runners.
REQUIRED_QT_MODULES = [
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
]

hidden = REQUIRED_QT_MODULES
# Only bundle the Qt plugin categories required for widget apps; avoid heavy/optional
# plugins (3D, multimedia, QML) that trigger missing-DLL warnings on CI.
datas = collect_data_files(
    "PyQt6",
    includes=[
        "Qt6/plugins/platforms/*",
        "Qt6/plugins/styles/*",
        "Qt6/plugins/iconengines/*",
        "Qt6/plugins/imageformats/*",
        "Qt6/translations/*",
    ],
)

block_cipher = None

a = Analysis(
    ["src/openai_tts_gui/main.py"],
    pathex=["src"],
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
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="OpenAI-TTS")
