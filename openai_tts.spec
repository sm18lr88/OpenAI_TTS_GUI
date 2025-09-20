# PyInstaller spec for OpenAI TTS GUI (native PyQt6 only)
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

EXCLUDED_QT_MODULES = (
    "PyQt6.QtWebEngineCore",
    "PyQt6.QtWebEngineQuick",
    "PyQt6.QtWebView",
    "PyQt6.QtQml",
    "PyQt6.QtQuick",
    "PyQt6.QtQuick3D",
    "PyQt6.QtQmlXmlListModel",
    "PyQt6.Qt3DCore",
    "PyQt6.Qt3DRender",
    "PyQt6.Qt3DInput",
    "PyQt6.Qt3DAnimation",
    "PyQt6.QtDesigner",
    "PyQt6.QtHelp",
    "PyQt6.QtTest",
    "PyQt6.QtPdf",
    "PyQt6.QtPdfWidgets",
    "PyQt6.QtNfc",
    "PyQt6.QtBluetooth",
    "PyQt6.QtSerialPort",
    "PyQt6.QtOpenGL",
    "PyQt6.QtSvg",
    "PyQt6.QtSvgWidgets",
    "PyQt6.QtRemoteObjects",
    "PyQt6.QtSensors",
)


def _is_excluded(module_name: str) -> bool:
    """Return True when the PyQt6 submodule is intentionally left out."""
    return any(
        module_name == excluded or module_name.startswith(excluded + ".")
        for excluded in EXCLUDED_QT_MODULES
    )


hidden = [
    name for name in collect_submodules("PyQt6")
    if not _is_excluded(name)
]

datas = collect_data_files("PyQt6")

block_cipher = None

a = Analysis(
    ["src/openai_tts_gui/main.py"],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    excludes=list(EXCLUDED_QT_MODULES),
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    name="openai_tts_bin",
    console=False,
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="OpenAI-TTS")
