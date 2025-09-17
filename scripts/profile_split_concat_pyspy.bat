@echo off
setlocal
REM Sampling profile via py-spy; produces a flamegraph SVG
if not exist profiling mkdir profiling
py-spy record -o profiling\split_concat_profile.svg -- python tools\profile_split_concat.py
echo py-spy flamegraph written to profiling\split_concat_profile.svg
endlocal
