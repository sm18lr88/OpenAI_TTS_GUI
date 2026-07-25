.PHONY: test-fast test lint coverage install-hooks pmat pmat-gate

test-fast:
	uv run pytest --ignore=tests/integration --ignore=tests/perf -q

test:
	uv run pytest --ignore=tests/perf -q

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run ty check

coverage:
	uv run pytest --ignore=tests/perf --cov=openai_tts_gui --cov-branch --cov-report=term-missing --cov-report=json:coverage.json
	uv run scripts/check_coverage_thresholds.py coverage.json --min-statements 90 --min-branches 90

install-hooks:
	uv run pre-commit install

pmat:
	pmat analyze complexity --path src --timeout 120
	pmat analyze tdg --path src
	pmat analyze dead-code --path src --timeout 120

pmat-gate:
	pmat analyze complexity --path src --max-cyclomatic 15 --max-cognitive 125 --fail-on-violation --timeout 120
