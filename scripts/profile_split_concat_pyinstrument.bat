@echo off
setlocal
REM Profile CPU on a deterministic, network-free workload
if not exist profiling mkdir profiling
pyinstrument -o profiling\split_concat_profile.html tools\profile_split_concat.py
echo Pyinstrument report written to profiling\split_concat_profile.html
endlocal
