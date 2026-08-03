@echo off
setlocal
cd /d "%~dp0.." || exit /b 1
REM Run only performance benchmarks. Save results automatically as JSON.
if not exist reports mkdir reports
python -m pytest -q -k "perf or bench" ^
  --benchmark-only ^
  --benchmark-autosave ^
  --benchmark-min-rounds=5 ^
  --benchmark-columns=min,mean,stddev,ops ^
  --benchmark-json=reports\bench.json
echo Benchmarks complete. Results: .benchmarks and reports\bench.json
endlocal
