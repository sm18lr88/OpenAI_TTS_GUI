@echo off
setlocal
cd /d "%~dp0.." || exit /b 1
REM Profile the full pytest run with pyinstrument. Write an HTML report.
if not exist profiling mkdir profiling
pyinstrument -o profiling\pytest_profile.html -m pytest -q
echo Pyinstrument report: profiling\pytest_profile.html
endlocal
