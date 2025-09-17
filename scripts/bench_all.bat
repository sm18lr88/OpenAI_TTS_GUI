@echo off
setlocal
REM Run performance benchmarks only; autosave and JSON export
if not exist reports mkdir reports
python -m pytest -q -k "perf or bench" ^
  --benchmark-only ^
  --benchmark-autosave ^
  --benchmark-min-rounds=5 ^
  --benchmark-columns=min,mean,stddev,ops ^
  --benchmark-json=reports\bench.json
echo Benchmarks complete. Results saved under .benchmarks and reports\bench.json
endlocal
