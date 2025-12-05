# Agent Notes

This project ships tests and tooling tuned for automated agents as well as humans. Key points:

- **Temp isolation:** Tests and helper scripts keep all temporary files under `.pytest_tmp` to avoid locked-down OS temp directories (common on Windows). See `tests/conftest.py`.
- **Tooling:** Use `uv` for reproducible environments. Lint with `uv run ruff check`, type-check with `uv run ty check`, and run tests with `uv run pytest`.
- **CI:** GitHub Actions workflow (`.github/workflows/ci.yml`) runs lint, types, tests on Windows/macOS/Linux and builds a PyInstaller artifact on Windows.
- **Networking:** Core unit tests are network-free; the TTS API is faked/mocked. Profiling helpers (`tools/profile_split_concat.py`) are also offline.
- **Resource usage:** TTS chunking streams to disk (`stream_format="audio"`) and records request IDs in sidecars. Parallel chunk generation is gated by `TTS_PARALLELISM`.
- **Packaging:** PyInstaller spec includes PyQt6 and OpenAI modules by default (`openai_tts.spec`).

If you need to add new tests or scripts, prefer repo-local temp dirs and avoid network or GPU assumptions. Refer to `README.md` for developer commands and platform notes.***
