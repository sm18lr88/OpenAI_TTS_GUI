import logging
import tkinter as tk
from tkinter import filedialog, messagebox
import requests
import os
from pydub import AudioSegment
from threading import Thread
import math
import subprocess
import time

# Set up logging
logging.basicConfig(filename='tts_app.log', level=logging.DEBUG,
                    format='%(asctime)s:%(levelname)s:%(message)s')

# Constants
TTS_PRICE_PER_1K_CHARS = 0.015
TTS_HD_PRICE_PER_1K_CHARS = 0.030
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

def read_api_key():
    try:
        with open('api_key.txt', 'r') as file:
            return file.read().strip()
    except FileNotFoundError:
        messagebox.showerror("Error", "API key file 'api_key.txt' not found.")
        return None
    except Exception as e:
        messagebox.showerror("Error", str(e))
        return None

def estimate_price(text_length, hd=False):
    token_price = TTS_PRICE_PER_1K_CHARS if not hd else TTS_HD_PRICE_PER_1K_CHARS
    return math.ceil(text_length / 1000) * token_price

def estimate_price_button_action():
    text = text_box.get("1.0", tk.END)
    if not text.strip():
        messagebox.showwarning("Warning", "The text box is empty.")
        return
    num_chars = len(text)
    hd = 'hd' in model_var.get()
    price = estimate_price(num_chars, hd)
    messagebox.showinfo("Estimate Price", f"Estimated price: ${price:.2f}")

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

def select_path():
    file_path = filedialog.asksaveasfilename(
        defaultextension=".mp3",
        filetypes=[
            ("MP3 audio file", "*.mp3"),
            ("WAV audio file", "*.wav"),
            ("FLAC audio file", "*.flac"),
            ("AAC audio file", "*.aac")
        ]
    )
    if file_path:
        path_entry.delete(0, tk.END)
        path_entry.insert(0, file_path)

def create_speech():
    text = text_box.get("1.0", tk.END).strip()
    if not text:
        messagebox.showwarning("Warning", "Please enter some text.")
        return
    path = path_entry.get()
    if not path:
        messagebox.showwarning("Warning", "Please select a file path to save the TTS.")
        return
    api_key = read_api_key()
    if not api_key:
        return
    model = model_var.get()
    voice = voice_var.get()
    response_format = format_var.get()
    speed = speed_var.get()
    hd = 'hd' in model
    chunks = split_text(text)
    estimated_price = estimate_price(len(text), hd)
    if not messagebox.askokcancel(
        "Price Estimate",
        f"The estimated cost for this TTS is ${estimated_price:.2f}. Do you want to continue?"
    ):
        return
    Thread(target=process_speech, args=(chunks, path, api_key, model, voice, response_format, speed)).start()

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
            app.after(0, cleanup_files, temp_files)
            return
    app.after(0, concatenate_audio_files, temp_files, path)

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
                    app.after(0, messagebox.showerror, "Error",
                              f"Received empty audio content for chunk {filename}.")
                    return False
                with open(filename, 'wb') as file:
                    file.write(response.content)
                return True
            elif response.status_code == 429 or response.status_code >= 500:
                logging.warning(f"Received status code {response.status_code}. Retrying after delay.")
                time.sleep(RETRY_DELAY * (2 ** attempt))
            else:
                logging.error(f"Failed to create TTS for chunk {filename}: {response.status_code}\n{response.text}")
                app.after(0, messagebox.showerror, "Error",
                          f"Failed to create TTS for chunk {filename}: {response.status_code}\n{response.text}")
                return False
        except requests.RequestException as e:
            logging.exception("Network error occurred.")
            if attempt < MAX_RETRIES - 1:
                logging.info(f"Retrying... Attempt {attempt + 1}")
                time.sleep(RETRY_DELAY)
            else:
                app.after(0, messagebox.showerror, "Error", f"Network error occurred: {e}")
                return False

def cleanup_files(file_list):
    for file in file_list:
        try:
            os.remove(file)
        except Exception as e:
            logging.error(f"Failed to delete temporary file {file}: {e}")

# GUI setup
app = tk.Tk()
app.title("OpenAI TTS")

model_var = tk.StringVar(value='tts-1')
voice_var = tk.StringVar(value='alloy')
format_var = tk.StringVar(value='mp3')
speed_var = tk.DoubleVar(value=1.0)

text_box = tk.Text(app, height=10, width=50)
text_box.pack()

path_entry = tk.Entry(app, width=50)
path_entry.pack()

select_path_button = tk.Button(app, text="Select Path", command=select_path)
select_path_button.pack()

settings_frame = tk.LabelFrame(app, text="Settings")
settings_frame.pack(fill="x", padx=5, pady=5)

tk.Label(settings_frame, text="Model:").pack(side=tk.LEFT)
model_menu = tk.OptionMenu(settings_frame, model_var, 'tts-1', 'tts-1-hd')
model_menu.pack(side=tk.LEFT, padx=5)

tk.Label(settings_frame, text="Voice:").pack(side=tk.LEFT)
voice_menu = tk.OptionMenu(settings_frame, voice_var, 'alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer')
voice_menu.pack(side=tk.LEFT, padx=5)

tk.Label(settings_frame, text="Format:").pack(side=tk.LEFT)
format_menu = tk.OptionMenu(settings_frame, format_var, 'mp3', 'opus', 'aac', 'flac')
format_menu.pack(side=tk.LEFT, padx=5)

tk.Label(settings_frame, text="Speed:").pack(side=tk.LEFT)
speed_menu = tk.OptionMenu(settings_frame, speed_var, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 3.5, 4.0)
speed_menu.pack(side=tk.LEFT, padx=5)

estimate_button = tk.Button(app, text="Estimate Price", command=estimate_price_button_action)
estimate_button.pack(side=tk.LEFT, padx=5)

create_button = tk.Button(app, text="Create TTS", command=create_speech)
create_button.pack(side=tk.LEFT)

app.mainloop()
