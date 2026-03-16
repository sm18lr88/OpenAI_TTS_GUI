# ADR-001: Architecture Restructure

## Status
Accepted

## Context
The original codebase had a flat layout (8 files in one directory) with several coupling problems:
- `config.py` imported `QColor` at module level, forcing Qt dependency on the CLI path
- `utils.py` (497 lines) mixed 5+ concerns: text processing, API key crypto, ffmpeg ops, presets, sidecar metadata
- `TTSProcessor` inherited from `QThread`, coupling core TTS logic to PyQt6
- `gui.py` (729 lines) contained both dialogs and the main window
- No public interfaces (`__init__.py` was empty)
- No domain-specific errors

## Decision
Restructure into feature-based modules following the software-architecture skill:
- Split `config.py` into `config/settings.py` (pure Python) + `config/theme.py` (Qt)
- Extract `utils.py` into `core/` (text, audio, ffmpeg, metadata), `keystore/`, `presets/`
- Create `TTSService` as pure Python class with callback-based progress reporting
- Wrap `TTSService` in `TTSWorker(QThread)` for the GUI path
- Add domain error hierarchy in `errors.py`
- Define `__all__` in every package `__init__.py`
- Split `gui.py` into `gui/main_window.py`, `gui/dialogs.py`, `gui/workers.py`, `gui/_layout.py`

## Consequences
- CLI path no longer requires PyQt6 installed
- TTS logic is testable without Qt mocking
- Architecture boundary tests enforce Qt-free core modules via AST analysis
- Backward compat maintained via `utils.py` re-export facade
- Existing keyring service names, obfuscation key, presets format preserved exactly
