import concurrent.futures
from decimal import Decimal
import logging
import os
import PySimpleGUI as sg
import requests
import subprocess
from threading import Thread
import time

# Initialize global variable for API rate limiting
last_request_time = 0

# Constants for price
TTS_PRICE_PER_1K_CHARS = Decimal('0.015')
TTS_HD_PRICE_PER_1K_CHARS = Decimal('0.030')

# Constants for API call rate limits
MAX_RETRIES = 3
RETRY_DELAY = 5  # Initial delay in seconds, for retrying API calls

# API key management
# Prefer environment variable; fallback to text file if necessary.
api_key = os.getenv('OPENAI_API_KEY')
if not api_key:
    def read_api_key():
        """Read the OpenAI API key from a file if not set as an environment variable.
        
        Returns:
            str: The API key, or None if the file doesn't exist or an error occurs.
        """
        try:
            with open(
                        'api_key.txt', 
                        'r'
                    ) as file:
                return file.read().strip()
        except FileNotFoundError:
            sg.popup_error(
                            "Error", 
                            "API key file 'api_key.txt' not found."
                            )
            
        except Exception as e:
            sg.popup_error(
                            "Error", 
                            str(e)
                            )
        return None

    api_key = read_api_key()

# Set up logging
logging.basicConfig(
                    filename='tts_app.log',
                    level=logging.DEBUG,
                    format='%(asctime)s:%(levelname)s:%(message)s'
                    )

def estimate_price(
                    char_count, 
                    hd=False
                    ):
    
    """Calculate the estimated price for text-to-speech conversion.
    
    Args:
        char_count (int): Number of characters in the input text.
        hd (bool): True if high-definition speech synthesis is requested, False otherwise.
    
    Returns:
        Decimal: The estimated price.
    """
    
    token_price = TTS_HD_PRICE_PER_1K_CHARS if hd else TTS_PRICE_PER_1K_CHARS
    char_blocks = (char_count + 999) // 1000  # Round up to the next thousand
    return char_blocks * token_price

def split_text(text, chunk_size=4096):
    
    """Split text into chunks that comply with the API's character limit.
    
    Args:
        text (str): The input text to split.
        chunk_size (int): Maximum size of each chunk. Default is 4096.
    
    Returns:
        list: A list of text chunks.
    """
    
    chunks = []
    while text:
        # Find the last punctuation to keep sentences intact.
        split_index = max(
                        (
                            text.rfind(
                                        punct, 
                                        0, 
                                        chunk_size
                                        ) 
                            + 1 for punct in '.?!'
                        ), 
                        default=chunk_size
                        )
        
        # Adjust if no suitable punctuation is found.
        if split_index <= 0:
            split_index = text.rfind(
                                        ' ', 
                                        0, 
                                        chunk_size
                                    )
            
        if split_index <= 0:
            split_index = chunk_size
        chunks.append(text[:split_index])
        text = text[split_index:].lstrip()
    return chunks

def rate_limited_request(
                            api_key, 
                            data, 
                            model
                        ):
    
    """Perform a rate-limited request to the OpenAI API.
    
    Ensures that requests don't exceed the rate limits specified by the model.
    Args:
        api_key (str): The API key for authentication.
        data (dict): The data payload for the POST request.
        model (str): The model being used, affecting rate limits.
    
    Returns:
        Response: The response object from the requests library.
    """
    global last_request_time
    
    min_interval = 60 / 50  # Assume 50 requests per minute for tts-1
    if 'hd' in model:
        min_interval = 60 / 3  # Assume 3 requests per minute for tts-1-hd

    elapsed = time.time() - last_request_time
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)
    
    response = requests.post(
                                'https://api.openai.com/v1/audio/speech',
                                headers={
                                            'Authorization': f'Bearer {api_key}',
                                            'Content-Type': 'application/json'
                                        },
                                json=data
                            )
    
    last_request_time = time.time()
    return response

def save_chunk(
                text, 
                filename, 
                api_key, 
                model, 
                voice, 
                response_format, 
                speed):
    
    """Attempt to save a single TTS audio chunk, retrying on failure.
    
    Retries are performed with exponential backoff to handle rate limits and temporary errors gracefully.
    Args:
        text (str): The text to convert to speech.
        filename (str): Where to save the resulting audio file.
        api_key (str): The API key for authentication.
        model, voice, response_format, speed: TTS parameters.
    
    Returns:
        bool, str: Success flag and the filename of the saved audio file.
    """
    
    attempt = 0
    backoff = RETRY_DELAY
    while attempt < MAX_RETRIES:
        attempt += 1
        try:
            data = {
                    'model': model, 
                    'input': text, 
                    'voice': voice, 
                    'response_format': response_format, 
                    'speed': speed}
            
            response = rate_limited_request(
                                            api_key, 
                                            data, 
                                            model)
            
            if response.status_code == 200 and len(response.content) > 0:
                with open(filename, 'wb') as file:
                    file.write(response.content)
                logging.info(f"Chunk saved successfully: {filename}")
                return True, filename
            
            elif response.status_code in [
                                            429, 
                                            500, 
                                            502, 
                                            503, 
                                            504]:
                
                logging.warning(f"Attempt {attempt}: Rate limit or server error ({response.status_code}) for '{filename}'. Retrying after {backoff} seconds...")
                time.sleep(backoff)
                backoff *= 2  # Exponential backoff
                
            else:
                logging.error(f"Attempt {attempt}: Non-retriable HTTP status ({response.status_code}) for '{filename}'.")
                break
        except Exception as e:
            logging.exception(f"Attempt {attempt}: Exception during API call for '{filename}': {e}. Retrying after {backoff} seconds...")
            time.sleep(backoff)
            backoff *= 2  # Exponential backoff

    logging.error(f"Failed to process TTS for '{filename}' after {MAX_RETRIES} attempts.")
    return False, filename

def select_path(window):
    file_path = sg.popup_get_file(
                                    'Save As',
                                    save_as=True,
                                    no_window=True,
                                    default_extension=".mp3",
                                    file_types=(
                                                ("MP3 audio file", "*.mp3"), 
                                                ("WAV audio file", "*.wav"), 
                                                ("FLAC audio file", "*.flac"), 
                                                ("AAC audio file", "*.aac")),
                                )
    
    if file_path:
        window['path_entry'].update(file_path)

# Joining all the resulting audio files together. Might throw the TTS speech off in terms of timing, but I haven't noticed anything so far.
def concatenate_audio_files(
                            file_list, 
                            output_file
                            ):
    try:
        output_dir = os.path.dirname(output_file)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        concat_list_path = os.path.join(output_dir, 'concat_list.txt')
        
        with open(concat_list_path, 'w') as f:
            for file_path in file_list:
                f.write(f"file '{file_path}'\n")
                
        concat_command = [
                            'ffmpeg', 
                            '-f', 
                            'concat', 
                            '-safe', 
                            '0', 
                            '-i', 
                            concat_list_path, 
                            '-c', 
                            'copy', 
                            output_file
                        ]
                            
        subprocess.run(
                        concat_command, 
                        check=True, 
                        stdout=subprocess.DEVNULL, 
                        stderr=subprocess.DEVNULL)
                        
        os.remove(concat_list_path)
        
    except Exception as e:
        logging.error(f"Error in concatenating audio files: {e}")

def process_speech(
                    chunks, 
                    path, 
                    api_key, 
                    model, 
                    voice, 
                    response_format, 
                    speed, 
                    retain_files, 
                    window
                    ):
    
    """Process text chunks into speech, ensuring all are successfully converted.
    
    Args:
        chunks (list): Text chunks to convert to speech.
        path (str): Base path for saving audio files.
        api_key, model, voice, response_format, speed: TTS parameters.
        retain_files (bool): Whether to retain individual chunk files.
        window (sg.Window): The GUI window for progress updates.
    """
    temp_files = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
                    executor.submit(
                                    save_chunk, 
                                    chunk, 
                                    os.path.join(
                                                    os.path.dirname(path), 
                                                    f"{os.path.splitext(
                                                                        os.path.basename(path))[0]}_{i}.{response_format}"), 
                                    api_key, 
                                    model, 
                                    voice, 
                                    response_format, 
                                    speed
                                    ): i for i, 
                    chunk in enumerate(chunks)
                    }
        
        for future in concurrent.futures.as_completed(futures):
            success, filename = future.result()
            if success:
                temp_files.append(filename)
            else:
                logging.error(f"Failed to process file: {filename}")
                
                # Early exit if any chunk fails, after canceling all pending futures
                for f in futures:
                    f.cancel()
                sg.popup_error("Failed to process some text chunks. Please check the logs for details.")
                return

            # Update GUI progress
            progress = len(temp_files) / len(chunks) * 100
            
            window.write_event_value(
                                    '-UPDATE PROGRESS-', 
                                    progress
                                    )

    if len(temp_files) == len(chunks):
        concatenate_audio_files(
                                temp_files, 
                                path
                                )
        
        window.write_event_value(
                                '-UPDATE PROGRESS-', 
                                100
                                )
        
        if not retain_files:
            cleanup_files(
                        temp_files, 
                        retain_files
                        )
    else:
        sg.popup_error("Concatenation skipped due to missing audio files.")


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
        Thread(
                target=process_speech, 
                args=(
                        chunks, 
                        path, 
                        api_key, 
                        model, 
                        voice, 
                        response_format, 
                        speed, 
                        retain_files, 
                        window
                    )
                ).start()


###################################################################################################################
# OpenAI's TTS sounds good only at 1.0. 
# Recommended algorithms to change speed (stretch, not pitch): 
#   - iZotope Radius with lots of pitch coherence (2-4)
#   - Adobe Audition's proprietary algorithm with the settings specific to vocals.
###################################################################################################################

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

import PySimpleGUI as sg

# GUI for the settings section, adhering to the specified formatting style
settings_layout = [
                    [sg.Text("Model:"), 
                                        sg.Combo(['tts-1', 'tts-1-hd'], 
                                                                        default_value='tts-1', 
                                                                        key='model_var', 
                                                                        readonly=True, 
                                                                        size=(10, 1))],
                    [sg.Text("Voice:"), 
                                        sg.Combo([
                                                    'echo', 
                                                    'alloy', 
                                                    'fable', 
                                                    'onyx', 
                                                    'nova', 
                                                    'shimmer'
                                                ], 
                                                default_value='echo', 
                                                key='voice_var', 
                                                readonly=True, 
                                                size=(10, 1)
                                                )
                    ],
                    [sg.Text("Speed:"), 
                                        sg.InputText(
                                                    default_text="1.0", 
                                                    key='speed_var', 
                                                    tooltip="1.0 is best, any deviation significantly degrades voice quality",
                                                    size=(10, 1), 
                                                    enable_events=True
                                                    )
                    ],
                    [sg.Text("Format:"), 
                                        sg.Combo(
                                                [
                                                    'mp3', 
                                                    'opus', 
                                                    'aac', 
                                                    'flac'
                                                ], 
                                        default_value='mp3', 
                                        key='format_var', 
                                        readonly=True, 
                                        size=(10, 1)
                                                )
                    ]
]

# GUI for the overall layout, maintaining the requested formatting
layout = [
            [sg.Text("Text for TTS:"), 
                                        sg.Push(), 
                                        sg.Text(
                                                "Limit: 4096 chars (auto-chunks if exceeded)", 
                                                justification='right'
                                                )
            ],
    [sg.Multiline(
                    size=(45, 10), 
                    key='text_box', 
                    expand_x=True, 
                    expand_y=True, 
                    enable_events=True
                )
    ],
    [sg.Text("Character Count: "), 
                                    sg.Text(
                                            "0", 
                                            key="char_count", 
                                            size=(15, 1)
                                            )
    ],
    [sg.Text("Number of Chunks: "), 
                                    sg.Text(
                                            "0", 
                                            key="chunk_count", 
                                            size=(15, 1), 
                                            tooltip="Chunks of 4096 characters.\nVisual indicator for the expense you will incur."
                                            )
    ],
    [sg.Frame(
                title="Settings", 
                layout=settings_layout
            )
    ],
    [sg.Text("Save Path:"), 
                            sg.InputText(
                                            key='path_entry', 
                                            expand_x=True
                                        ), 
    sg.Button("Select Path")
    ],
    
    [sg.Checkbox(
                "Retain individual audio files", 
                default=False, 
                key='retain_files', 
                tooltip="If your TTS job was >4096 characters, multiple audio files get created and then joined.\nBut the individual segments get deleted.\nIf you click here, you will retain those individual segments besides the final joint audio file.")],
    [sg.Text("Progress:"), 
    sg.ProgressBar(max_value=100, 
                    orientation='h', 
                    size=(45, 20), 
                    key='progress_bar'
                    )
    ],
    [sg.Button("Estimate Price"), 
    sg.Button("Create TTS")
    ]
]

window = sg.Window(
                    "OpenAI TTS", 
                                layout, 
                                resizable=True)

# Event Loop
while True:
    event, values = window.read()

    if event == sg.WIN_CLOSED:
        break  # Exit loop if window is closed

    if event == 'text_box':
        # Update character and chunk counts when text changes
        text = values['text_box']
        char_count = len(text)
        chunks = split_text(text)
        num_chunks = len(chunks)
        window['char_count'].update(f"{char_count}")
        window['chunk_count'].update(f"{num_chunks}")

    elif event == "Select Path":
        # Open a dialog to select the path for saving the TTS file
        select_path(window)

    elif event == "Estimate Price":
        # Show an estimation of the price based on the text length and HD selection
        text = values['text_box']
        hd = 'hd' in values['model_var']
        price = estimate_price(len(text), hd)
        sg.popup(f"Estimated price: ${price:.2f}")

    elif event == "Create TTS":
        # Start the TTS creation process in a separate thread to avoid blocking the GUI
        create_tts(values, window)

    elif event == '-UPDATE PROGRESS-':
        # Update the progress bar with the value sent from the processing thread
        progress_value = values[event]
        window['progress_bar'].update_bar(progress_value)

    elif event == 'speed_var' and values['speed_var']:
        # Validate and possibly correct the speed value when it's changed
        update_speed(window, values)

window.close()  # Close the window once the event loop is exited
