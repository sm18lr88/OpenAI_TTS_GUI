import os
import subprocess
import requests
import time
import logging
from decimal import Decimal

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


def split_text(text, chunk_size=4096):
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    while text:
        if len(text) <= chunk_size:
            chunks.append(text)
            break
        split_index = -1
        for punct in [".", "?", "!", ";"]:
            last_punct_index = text[:chunk_size].rfind(punct)
            if last_punct_index != -1:
                split_index = max(split_index, last_punct_index + 1)
                break
        if split_index == -1:
            split_index = text[:chunk_size].rfind(" ")
        if split_index == -1:
            split_index = chunk_size
        chunks.append(text[:split_index])
        text = text[split_index:].lstrip()
    return chunks


def estimate_price(char_count, hd=False):
    if char_count == 0:
        return 0.000
    token_price = TTS_PRICE_PER_1K_CHARS if not hd else TTS_HD_PRICE_PER_1K_CHARS
    char_blocks = (char_count + 4095) // 4096  # Correct chunk size
    total_price = char_blocks * token_price
    return round(total_price, 3)


def read_api_key():
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        return api_key
    try:
        with open("api_key.txt", "r") as file:
            return file.read().strip()
    except FileNotFoundError:
        return None


def save_api_key(api_key):
    with open("api_key.txt", "w") as file:
        file.write(api_key)


def concatenate_audio_files(file_list, output_file):
    if len(file_list) == 1:
        os.rename(file_list[0], output_file)
        logging.info(f"Renamed single chunk to {output_file}")
        return

    try:
        output_dir = os.path.dirname(output_file)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        concat_list_path = os.path.join(output_dir, "concat_list.txt")

        with open(concat_list_path, "w") as f:
            for file_path in file_list:
                if os.path.exists(file_path):
                    f.write(f"file '{file_path}'\n")
                else:
                    logging.error(
                        f"File {file_path} does not exist and will not be concatenated."
                    )

        output_extension = os.path.splitext(output_file)[1].lower()
        if output_extension == ".mp3":
            codec = "libmp3lame"
        elif output_extension == ".flac":
            codec = "flac"
        elif output_extension == ".aac":
            codec = "aac"
        elif output_extension == ".opus":
            codec = "libopus"
        else:
            codec = "copy"

        concat_command = [
            "ffmpeg",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_list_path,
            "-c:a",
            codec,
            output_file,
        ]

        logging.info(f"Running ffmpeg command: {' '.join(concat_command)}")
        result = subprocess.run(
            concat_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        logging.info(result.stdout.decode())
        logging.error(result.stderr.decode())
        os.remove(concat_list_path)
        logging.info(f"Concatenated audio files into {output_file}")
    except Exception as e:
        logging.error(f"Error in concatenating audio files: {e}")


def rate_limited_request(api_key, data, model):
    last_request_time = 0
    min_interval = 60 / 50
    if "hd" in model:
        min_interval = 60 / 3

    elapsed = time.time() - last_request_time
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)
    response = requests.post(
        "https://api.openai.com/v1/audio/speech",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=data,
    )
    last_request_time = time.time()
    return response


def cleanup_files(file_list, retain_files):
    if not retain_files:
        for file in file_list:
            if os.path.exists(file):
                try:
                    os.remove(file)
                    logging.info(f"Deleted temporary file {file}")
                except Exception as e:
                    logging.error(f"Failed to delete temporary file {file}: {e}")
            else:
                logging.error(
                    f"Temporary file {file} does not exist and cannot be deleted."
                )
