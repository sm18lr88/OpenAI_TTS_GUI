@echo off
setlocal
cd /d "%~dp0.." || exit /b 1
REM Create a sampling profile with py-spy. Write an SVG flame graph.
if not exist profiling mkdir profiling
py-spy record -o profiling\split_concat_profile.svg -- python tools\profile_split_concat.py
echo py-spy flame graph: profiling\split_concat_profile.svg
endlocal
