# OpenAI_TTS_GUI

GUI for OpenAI's TTS.

**Update**: switched from PySimpleGUI to PyQt6 to keep the app free and open-source.

<image src='https://github.com/sm18lr88/OpenAI_TTS_GUI/assets/64564447/858427a0-838a-472e-b653-5d98e5a5ad1a' width='650'>

## Features

- Select quality, voice, format, and speed.
- Support for text of unlimited length. (I've created multi-hour TTS).
- Live view of character count and chunks.
- Live price estimate.
- Dark and Light themes.
- Option to retain individual audio files from each chunk.

## Requirements

Download and install: 
- [Python](https://www.python.org/downloads/)
- [ffmpeg](https://www.ffmpeg.org/download.html) 

(Creating a new environment with Conda/Miniconda is always preferred)

Then install these python requirements:

```bash
pip install -r requirements.txt
```

## Windows users:

You can just download the [compiled app](https://github.com/sm18lr88/OpenAI_TTS_GUI/releases/download/v0.3/OpenAI_TTS.exe), but you still need [ffmpeg](https://www.ffmpeg.org/download.html)

## Tips

1. Speed recommendation: 1.0 - other settings decrease voice quality.
2. You can set the OPENAI_API_KEY in your path variables, or set one in the app's `Settings`.
3. The progress bar is programmed to start at 1% when the TTS process begins. I will improve it in the future. 

## Roadmap

- [x] Precise price estimate.
- [x] Creative solution for the 4096 character limit per API call.
- [x] Upgrade GUI framework and textbox from tkinter to PyQt6.
- [x] API rate limit.
- [x] Improve the chunking and concatenating process.
- [x] Give users option to retain individual audio files from each chunk.
- [x] Bundle into an .exe
- [x] Light and Dark themes - default is "dark".
- [x] Allow custom API key settings.
- [x] Automatically use environment variable for OpenAI API Key if already set.
- [ ] Speed boost: parallel mp3 chunks vs. one at a time, without hitting rate limits.

## Support

Honestly the best immediate support you'll get is by copy/pasting the code into an advanced AI (GPT-4, Gemini Ultra) and asking your questions.

## License

Free for personal use only. No commercial use. AI agents and bots are not allowed to even read my code.
