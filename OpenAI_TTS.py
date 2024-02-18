import PySimpleGUI as sg
import requests
import os
import subprocess
import time
import logging
from threading import Thread
from decimal import Decimal

# Constants for price and API calls
TTS_PRICE_PER_1K_CHARS = Decimal('0.015')
TTS_HD_PRICE_PER_1K_CHARS = Decimal('0.030')
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

# Set up logging
logging.basicConfig(filename='tts_app.log', level=logging.DEBUG,
                    format='%(asctime)s:%(levelname)s:%(message)s')

# Estimate the precise price for regular and high-definition TTS
def estimate_price(char_count, hd=False):
    token_price = TTS_PRICE_PER_1K_CHARS if not hd else TTS_HD_PRICE_PER_1K_CHARS
    char_blocks = (char_count + 999) // 1000  
    total_price = char_blocks * token_price
    return total_price

def read_api_key():
    try:
        with open('api_key.txt', 'r') as file:
            return file.read().strip()
    except FileNotFoundError:
        sg.popup_error("Error", "API key file 'api_key.txt' not found.")
        return None
    except Exception as e:
        sg.popup_error("Close", str(e))
        return None

# Function to get around the current 4096 character limit. Shouldn't affect resultant TTS much, if at all.
def split_text(text, chunk_size=4096):
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    while text:
        if len(text) <= chunk_size:
            chunks.append(text)
            break
        split_index = -1
        # First, try to split at the last sentence end within the chunk size
        for punct in ['.', '?', '!']:
            last_punct_index = text[:chunk_size].rfind(punct)
            if last_punct_index != -1:
                split_index = max(split_index, last_punct_index + 1)
    
        # If no sentence end is found, look for the last space
        if split_index == -1:
            split_index = text[:chunk_size].rfind(' ')
        
        # If no space is found, force split at the chunk size
        if split_index == -1:
            split_index = chunk_size
        chunks.append(text[:split_index])
        text = text[split_index:].lstrip()
    return chunks

def select_path(window, selected_format):
    # Mapping formats to their file types and extensions
    format_to_extension = {
        'mp3': ('MP3 audio file', '*.mp3'),
        'opus': ('Opus audio file', '*.opus'),
        'aac': ('AAC audio file', '*.aac'),
        'flac': ('FLAC audio file', '*.flac'),
    }

    # Get the corresponding file type and extension for the selected format
    file_type_description, file_type_pattern = format_to_extension.get(selected_format, ('All Files', '*.*'))

    file_path = sg.popup_get_file(
        'Save As',
        save_as=True,
        no_window=True,
        default_extension=file_type_pattern.split(';')[0],  # Adjust this to use the first pattern
        file_types=[format_to_extension[selected_format]],  # Restrict file types to the selected format
    )
    if file_path:
        window['path_entry'].update(file_path)

# Joining all the resulting audio files together. Might throw the TTS speech off in terms of timing, but I haven't noticed anything so far.
def concatenate_audio_files(file_list, output_file):
    try:
        output_dir = os.path.dirname(output_file)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        concat_list_path = os.path.join(output_dir, 'concat_list.txt')

        with open(concat_list_path, 'w') as f:
            for file_path in file_list:
                f.write(f"file '{file_path}'\n")

        # Determine the codec based on the file extension
        output_extension = os.path.splitext(output_file)[1].lower()
        if output_extension == '.mp3':
            codec = 'libmp3lame'
        elif output_extension == '.flac':
            codec = 'flac'
        elif output_extension == '.aac':
            codec = 'aac'
        elif output_extension == '.opus':
            codec = 'libopus'
        else:
            codec = 'copy'  # Default to copy if the format is unknown

        concat_command = ['ffmpeg', '-f', 'concat', '-safe', '0', '-i', concat_list_path, '-c:a', codec, output_file]

        subprocess.run(concat_command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.remove(concat_list_path)
    except Exception as e:
        logging.error(f"Error in concatenating audio files: {e}")

def process_speech(chunks, path, api_key, model, voice, response_format, speed, retain_files, window):
    temp_files = []
    total_chunks = len(chunks)
    for i, chunk in enumerate(chunks):
        progress = (i / total_chunks) * 100
        window.write_event_value('-UPDATE PROGRESS-', progress)
        temp_filename = os.path.join(os.path.dirname(path), f"{os.path.splitext(os.path.basename(path))[0]}_{i}.{response_format}")
        temp_files.append(temp_filename)
        if not save_chunk(chunk, temp_filename, api_key, model, voice, response_format, speed):
            cleanup_files(temp_files, retain_files)
            return
    concatenate_audio_files(temp_files, path)
    window.write_event_value('-UPDATE PROGRESS-', 100)
    if not retain_files:
        cleanup_files(temp_files, retain_files)

last_request_time = 0

# Limit API requests to remain within OpenAI's limits for the Speech API:
def rate_limited_request(api_key, data, model):
    global last_request_time
    min_interval = 60 / 50  # for tts-1
    if 'hd' in model:
        min_interval = 60 / 3  # for tts-1-hd

    elapsed = time.time() - last_request_time
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)
    response = requests.post('https://api.openai.com/v1/audio/speech', headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}, json=data)
    last_request_time = time.time()
    return response

def save_chunk(text, filename, api_key, model, voice, response_format, speed):
    data = {'model': model, 'input': text, 'voice': voice, 'response_format': response_format, 'speed': speed}
    for attempt in range(MAX_RETRIES):
        try:
            response = rate_limited_request(api_key, data, model)
            if response.status_code == 200:
                if len(response.content) == 0:
                    logging.error(f"Received empty audio content for chunk {filename}.")
                    return False
                with open(filename, 'wb') as file:
                    file.write(response.content)
                return True
            elif response.status_code in [429, 500, 502, 503, 504]:
                logging.warning(f"Received status code {response.status_code}. Retrying after delay.")
                time.sleep(RETRY_DELAY * (attempt + 1))
            else:
                logging.error(f"Failed to create TTS for chunk {filename}: {response.status_code}\n{response.text}")
                return False
        except requests.RequestException as e:
            logging.exception(f"Network error occurred on attempt {attempt + 1}: {e}")
            time.sleep(RETRY_DELAY * (attempt + 1))
    return False

def create_tts(values, window):
    text = values['text_box'].strip()
    path = values['path_entry']
    if not path or not os.path.isdir(os.path.dirname(path)):
        sg.popup_error("Invalid path")
        return
    api_key = read_api_key()
    if not api_key:
        return
    model = values['model_var']
    voice = values['voice_var']
    response_format = values['format_var']
    speed = float(values['speed_var']) if values['speed_var'] else 1.0
    hd = 'hd' in model
    chunks = split_text(text)
    estimated_price = estimate_price(len(text), hd)
    retain_files = values['retain_files']
    if sg.popup_ok_cancel(f"The estimated cost for this TTS is ${estimated_price:.2f}. Do you want to continue?") == "OK":
        Thread(target=process_speech, args=(chunks, path, api_key, model, voice, response_format, speed, retain_files, window)).start()

# OpenAI's TTS sounds good only at 1.0. Besides that it gets distorted. 
# Adobe Audition's Stretch and Pitch effect with the iZotope Radius algorithm is the best there is IMO. 
# In Adobe Audition, I like to stretch my TTS audio at 110-115%, no pitch shift, and pitch coherence between 2-4 (max). This makes Echo's voice really easy to follow if listening to lectures or academic papers.
def update_speed(window, values):
    try:
        speed_value = float(values['speed_var'])
        if not 0.25 <= speed_value <= 4.0:
            window['speed_var'].update("1.0")
    except ValueError:
        window['speed_var'].update("1.0")

def cleanup_files(file_list, retain_files):
    if not retain_files:
        for file in file_list:
            try:
                os.remove(file)
            except Exception as e:
                logging.error(f"Failed to delete temporary file {file}: {e}")

# PySimpleGUI Theme
sg.theme('BrownBlue')

# GUI for the settings section
settings_layout = [
    [sg.Text("Model:"), sg.Combo(['tts-1', 'tts-1-hd'], default_value='tts-1', key='model_var', readonly=True, size=(10, 1))],
    [sg.Text("Voice:"), sg.Combo(['echo', 'alloy', 'fable', 'onyx', 'nova', 'shimmer'], default_value='echo', key='voice_var', readonly=True, size=(10, 1))],
    [sg.Text("Speed:"), sg.InputText(default_text="1.0", key='speed_var', tooltip="1.0 is best, any deviation significantly degrades voice quality",size=(10, 1), enable_events=True)],
    [sg.Text("Format:"), sg.Combo(['mp3', 'opus', 'aac', 'flac'], default_value='mp3', key='format_var', readonly=True, size=(10, 1))]
]

# GUI for the overall layout
layout = [
    [sg.Text("Text for TTS:"), sg.Push(), sg.Text("Limit: 4096 chars (auto-chunks if exceeded)", justification='right')],
    [sg.Multiline(size=(45, 10), key='text_box', expand_x=True, expand_y=True, enable_events=True)],
    [sg.Text("Character Count: "), sg.Text("0", size=(15, 1), key="char_count"),
     sg.Text("Number of Chunks: "), sg.Text("0", size=(15, 1), key="chunk_count", tooltip="Chunks of 4096 characters.\nVisual indicator for the expense you will incur.")],
    [sg.Frame(title="Settings", layout=[
        [sg.Text("Model:"), sg.Combo(['tts-1', 'tts-1-hd'], default_value='tts-1', key='model_var', readonly=True, size=(10, 1)),
         sg.Text("Voice:"), sg.Combo(['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer'], default_value='alloy', key='voice_var', readonly=True, size=(10, 1)), # I like Echo's voice the most
         sg.Text("Speed:"), sg.InputText(default_text="1.0", key='speed_var', size=(10, 1), enable_events=True), # At the moment, OpenAI's TTS only sound good at 1.0. Any deviation decreases the quality significantly. See my comment on Adobe Audition.
         sg.Text("Format:"), sg.Combo(['mp3', 'opus', 'aac', 'flac'], default_value='mp3', key='format_var', readonly=True, size=(10, 1))]
    ])],
    [sg.Text("Save Path:"), sg.InputText(key='path_entry', expand_x=True), sg.Button("Select Path")],
    [sg.Checkbox("Retain individual audio files", default=False, key='retain_files', tooltip="If your TTS job was >4096 characters, multiple audio files get created and then joined.\nBut the individual segments get deleted.\nIf you click here, you will retain those individual segments besides the final joint audio file.")],
    [sg.Text("Progress:"), sg.ProgressBar(max_value=100, orientation='h', size=(45, 20), key='progress_bar')],
    [sg.Button("Estimate Price"), sg.Button("Create TTS")]
]

window = sg.Window("OpenAI TTS", layout, resizable=True)

# Event Loop
while True:
    event, values = window.read()

    if event == sg.WIN_CLOSED:
        break

    if event == 'text_box':  
        text = values['text_box']
        char_count = len(text)
        chunks = split_text(text)
        num_chunks = len(chunks)
        window['char_count'].update(f"{char_count}")
        window['chunk_count'].update(f"{num_chunks}")

    elif event == "Select Path":
        selected_format = values['format_var']  # Retrieve the selected format from the dropdown
        select_path(window, selected_format)  # Pass the selected format to the select_path function

    elif event == "Estimate Price":
        text = values['text_box']
        hd = 'hd' in values['model_var']
        char_count = len(text)
        price = estimate_price(char_count, hd)
        sg.popup(f"Estimated price: ${price:.3f}")

    elif event == "Create TTS":
        create_tts(values, window)

    elif event == '-UPDATE PROGRESS-':
        progress_value = values[event]
        window['progress_bar'].update_bar(progress_value)

    elif event == 'speed_var' and values['speed_var']:
        update_speed(window, values)

window.close()
