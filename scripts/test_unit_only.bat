@echo off
setlocal
REM Run mostly unit tests in one process. Skip perf and bench tests.
python -m pytest -q ^
  -k "not perf and not bench" ^
  --timeout=60 ^
  --cov=. ^
  --cov-report=term-missing:skip-covered
echo Unit tests complete.
endlocal
