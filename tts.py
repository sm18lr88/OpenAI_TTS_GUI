import os
import requests
import time
import logging
from threading import Thread
from decimal import Decimal
from PyQt6.QtWidgets import QMessageBox
from utils import (
    split_text,
    estimate_price,
    read_api_key,
    concatenate_audio_files,
    cleanup_files,
    rate_limited_request,
)

# Constants for price and API calls
TTS_PRICE_PER_1K_CHARS = Decimal("0.015")
TTS_HD_PRICE_PER_1K_CHARS = Decimal("0.030")
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

logging.basicConfig(
    filename="tts_app.log",
    level=logging.DEBUG,
    format="%(asctime)s:%(levelname)s:%(message)s",
)


def create_tts(values, window):
    text = values["text_box"].strip()
    path = values["path_entry"]
    if not path or not os.path.isdir(os.path.dirname(path)):
        window.show_message("Invalid path")
        return
    api_key = read_api_key()
    if not api_key:
        window.show_message(
            "No API key found. Set the API key in the environment variable or the app's settings."
        )
        return
    model = values["model_var"]
    voice = values["voice_var"]
    response_format = values["format_var"]
    speed = float(values["speed_var"]) if values["speed_var"] else 1.0
    hd = "hd" in model
    char_count = len(text)
    estimated_price = estimate_price(char_count, hd)
    retain_files = values["retain_files"]

    msg_box = QMessageBox()
    msg_box.setText(
        f"The estimated cost for this TTS is ${estimated_price:.3f}. Do you want to continue?"
    )
    msg_box.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    result = msg_box.exec()

    if result == QMessageBox.StandardButton.Yes:
        window.progress_updated.emit(1)  # Set progress to 1% when starting
        Thread(
            target=process_speech,
            args=(
                split_text(text),
                path,
                api_key,
                model,
                voice,
                response_format,
                speed,
                retain_files,
                window,
            ),
        ).start()


def process_speech(
    chunks, path, api_key, model, voice, response_format, speed, retain_files, window
):
    temp_files = []
    total_chunks = len(chunks)
    for i, chunk in enumerate(chunks):
        progress = (i / total_chunks) * 100
        window.progress_updated.emit(progress)
        temp_filename = os.path.join(
            os.path.dirname(path),
            f"{os.path.splitext(os.path.basename(path))[0]}_{i}.{response_format}",
        )
        temp_files.append(temp_filename)
        if not save_chunk(
            chunk, temp_filename, api_key, model, voice, response_format, speed
        ):
            cleanup_files(temp_files, retain_files)
            return
    concatenate_audio_files(temp_files, path)
    window.progress_updated.emit(100)
    if not retain_files:
        cleanup_files(temp_files, retain_files)


def save_chunk(text, filename, api_key, model, voice, response_format, speed):
    data = {
        "model": model,
        "input": text,
        "voice": voice,
        "response_format": response_format,
        "speed": speed,
    }
    for attempt in range(MAX_RETRIES):
        try:
            response = rate_limited_request(api_key, data, model)
            if response.status_code == 200:
                if len(response.content) == 0:
                    logging.error(f"Received empty audio content for chunk {filename}.")
                    return False
                with open(filename, "wb") as file:
                    file.write(response.content)
                logging.info(f"Saved chunk to {filename}")
                return True
            elif response.status_code in [429, 500, 502, 503, 504]:
                logging.warning(
                    f"Received status code {response.status_code}. Retrying after delay."
                )
                time.sleep(RETRY_DELAY * (attempt + 1))
            else:
                logging.error(
                    f"Failed to create TTS for chunk {filename}: {response.status_code}\n{response.text}"
                )
                return False
        except requests.RequestException as e:
            logging.exception(f"Network error occurred on attempt {attempt + 1}: {e}")
            time.sleep(RETRY_DELAY * (attempt + 1))
    return False
