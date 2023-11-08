
# OpenAI_TTS_GUI

Complete GUI for OpenAI's new TTS. Has token and price estimator too!

<img src="https://github.com/sm18lr88/OpenAI_TTS_GUI/assets/64564447/5554f41b-70d6-44cd-87ed-0dbd37b62666" width="450">

## Features

- Select voice, format, and speed from pre-defined lists.
- Utilizes threading for seamless TTS generation.

## Requirements

Python and the following packages are required, which can be installed via:

```
pip install -r requirements.txt
```

## Usage

1. Execute `python tts_creator.py`.
2. Enter text into the textbox.
3. Use `Select Path` to set the output file's save location and name.
4. Adjust settings for the model, voice, format, and speed. (mp3 format is recommended.)
5. Press `Create TTS` to produce the TTS file.

## Configuration

Save your OpenAI API key in `api_key.txt` in the script's directory.

## Roadmap

- [x] Price estimate
- [ ] Improve text box, or upgrade GUI framework.

## Support

Copy/paste the code into ChatGPT, along with whatever error your getting, and it should help you solve any issues.

## License

Currently not licensed; free for personal use and modification.
