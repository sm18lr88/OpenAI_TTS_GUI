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
    hookspath=[]
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(pyz, a.scripts, name="OpenAI-TTS", console=False)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="OpenAI-TTS")
