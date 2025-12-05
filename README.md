# OpenAI TTS GUI

* Easily use high quality, cheap TTS.
* Long text is supported. 

<image src='https://github.com/user-attachments/assets/6a70fa4f-d127-4c9f-bb70-66165e5b5a7b' width='900'>

## Features

- Models: `tts-1`, `tts-1-hd`, `gpt-4o-mini-tts`
- Voices: All standard OpenAI TTS options (alloy, ash, ballad, cedar, coral, echo, fable, marin, onyx, nova, sage, shimmer, verse)
- Format/Speed: MP3, Opus, AAC, FLAC, WAV, PCM; 0.25x-4.0x
- Instructions: Custom voice instructions for `gpt-4o-mini-tts`
- Presets: you can save or load your custom instructions
- Long Text: handled automatically; no character limits
- Feedback: Live character/chunk count for manual cost calculation if desired
- Themes: Dark or Light (native Qt)
- API Key: manually set, or reads from your environment variables
- Retention: retain individual mp3 chunks if desired
- Sidecar: JSON metadata written next to outputs for reproducibility
- CLI: `openai-tts --in text.txt --out out.mp3 --model tts-1`
- Stream-aware: uses `stream_format="audio"` for low-memory downloads; request IDs are recorded in sidecars
- One-click debug: copy request IDs and open log folder from the GUI

## Requirements

- [**Python**](https://www.python.org/downloads/)
- [**ffmpeg**](https://www.ffmpeg.org/download.html)
- [**An OpenAI API key**](https://platform.openai.com/signup)
- Windows users: if your `%TEMP%` is locked down, tests and temp files will be written under `.pytest_tmp`

## Installation

If installation seems too complicated, copy/paste this text into an AI chatbot to help you in the process.

1. **Clone the repository:**
   ```bash
   git clone https://github.com/sm18lr88/OpenAI_TTS_GUI.git
   cd OpenAI_TTS_GUI
   ```

2. **Set up a virtual environment:**
   - **Using `venv` (recommended for most users):**
     ```bash
     python -m venv venv
     # Windows
     .\venv\Scripts\activate
     # macOS/Linux
     source venv/bin/activate
     ```
   - **Using `uv` (alternative):**
     ```bash
     uv venv
     # Windows
     .\venv\Scripts\activate
     # macOS/Linux
     source venv/bin/activate
     ```

3. **Install dependencies:**
   - The dependencies are specified in `pyproject.toml`. Install them using:
     ```bash
     pip install -U openai PyQt6 keyring platformdirs
     ```
   - If using **uv**:
     ```bash
     uv sync
     ```

## Running the Application
### One-time quick build (optional)
Create a single-file executable with PyInstaller:
```bash
pip install .[dev]
pyinstaller --noconfirm openai_tts.spec
```
Artifacts will appear in `dist/`.

1. **Set API Key**:
   - **Option 1**: Set the `OPENAI_API_KEY` environment variable.
   - **Option 2**: Launch the app and use `API Key` -> `Set/Update API Key...` (stored in your OS keyring when available and obfuscated in `api_key.enc`).
   - (Optional) For self-hosted/OpenAI-compatible endpoints, set `OPENAI_BASE_URL` before launch.
2. **Start the GUI:**
   ```bash
   python -m openai_tts_gui
   ```
3. **CLI (headless):**
   ```bash
   openai-tts --in text.txt --out out.mp3 --model tts-1 --voice alloy --format mp3 --speed 1.0 --log-level INFO
   ```
### Optional concurrency
Set `TTS_PARALLELISM` to enable parallel chunk generation (default = 1 / off):
```bash
# Example: use up to 4 concurrent requests
set TTS_PARALLELISM=4   # Windows PowerShell: $env:TTS_PARALLELISM=4
```

### Development & QA
- Style/lint: `uv run ruff check`
- Types: `uv run ty check`
- Tests: `uv run pytest` (uses repo-local `.pytest_tmp` for temp files)
- Build (Windows): `uv run pyinstaller --noconfirm openai_tts.spec`

## Troubleshooting
- **FFmpeg**: Ensure it's on PATH or configured in `config.py`. The app performs a preflight check on startup.
- **Keys**: OS keyring is used when available; `api_key.enc` is a fallback.
- **Logs & Data**: Logs at the path shown in **About**; presets and app data live under the per-user data directory.

## Tips

- **Speed**: Adjustments far from 1.0x may impact quality; try Adobe Audition for speed tweaks, or select the `gpt-4o-mini-tts` model and instruct it to speak faster/slower.
- **Instructions**: check examples at [openai.fm](openai.fm).
- **Security**: `api_key.enc` is obfuscated, not encrypted. Prefer environment variables or OS keyring storage.
- **ffmpeg**: If not found, ensure it’s in PATH or set its path in `config.py`.
- **Logs**: Check `tts_app.log` for errors or details.

## Roadmap

- [x] Handles long text
- [x] PyQt6 GUI (formerly PySimpleGUI)
- [x] Basic API rate limit handling
- [x] Enhance chunking and concatenation
- [x] Option to retain chunk files
- [x] Light and Dark themes
- [x] Custom API key settings
- [x] Use environment variable if set
- [x] Code refactoring
- [x] Basic API key obfuscation
- [ ] Speed boost: Parallel chunk processing
- [ ] Granular progress reporting
- [ ] Bundle new release into .exe
- [ ] Price estimate

## Versions / Notes

- OpenAI Python SDK `==2.9.0`.
- PyQt6 `==6.10.0`.
- Streams audio via `stream_format="audio"` (OpenAI Python v2 default).

## Support

Check `tts_app.log` for issues. Report problems on GitHub. For code help, consult AI models with logs or snippets.
