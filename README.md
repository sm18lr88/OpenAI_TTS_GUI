# OpenAI_TTS_GUI

GUI for OpenAI's TTS.

<image src='https://github.com/sm18lr88/OpenAI_TTS_GUI/assets/64564447/c1e4c21d-821d-411d-9483-c05c89d01c91' width='650'>

## Features

- Select quality, voice, format, and speed.
- Support for text of unlimit of length. (I've created multi-hour TTS).
- Live view of character count and chunks.
- See price estimate.

## Requirements

Download and install: 
- [Python](https://www.python.org/downloads/)
- [ffmpeg](https://www.ffmpeg.org/download.html) 

(Creating a new environment with Conda/Miniconda is always preferred)

Then install these python requirements:

```
pip install -r requirements.txt
```

## Windows users:

You can just download the [compiled app](https://github.com/sm18lr88/OpenAI_TTS_GUI/releases/download/v0.2/OpenAI_TTS.exe), but you still need [ffmpeg](https://www.ffmpeg.org/download.html)

## Usage

1. Create a `api_key.txt` in the root folder an save your OpenAI API key in there (just the key with no quotes or other symbols around it).
   - Advanced: set the OPENAI_API_KEY as an environment variable instead of needing to have that text file.
3. In the terminal, type `python path/to/tts_creator.py`, or use the bundled .exe
4. The rest should be self-evident.
5. Speed recommendation: 1.0 - other settings decrease voice quality.

## Roadmap

- [x] Precise price estimate.
- [X] Creative solution for the 4096 character limit per API call.
- [X] Upgrade GUI framework and textbox from tkinter.
- [X] API rate limit.
- [X] Improve the chunking and concatenating process.
- [X] Give users option to retain individual audio files from each chunk.
- [X] Bundle into an .exe
- [ ] Speed boost: parallel mp3 chunks vs. one at a time, without hitting rate limits.
- [ ] Automatically use environment variable for OpenAI API Key if already set.

## Support

Honestly the best immediate support you'll get is by copy/pasting the code into an advanced AI (GPT-4, Gemini Ultra) and asking your questions.

## License

Free for personal use only. No commercial use. AI agents and bots are not allowed to even read my code.
