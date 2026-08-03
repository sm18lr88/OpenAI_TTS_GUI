# Architecture

> A desktop GUI and CLI that generate speech audio from text through OpenAI's TTS API.

## Module Map

```
src/openai_tts_gui/
  config/      → Application settings (pure Python) and Qt theme definitions
  core/        → Text chunking, audio concatenation, ffmpeg operations, sidecar metadata
  tts/         → TTS service (pure Python, no Qt) — chunk scheduling, service-owned retry/backoff, ordered finalization
  keystore/    → API key storage — OS keyring, encrypted file fallback, env var
  presets/     → Instruction preset persistence (JSON file)
  gui/         → PyQt6 UI — main window, dialogs, layout, Qt thread worker
  errors.py    → Domain error hierarchy (TTSError base)
  cli.py       → CLI entry point using TTSService directly with model/voice/format/speed flags
  main.py      → GUI entry point — QApplication bootstrap, logging, theme
```

## Module Relationships

```
gui/ ──→ tts/_service ──→ core/ (text, audio, metadata, ffmpeg)
gui/ ──→ keystore/
gui/ ──→ presets/
gui/ ──→ config/settings + config/theme
cli  ──→ tts/_service ──→ core/
cli  ──→ keystore/
cli  ──→ config/settings (NO Qt)
```

- `config/settings` has zero Qt imports and is safe for the CLI path.
- `config/theme` requires PyQt6 and is only imported by gui/.
- `core/` has zero Qt imports and contains pure Python logic.
- `tts/_service` has zero Qt imports, is pure Python, and uses callbacks.
- `tts/_service` owns the OpenAI retry policy for synthesis runs and disables SDK retries for this path.
- `gui/workers` wraps TTSService in a QThread for a non-blocking UI.
- `keystore/` and `presets/` are standalone and only depend on config/settings.

Import only from `__init__.py` interfaces. Internal files prefixed with `_`.

## Data Flow

```
[User] → [TTSWindow (gui/)] → signal → [TTSWorker (QThread)]
                                              ↓
                                      [TTSService (tts/)]
                                          ↓         ↓
                                [OpenAI API]   [core/audio → ffmpeg]
                                                     ↓
                                            [output.mp3 + sidecar.json]
```

During multi-chunk runs, `TTSService` keeps manifest order separate from completion order. Parallel workers can finish out of order. It finalizes concat and sidecar `request_meta` after every expected chunk index has one successful result.

The service coordinates rate limiting within a single run. A `429` response can reduce the active worker cap and impose a shared cooldown. Retry delays prefer `retry-after-ms`, then `retry-after`, then exponential fallback. Failed or cancelled runs do not emit success sidecars or final audio outputs.

## How to Run

```bash
uv sync                          # Install dependencies
uv run pytest                    # Run all tests
uv run pytest tests/test_smoke.py # Single test file
uv run ruff check                # Lint
uv run ruff format --check .     # Format check
uv run ty check                  # Type check
uv run pyinstaller --noconfirm packaging/pyinstaller/openai_tts.spec # Build Windows app bundle
python -m openai_tts_gui         # Launch GUI
openai-tts --in f.txt --out o.mp3 # CLI
openai-tts --help                  # CLI options and supported TTS choices
```

The CLI provides the same core synthesis controls as the GUI. These controls include the model,
voice, output format, speed, optional instructions, and retained chunk files. The CLI remains
Qt-free because it uses `config/settings`, `keystore`, and `TTSService` directly.

## Conventions

**Public interfaces:** Every package has `__init__.py` with `__all__`.

**Internal files:** Prefixed with `_` (e.g., `_service.py`, `_storage.py`, `_layout.py`).

**Tests:** In `tests/` directory. Import from public interfaces.

**Config:** `config/settings.py` (pure Python) vs `config/theme.py` (Qt). Never import theme from non-GUI code.

**Errors:** Use domain errors from `errors.py`, never raise bare `Exception` or `ValueError`.

**Threading (PyQt6 rule):** Never block the main thread. Long operations go through `gui/workers.py` → `TTSService`.

**Theming (PyQt6 rule):** QSS applied at `QApplication` level via `apply_fusion_dark()`. No per-widget inline styles.

## Boundary Enforcement

Architecture boundary tests in `tests/test_architecture.py` use AST analysis to verify that
core/, tts/_service, keystore/, presets/, and config/settings have zero PyQt6 imports.

## Decisions

ADRs in `docs/decisions/`. Read before modifying module boundaries.

## Adding a New Module

1. Create directory under `src/openai_tts_gui/`
2. Add `__init__.py` with `__all__`
3. Prefix internal files with `_`
4. Add boundary test in `tests/test_architecture.py` if Qt-free
5. Update this module map
