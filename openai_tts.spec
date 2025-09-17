# PyInstaller spec for OpenAI TTS GUI (native PyQt6 only)
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hidden = collect_submodules("PyQt6")
datas = collect_data_files("PyQt6")

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    excludes=[
        "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineQuick", "PyQt6.QtWebView",
        "PyQt6.QtQml", "PyQt6.QtQuick", "PyQt6.QtQuick3D", "PyQt6.QtQmlXmlListModel",
        "PyQt6.Qt3DCore", "PyQt6.Qt3DRender", "PyQt6.Qt3DInput", "PyQt6.Qt3DAnimation",
        "PyQt6.QtDesigner", "PyQt6.QtHelp", "PyQt6.QtTest", "PyQt6.QtPdf", "PyQt6.QtPdfWidgets",
        "PyQt6.QtNfc", "PyQt6.QtBluetooth", "PyQt6.QtSerialPort", "PyQt6.QtOpenGL",
        "PyQt6.QtSvg", "PyQt6.QtSvgWidgets", "PyQt6.QtRemoteObjects", "PyQt6.QtSensors",
    ],
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(pyz, a.scripts, name="openai_tts_bin", console=False) # avoid name clash with COLLECT output dir
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="OpenAI-TTS")
