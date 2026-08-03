# ADR-001: Architecture Restructure

## Status
Accepted

## Context
The original codebase used a flat layout with 8 files in one directory. It had several coupling problems:
- `config.py` imported `QColor` at module level. This forced a Qt dependency on the CLI path.
- `utils.py` had 497 lines and mixed 5+ concerns: text processing, API key crypto, ffmpeg ops, presets, and sidecar metadata.
- `TTSProcessor` inherited from `QThread`. This coupled core TTS logic to PyQt6.
- `gui.py` had 729 lines and contained both dialogs and the main window.
- There were no public interfaces. `__init__.py` was empty.
- There were no domain-specific errors.

## Decision
Use feature-based modules. Follow the software-architecture skill:
- Split `config.py` into `config/settings.py` (pure Python) + `config/theme.py` (Qt)
- Extract `utils.py` into `core/` (text, audio, ffmpeg, metadata), `keystore/`, `presets/`
- Create `TTSService` as pure Python class with callback-based progress reporting
- Wrap `TTSService` in `TTSWorker(QThread)` for the GUI path
- Add domain error hierarchy in `errors.py`
- Define `__all__` in every package `__init__.py`
- Split `gui.py` into `gui/main_window.py`, `gui/dialogs.py`, `gui/workers.py`, `gui/_layout.py`

## Consequences
- The CLI path no longer requires PyQt6 to be installed.
- The TTS logic is testable without Qt mocking.
- Architecture boundary tests use AST analysis to enforce Qt-free core modules.
- The `utils.py` re-export facade maintains backward compatibility.
- Existing keyring service names, obfuscation key, and presets format remain exactly preserved.
