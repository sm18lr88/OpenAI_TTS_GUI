@echo off
setlocal
REM Fast path: single-process, no xdist, unit-heavy (skips perf/bench)
python -m pytest -q ^
  -k "not perf and not bench" ^
  --timeout=60 ^
  --cov=. ^
  --cov-report=term-missing:skip-covered
echo Unit tests done.
endlocal
