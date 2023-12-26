import PySimpleGUI as sg
import requests
import os
import math
import subprocess
import time
import logging
from pydub import AudioSegment
from threading import Thread
import tiktoken

# Set up logging
logging.basicConfig(filename='tts_app.log', level=logging.DEBUG,
                    format='%(asctime)s:%(levelname)s:%(message)s')

# Constants
TTS_PRICE_PER_1K_CHARS = 0.015
TTS_HD_PRICE_PER_1K_CHARS = 0.030
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

# Token counting function for the "gpt-4": "cl100k_base" model
def count_tokens(text):
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text)
    return len(tokens)

def read_api_key():
    try:
        with open('api_key.txt', 'r') as file:
            return file.read().strip()
    except FileNotFoundError:
        sg.popup_error("Error", "API key file 'api_key.txt' not found.")
        return None
    except Exception as e:
        sg.popup_error("Error", str(e))
        return None

def estimate_price(text_length, hd=False):
    token_price = TTS_PRICE_PER_1K_CHARS if not hd else TTS_HD_PRICE_PER_1K_CHARS
    return math.ceil(text_length / 1000) * token_price

def split_text(text, chunk_size=4096):
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    while text:
        split_index = text.rfind('\n', 0, chunk_size)
        if split_index == -1:
            split_index = text.rfind(' ', 0, chunk_size)
        if split_index == -1:
            split_index = chunk_size
        chunks.append(text[:split_index])
        text = text[split_index:].strip()
    return chunks

def select_path(window):
    file_path = sg.popup_get_file(
        'Save As',
        save_as=True,
        no_window=True,
        default_extension=".mp3",
        file_types=(("MP3 audio file", "*.mp3"), ("WAV audio file", "*.wav"), ("FLAC audio file", "*.flac"), ("AAC audio file", "*.aac")),
    )
    if file_path:
        window['path_entry'].update(file_path)

def concatenate_audio_files(file_list, output_file):
    # Ensure the directory where the output file will be saved exists
    output_dir = os.path.dirname(output_file)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Define the full path for concat_list.txt in the output directory
    concat_list_path = os.path.join(output_dir, 'concat_list.txt')

    # Write file paths to the concat_list.txt file
    with open(concat_list_path, 'w') as f:
        for file_path in file_list:
            f.write(f"file '{file_path}'\n")

    # Concatenate audio files using FFmpeg
    concat_command = ['ffmpeg', '-f', 'concat', '-safe', '0', '-i', concat_list_path, '-c', 'copy', output_file]
    subprocess.run(concat_command, check=True)

    # Remove the temporary list file
    os.remove(concat_list_path)

def process_speech(chunks, path, api_key, model, voice, response_format, speed):
    temp_files = []
    for i, chunk in enumerate(chunks):
        temp_filename = os.path.join(os.path.dirname(path),
                                     f"{os.path.splitext(os.path.basename(path))[0]}_{i}.{response_format}")
        temp_files.append(temp_filename)
        if not save_chunk(chunk, temp_filename, api_key, model, voice, response_format, speed):
            cleanup_files(temp_files)
            return
    concatenate_audio_files(temp_files, path)
    cleanup_files(temp_files)

def save_chunk(text, filename, api_key, model, voice, response_format, speed):
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    data = {
        'model': model,
        'input': text,
        'voice': voice,
        'response_format': response_format,
        'speed': speed
    }
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post('https://api.openai.com/v1/audio/speech', headers=headers, json=data)
            if response.status_code == 200:
                if len(response.content) == 0:
                    logging.error(f"Received empty audio content for chunk {filename}.")
                    return False
                with open(filename, 'wb') as file:
                    file.write(response.content)
                return True
            elif response.status_code == 429 or response.status_code >= 500:
                logging.warning(f"Received status code {response.status_code}. Retrying after delay.")
                time.sleep(RETRY_DELAY * (2 ** attempt))
            else:
                logging.error(f"Failed to create TTS for chunk {filename}: {response.status_code}\n{response.text}")
                return False
        except requests.RequestException as e:
            logging.exception("Network error occurred.")
            if attempt < MAX_RETRIES - 1:
                logging.info(f"Retrying... Attempt {attempt + 1}")
                time.sleep(RETRY_DELAY)
            else:
                return False

def cleanup_files(file_list):
    for file in file_list:
        try:
            os.remove(file)
        except Exception as e:
            logging.error(f"Failed to delete temporary file {file}: {e}")

# GUI setup
sg.theme('BrownBlue')

settings_layout = [
    sg.Text("Model:"), sg.Combo(['tts-1', 'tts-1-hd'], default_value='tts-1', key='model_var', readonly=True, size=(10, 1)),
    sg.Text("Voice:"), sg.Combo(['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer'], default_value='alloy', key='voice_var', readonly=True, size=(10, 1)),
    sg.Text("Speed:"), sg.Combo([0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 3.5, 4.0], default_value=1.0, key='speed_var', readonly=True, size=(10, 1)),
    sg.Text("Format:"), sg.Combo(['mp3', 'opus', 'aac', 'flac'], default_value='mp3', key='format_var', readonly=True, size=(10, 1))
]

layout = [
    [sg.Text("Text for TTS:")],
    [sg.Multiline(size=(45, 10), key='text_box', expand_x=True, expand_y=True, enable_events=True)],
    [sg.Text("Token Count: "), sg.Text("0", size=(15, 1), key="token_count")],
    [sg.Frame(title="Settings", layout=[settings_layout], relief=sg.RELIEF_SUNKEN, expand_x=True)],
    [sg.Text("Save Path:"), sg.InputText(key='path_entry', expand_x=True), sg.Button("Select Path")],
    [sg.Button("Estimate Price"), sg.Button("Create TTS")]
]

# Create the window
window = sg.Window("OpenAI TTS", layout, resizable=True)

# Event Loop
while True:
    event, values = window.read()

    if event == sg.WIN_CLOSED:
        break

    # This event is triggered whenever the text in 'text_box' is changed
    if event == 'text_box':  
        text = values['text_box']
        token_count = count_tokens(text)
        window['token_count'].update(f"{token_count}")

    elif event == "Select Path":
        file_path = sg.popup_get_file(
            'Save As',
            save_as=True,
            no_window=True,
            default_extension=".mp3",
            file_types=(("MP3 audio file", "*.mp3"), ("WAV audio file", "*.wav"), ("FLAC audio file", "*.flac"), ("AAC audio file", "*.aac"))
        )
        if file_path:
            window['path_entry'].update(file_path)

    elif event == "Estimate Price":
        text = values['text_box']
        hd = 'hd' in values['model_var']
        price = estimate_price(len(text), hd)
        sg.popup(f"Estimated price: ${price:.2f}")

    elif event == "Create TTS":
        text = values['text_box'].strip()
        path = values['path_entry']
        api_key = read_api_key()
        if not api_key:
            continue
        model = values['model_var']
        voice = values['voice_var']
        response_format = values['format_var']
        speed = values['speed_var']
        hd = 'hd' in model
        chunks = split_text(text)
        estimated_price = estimate_price(len(text), hd)
        if sg.popup_ok_cancel(f"The estimated cost for this TTS is ${estimated_price:.2f}. Do you want to continue?") == "OK":
            Thread(target=process_speech, args=(chunks, path, api_key, model, voice, response_format, speed)).start()

window.close()
