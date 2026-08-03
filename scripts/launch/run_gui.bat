@echo off
setlocal

for %%I in ("%~dp0..\..") do cd /d "%%~fI" || exit /b 1

where uv >nul 2>nul
if errorlevel 1 (
    echo uv is required but was not found on PATH.
    echo Install: https://docs.astral.sh/uv/getting-started/installation/
    exit /b 1
)

uv run python -m openai_tts_gui %*
endlocal
