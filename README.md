# OpenAI TTS GUI

Easily use high quality, cheap TTS.

<image src='https://github.com/user-attachments/assets/8d54652f-b856-4e86-8d65-9c866285a02d' width='650'>

## Features

- Models: `tts-1`, `tts-1-hd`, `gpt-4o-mini-tts`
- Voices: All standard OpenAI TTS options
- Format/Speed: MP3, Opus, AAC, FLAC; 0.25x-4.0x
- Instructions: Custom guidance for `gpt-4o-mini-tts`
- Presets: Save/load instruction sets
- Long Text: Splits and joins via `ffmpeg`
- Feedback: Live character/chunk counts
- Progress: Generation status bar
- Themes: Dark (default) or Light
- API Key: Env var or GUI (obfuscated in `api_key.enc`)
- Errors: Retries and detailed reporting
- Retention: Optional chunk file saving

## Requirements

- **Python**: 3.10 or higher ([Download Python](https://www.python.org/downloads/))
- **ffmpeg**: Must be installed and in PATH ([Download ffmpeg](https://www.ffmpeg.org/download.html))
- **OpenAI API Key**: Obtain from [OpenAI](https://platform.openai.com/signup)

## Installation

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
     pip install openai pyqt6
     ```
   - If using `uv`, you can run:
     ```bash
     uv pip install openai pyqt6
     ```

## Running the Application

1. **Set API Key**:
   - **Option 1**: Set the `OPENAI_API_KEY` environment variable.
   - **Option 2**: Launch the app and use `API Key` -> `Set/Update API Key...` (saves obfuscated in `api_key.enc`).

2. **Start the GUI:**
   ```bash
   python main.py
   ```

## Tips

- **Speed**: Adjustments far from 1.0x may impact quality; use audio software liked Adobe Premiere for high-quality tweaks, or use the instruction model and instruct it to speak faster/slower.
- **Instructions**: Only work with `gpt-4o-mini-tts`; presets simplify reuse.
- **Security**: `api_key.enc` is obfuscated, not encrypted—don’t share it. Prefer environment variables.
- **ffmpeg**: If not found, ensure it’s in PATH or set its path in `config.py`.
- **Logs**: Check `tts_app.log` for errors or details.

## Roadmap

- [x] Handle 4096 character limit
- [x] Upgrade to PyQt6
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
- [ ] Price tracking

## Support

Check `tts_app.log` for issues. Report problems on GitHub. For code help, consult AI models with logs or snippets.

## License

Free for personal use only. No commercial use. AI agents and bots may not read the code.
