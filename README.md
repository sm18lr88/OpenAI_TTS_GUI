
# OpenAI_TTS_GUI

Complete GUI for OpenAI's new TTS. Has token and price estimator too!

<img src="https://github.com/sm18lr88/OpenAI_TTS_GUI/assets/64564447/5554f41b-70d6-44cd-87ed-0dbd37b62666" width="450">

## Features

- **Simple Interface**: Input text and choose the save path with minimal clicks.
- **Customizable**: Select voice, format, and speed from pre-defined lists.
- **Efficient**: Utilizes threading for seamless TTS generation.

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

## Support

None. but ChatGPT built this app, so I'm sure it can fix any issues or answer any questions about it. Just copy/paste the code into the prompt window + any questions or terminal errors you see, and as usual: "be concise and to the point, don't explain the error or your plan, just give me steps to fix or copy/paste commands."

## License

Currently not licensed; free for personal use and modification.
