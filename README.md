# OpenAI TTS GUI

Easily use high quality, cheap TTS.

<image src='https://github.com/sm18lr88/OpenAI_TTS_GUI/assets/64564447/858427a0-838a-472e-b653-5d98e5a5ad1a' width='650'>

## Features

- **Model Selection**: Choose between `tts-1`, `tts-1-hd`, and `gpt-4o-mini-tts`.
- **Voice Selection**: Access all standard OpenAI TTS voices.
- **Format & Speed**: Select output format (MP3, Opus, AAC, FLAC) and adjust playback speed (0.25x - 4.0x).
- **Instructions Support**: Add custom voice guidance for `gpt-4o-mini-tts`.
- **Instruction Presets**: Save, load, and manage frequently used instructions.
- **Long Text Handling**: Splits large texts into API-compliant chunks and concatenates using `ffmpeg`.
- **Real-time Feedback**: Displays character and chunk counts live.
- **Progress Indication**: Shows TTS generation progress with a bar.
- **Theming**: Toggle between Dark (default) and Light modes.
- **API Key Management**: Set via environment variable or GUI (obfuscated storage in `api_key.enc`).
- **Error Handling**: Includes retries and improved error reporting.
- **Optional File Retention**: Keep intermediate audio chunk files if desired.

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
- [] Bundle new release into .exe

## Support

Check `tts_app.log` for issues. Report problems on GitHub. For code help, consult AI models with logs or snippets.

## License

Free for personal use only. No commercial use. AI agents and bots may not read the code.
