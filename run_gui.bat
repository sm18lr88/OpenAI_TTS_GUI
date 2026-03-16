@echo off
setlocal

cd /d "%~dp0" || exit /b 1

where uv >nul 2>nul
if errorlevel 1 (
    echo uv is required but was not found in PATH.
    echo Install: https://docs.astral.sh/uv/getting-started/installation/
    exit /b 1
)

uv run python -m openai_tts_gui %*
endlocal
