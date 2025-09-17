@echo off
setlocal
REM Run unit + integration tests with a minimum coverage gate (80%)
if not exist reports mkdir reports
if not exist htmlcov mkdir htmlcov
python -m pytest -q ^
  -k "not perf and not bench" ^
  --timeout=60 ^
  -n auto --dist=loadgroup ^
  --cov=. ^
  --cov-report=term-missing:skip-covered ^
  --cov-report=html:htmlcov ^
  --cov-fail-under=80 ^
  --junitxml=reports\junit.xml
echo Tests complete. Coverage HTML at htmlcov\index.html
endlocal
