@echo off
setlocal
cd /d "%~dp0.." || exit /b 1
REM Profile CPU with a deterministic, network-free workload.
if not exist profiling mkdir profiling
pyinstrument -o profiling\split_concat_profile.html tools\profile_split_concat.py
echo Pyinstrument report: profiling\split_concat_profile.html
endlocal
