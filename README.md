# OpenAI_TTS_GUI

GUI for OpenAI's TTS.

<image src='https://github.com/sm18lr88/OpenAI_TTS_GUI/assets/64564447/af41aea7-653d-4074-b204-d7feab50d182' width='650'>

## Features

- Select voice, format, and speed from pre-defined lists.
- Text over 4096 characters get chunked, turned into audio, then concatenated.
- Live view of token count, character count, and estimated price.

## Personalized assistance setting up this app:

Copy/paste this text into ChatGPT and ask it to help you, seriously. Best way for those not familiar with python and ffmpeg.

## Requirements

Download and install: 
- [Python](https://www.python.org/downloads/)
- [ffmpeg](https://www.ffmpeg.org/download.html) 

(Creating a new environment with Conda/Miniconda is always preferred)

Then install these python requirements:

```
pip install -r requirements.txt
```

## Add your OpenAI API key

Save your OpenAI API key inside the `api_key.txt` file.

## Usage

1. Execute `python tts_creator.py`.
2. Enter text into the textbox.
3. Use `Select Path` to set the output file's save location and name.
4. Adjust settings for the model, voice, format, and speed. (mp3 format is recommended.)
5. Press `Create TTS` to produce the TTS file.

## Roadmap

- [x] Rough price estimate.
- [X] Creative solution for the 4096 character limit per API call.
- [X] Improve text box, or upgrade GUI framework.
- [ ] Correct price estimate when chunking.
- [ ] Improve the chunking and concatenating process, and maybe give users some options.

## Support

Honestly the best immediate support you'll get is by copy/pasting the code into ChatGPT and asking your questions.

## License

Free for personal use only. No commercial use.
