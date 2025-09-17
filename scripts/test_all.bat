@echo off
setlocal
REM Run full test suite with coverage, parallelization, timeout and JUnit/HTML reports
if not exist reports mkdir reports
if not exist htmlcov mkdir htmlcov
REM Use xdist to parallelize; coverage combines across workers (pytest-cov supports xdist)
python -m pytest -q ^
  --maxfail=1 ^
  --timeout=60 ^
  -n auto --dist=loadgroup ^
  -k "not perf and not bench" ^
  --cov=. ^
  --cov-report=term-missing:skip-covered ^
  --cov-report=html:htmlcov ^
  --junitxml=reports\junit.xml
echo Tests complete. Coverage HTML at htmlcov\index.html
endlocal
