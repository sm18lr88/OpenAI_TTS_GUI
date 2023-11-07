import tkinter as tk
from tkinter import filedialog, messagebox
import requests
from threading import Thread
import tiktoken

# Pricing constants
TTS_PRICE_PER_1K_CHARS = 0.015
TTS_HD_PRICE_PER_1K_CHARS = 0.030

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

def count_tokens(text, model_name='cl100k_base'):
    enc = tiktoken.get_encoding(model_name)
    tokens = enc.encode(text)
    token_count = len(tokens)
    return token_count

def estimate_price():
    text = text_box.get("1.0", tk.END)
    if not text.strip():
        messagebox.showwarning("Warning", "The text box is empty.")
        return
    
    token_count = count_tokens(text)
    num_chars = len(text)
    
    # Choose the pricing based on the model
    if model_var.get() == 'tts-1':
        price_per_1k_chars = TTS_PRICE_PER_1K_CHARS
    else:  # tts-1-hd or any other HD models
        price_per_1k_chars = TTS_HD_PRICE_PER_1K_CHARS
    
    # Calculate the price
    price = (num_chars / 1000) * price_per_1k_chars
    messagebox.showinfo("Estimate Price", f"Estimated tokens: {token_count}\nEstimated price: ${price:.2f}")

def save_speech(text, path, api_key, model, voice, response_format, speed):
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
    
    response = requests.post('https://api.openai.com/v1/audio/speech', headers=headers, json=data)
    
    if response.status_code == 200:
        with open(path, 'wb') as file:
            file.write(response.content)
        messagebox.showinfo("Success", "The TTS file has been saved.")
    else:
        messagebox.showerror("Error", f"Failed to create TTS: {response.status_code}\n{response.text}")

def select_path():
    file_path = filedialog.asksaveasfilename(defaultextension=".mp3", filetypes=[("MP3 audio file", "*.mp3")])
    if file_path:
        path_entry.delete(0, tk.END)
        path_entry.insert(0, file_path)

def create_speech():
    text = text_box.get("1.0", tk.END)
    path = path_entry.get()
    if not path:
        messagebox.showwarning("Warning", "Please select a file path to save the TTS.")
        return
    
    api_key = read_api_key()
    model = model_var.get()
    voice = voice_var.get()
    response_format = format_var.get()
    speed = speed_var.get()
    
    Thread(target=save_speech, args=(text, path, api_key, model, voice, response_format, speed)).start()

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

estimate_button = tk.Button(app, text="Estimate Price", command=estimate_price)
estimate_button.pack(side=tk.LEFT, padx=5)

create_button = tk.Button(app, text="Create TTS", command=create_speech)
create_button.pack(side=tk.LEFT)

app.mainloop()
