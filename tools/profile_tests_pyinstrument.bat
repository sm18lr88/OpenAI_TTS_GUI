@echo off
setlocal
cd /d "%~dp0.." || exit /b 1
REM Profile the entire pytest run with pyinstrument and write an HTML report
if not exist profiling mkdir profiling
pyinstrument -o profiling\pytest_profile.html -m pytest -q
echo Pyinstrument report written to profiling\pytest_profile.html
endlocal
