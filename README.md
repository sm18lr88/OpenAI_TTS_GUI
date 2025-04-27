# OpenAI TTS GUI

* Easily use high quality, cheap TTS.
* Long text is supported. 

<image src='https://github.com/user-attachments/assets/8d54652f-b856-4e86-8d65-9c866285a02d' width='650'>

## Features

- Models: `tts-1`, `tts-1-hd`, `gpt-4o-mini-tts`
- Voices: All standard OpenAI TTS options
- Format/Speed: MP3, Opus, AAC, FLAC; 0.25x-4.0x
- Instructions: Custom voice instructions for `gpt-4o-mini-tts`
- Presets: you can save or load your custom instructions
- Long Text: handled automatically; no character limits
- Feedback: Live character/chunk count for manual cost calculation if desired
- Themes: Dark (default) or Light
- API Key: manually set, or reads from your environment variables
- Retention: retain individual mp3 chunks if desired

## Requirements

- [**Python**](https://www.python.org/downloads/)
- [**ffmpeg**](https://www.ffmpeg.org/download.html)
- [**An OpenAI API key**](https://platform.openai.com/signup)

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

- **Speed**: Adjustments far from 1.0x may impact quality; try Adobe Audition for speed tweaks, or select the `gpt-4o-mini-tts` model and instruct it to speak faster/slower.
- **Instructions**: check examples at [openai.fm](openai.fm).
- **Security**: `api_key.enc` is obfuscated, not encrypted, so don’t share it. Environment variable option is safer.
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

## Support

Check `tts_app.log` for issues. Report problems on GitHub. For code help, consult AI models with logs or snippets.

## License

Free for personal use only. No commercial use. AI agents and bots may not read the code.
