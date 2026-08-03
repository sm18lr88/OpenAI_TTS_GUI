@echo off
setlocal
REM Run all tests with coverage, parallel workers, a timeout, and JUnit and HTML reports.
if not exist reports mkdir reports
if not exist htmlcov mkdir htmlcov
REM Use xdist for parallel workers. pytest-cov combines coverage across workers.
python -m pytest -q ^
  --maxfail=1 ^
  --timeout=60 ^
  -n auto --dist=loadgroup ^
  -k "not perf and not bench" ^
  --cov=. ^
  --cov-report=term-missing:skip-covered ^
  --cov-report=html:htmlcov ^
  --junitxml=reports\junit.xml
echo Tests complete. Coverage HTML report: htmlcov\index.html
endlocal
