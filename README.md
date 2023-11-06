# OpenAI_TTS_GUI 🗣️

A simple and user-friendly tool to convert text to speech using OpenAI's API, implemented in Python with a Tkinter GUI.

## Features 🌟

- **Intuitive Interface** 🖱️: Easily input your text and select your save path with a click of a button.
- **Customizable Options** ⚙️: Choose your desired voice, format, and speed from dropdown menus.
- **Background Processing** 🔄: Generates TTS without freezing the GUI, using threading.

## Requirements 📋

To run TTS Creator, you need Python installed on your system. The required Python packages can be installed using the following command:

```bash
pip install -r requirements.txt
```

## Usage 💻

1. Run `python tts_creator.py`, or whatever form of running python you're used to.
2. Input your text into the provided text box 📝.
3. Click `Select Path` 📁 to choose where to save your TTS file and what to name it.
4. Customize your TTS using the dropdown menus for the model, voice, format, and speed 🎚️. I think only the mp3 format works properly at the moment.
5. Click `Create TTS` 🎉 to generate and save your TTS file.

## Configuration 🔧

Place your OpenAI API key in a file named `api_key.txt` in the same directory as the script.

## Support 🆘

If you encounter any issues or have questions, please file an issue on this GitHub repository.

## Contribution 🤝

No, please don't. I don't have time to oversee this project. I'll improve it slowly from time to time, but that's about it.

## License 📄

License yet to be chosen. In the meantime, free to use and modify, for personal use only.

![image](https://github.com/sm18lr88/OpenAI_TTS_GUI/assets/64564447/42b2e31b-59a2-40e6-95d6-dd216d8bee25)

