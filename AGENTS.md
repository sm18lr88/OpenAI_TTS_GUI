# Agent Notes

## Project Overview
PyQt6 desktop app + CLI for OpenAI TTS. Converts text to speech via OpenAI API with chunking, retry, and ffmpeg concatenation.

## Module Map
```
src/openai_tts_gui/
  config/      settings (pure Python) + theme (Qt)
  core/        text chunking, audio concat, ffmpeg, sidecar metadata
  tts/         TTSService (pure Python, no Qt dependency)
  keystore/    API key storage (keyring + encrypted file)
  presets/     Instruction preset JSON persistence
  gui/         PyQt6 UI (main_window, dialogs, workers, _layout)
  errors.py    Domain error hierarchy
  cli.py       CLI entry point
  main.py      GUI entry point
```

## Build / Test / Lint
```bash
uv sync                    # install
uv run pytest              # test (uses .pytest_tmp for temp files)
uv run ruff check          # lint
uv run ruff format .       # format
uv run ty check            # type check
```

## Core Conventions
- Import ONLY from `__init__.py` interfaces, never from `_`-prefixed internal files
- `config/settings.py` has ZERO Qt imports — CLI path must stay Qt-free
- `core/`, `tts/_service.py`, `keystore/`, `presets/` have ZERO Qt imports
- Architecture boundary tests in `tests/test_architecture.py` enforce this via AST
- Domain errors from `errors.py` — never raise bare Exception/ValueError
- QSS theming at QApplication level (Fusion + dark palette) — no per-widget styles
- Long operations via `gui/workers.py` QThread — never block main UI thread

## NEVER Rules
- NEVER change `OBFUSCATION_KEY` value in `config/settings.py`
- NEVER change keyring service name `"OpenAI_TTS_GUI"` or username `"OPENAI_API_KEY"`
- NEVER change environment variable names: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `TTS_PARALLELISM`, `TTS_STREAM_FORMAT`
- NEVER import PyQt6 in core/, tts/_service.py, keystore/, presets/, or config/settings.py
- NEVER add `utils.py`, `helpers.py`, or `common.py` catch-all files

## Temp Isolation
Tests use `.pytest_tmp` for temp files (see `tests/conftest.py`). Avoids locked OS temp dirs on Windows.

## Networking
Core unit tests are network-free. TTS API is mocked. Profiling helpers are offline.

## Packaging
PyInstaller spec (`openai_tts.spec`) includes hidden imports for all subpackages.
