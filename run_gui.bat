@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
if not defined SCRIPT_DIR set "SCRIPT_DIR=.\"
cd /d "%SCRIPT_DIR%" || exit /b 1

where uv >nul 2>nul
if errorlevel 1 (
    echo uv is required but was not found in PATH.
    echo Install instructions: https://docs.astral.sh/uv/getting-started/installation/
    exit /b 1
)

if not exist .venv (
    echo Creating uv-managed virtual environment...
    uv venv || exit /b 1
)

echo Syncing dependencies with uv...
uv sync
if errorlevel 1 exit /b 1

set "UV_PY=.venv\Scripts\python.exe"
if not exist "%UV_PY%" (
    echo Expected interpreter not found at %UV_PY%.
    exit /b 1
)

"%UV_PY%" -m openai_tts_gui %*
endlocal
