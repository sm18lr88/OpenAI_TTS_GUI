import os
import subprocess
import json
import logging
import base64
from itertools import cycle

import config  # Import the configuration

# Setup logger for this module
logger = logging.getLogger(__name__)

# --- Text Processing ---


def split_text(text, chunk_size=config.MAX_CHUNK_SIZE):
    """
    Split text into chunks, respecting sentence boundaries where possible.

    Args:
        text (str): The input text.
        chunk_size (int): The maximum size of each chunk.

    Returns:
        list[str]: A list of text chunks.
    """
    logger.debug(f"Splitting text of length {len(text)} with chunk_size {chunk_size}")
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    current_pos = 0
    text_len = len(text)

    while current_pos < text_len:
        end_pos = min(current_pos + chunk_size, text_len)
        chunk = text[current_pos:end_pos]

        if end_pos == text_len:
            chunks.append(chunk)
            break

        # Try to find the last sentence-ending punctuation within the chunk
        split_index = -1
        best_punct_index = -1
        for punct in [".", "?", "!", ";", ":"]:
            try:
                # Find the last occurrence of the punctuation
                last_punct_index = chunk.rindex(punct)
                # Ensure it's followed by space or newline, or is at the very end
                if last_punct_index + 1 < len(chunk):
                    if chunk[last_punct_index + 1].isspace():
                        best_punct_index = max(best_punct_index, last_punct_index)
                elif last_punct_index + 1 == len(
                    chunk
                ):  # Punctuation at the end of chunk
                    best_punct_index = max(best_punct_index, last_punct_index)

            except ValueError:
                continue  # Punctuation not found in this chunk

        if best_punct_index != -1:
            split_index = best_punct_index + 1  # Split after the punctuation

        # If no sentence end found, try splitting at the last space
        if split_index == -1:
            try:
                space_index = chunk.rindex(" ")
                split_index = space_index + 1  # Split after the space
            except ValueError:
                # No space found, force split at chunk_size
                split_index = chunk_size
                logger.warning(
                    f"Forced split at index {current_pos + split_index} without space/punctuation"
                )

        final_chunk = text[current_pos : current_pos + split_index]
        chunks.append(final_chunk)
        current_pos += len(final_chunk)  # Move position past the extracted chunk
        # Skip leading whitespace for the next chunk
        while current_pos < text_len and text[current_pos].isspace():
            current_pos += 1

    logger.debug(f"Text split into {len(chunks)} chunks")
    # Filter out any potentially empty chunks created by splitting logic
    chunks = [c for c in chunks if c.strip()]
    return chunks


# --- API Key Obfuscation (Simple XOR) ---
# WARNING: This provides minimal security through obfuscation only.


def _xor_cipher(data, key):
    """Applies XOR cipher using the provided key."""
    return bytes(a ^ b for a, b in zip(data, cycle(key)))


def encrypt_key(api_key: str) -> str:
    """Obfuscates the API key using XOR and Base64 encodes it."""
    if not api_key:
        return ""
    try:
        key_bytes = api_key.encode("utf-8")
        encrypted_bytes = _xor_cipher(key_bytes, config.OBFUSCATION_KEY)
        return base64.urlsafe_b64encode(encrypted_bytes).decode("utf-8")
    except Exception as e:
        logger.error(f"Error encrypting API key: {e}")
        return ""  # Return empty on error


def decrypt_key(encrypted_key: str) -> str:
    """De-obfuscates the API key."""
    if not encrypted_key:
        return ""
    try:
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_key.encode("utf-8"))
        decrypted_bytes = _xor_cipher(encrypted_bytes, config.OBFUSCATION_KEY)
        return decrypted_bytes.decode("utf-8")
    except Exception as e:
        logger.error(f"Error decrypting API key: {e}")
        return ""  # Return empty on error


# --- File Operations ---


def read_api_key(filename=config.API_KEY_FILE) -> str | None:
    """Reads and decrypts the API key from the specified file."""
    api_key_env = os.environ.get("OPENAI_API_KEY")
    if api_key_env:
        logger.info("Using API key from OPENAI_API_KEY environment variable.")
        return api_key_env

    if not os.path.exists(filename):
        logger.warning(f"API key file '{filename}' not found.")
        # Optionally create an empty or example file here if desired
        # try:
        #     with open(filename, "w") as f:
        #         f.write(encrypt_key("sk-your_example_api_key_here")) # Store example encrypted
        #     logger.info(f"Created example API key file: {filename}")
        # except IOError as e:
        #     logger.error(f"Could not create example API key file {filename}: {e}")
        return None

    try:
        with open(filename, "r", encoding="utf-8") as file:
            encrypted_key = file.readline().strip()
        if not encrypted_key:
            logger.warning(f"API key file '{filename}' is empty.")
            return None

        decrypted_key = decrypt_key(encrypted_key)
        if decrypted_key:
            logger.debug(f"Read and decrypted API key from {filename}")
            return decrypted_key
        else:
            logger.error(f"Failed to decrypt API key from {filename}.")
            return None
    except IOError as e:
        logger.exception(f"Error reading API key file {filename}: {e}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error reading API key file {filename}: {e}")
        return None


def save_api_key(api_key: str, filename=config.API_KEY_FILE):
    """Encrypts and saves the API key to the specified file."""
    if not api_key:
        logger.warning("Attempted to save an empty API key. Aborting.")
        return False
    encrypted_key = encrypt_key(api_key)
    if not encrypted_key:
        logger.error("Failed to encrypt API key for saving.")
        return False
    try:
        with open(filename, "w", encoding="utf-8") as file:
            file.write(encrypted_key + "\n")
        logger.info(f"Encrypted API key saved to {filename}")
        return True
    except IOError as e:
        logger.exception(f"Error saving API key to {filename}: {e}")
        return False
    except Exception as e:
        logger.exception(f"Unexpected error saving API key to {filename}: {e}")
        return False


def concatenate_audio_files(file_list: list[str], output_file: str):
    """
    Concatenates audio files using ffmpeg.

    Args:
        file_list (list[str]): List of paths to audio files to concatenate.
        output_file (str): Path to the final output audio file.

    Raises:
        FileNotFoundError: If ffmpeg command is not found.
        subprocess.CalledProcessError: If ffmpeg fails.
        IOError: If file list cannot be written or output directory cannot be created.
        Exception: For other unexpected errors.
    """
    logger.info(f"Attempting to concatenate {len(file_list)} files into {output_file}")
    if not file_list:
        logger.warning("No files provided for concatenation.")
        return

    # Handle single file case by renaming
    if len(file_list) == 1:
        try:
            if os.path.exists(file_list[0]):
                # Ensure output directory exists before renaming
                output_dir = os.path.dirname(output_file)
                if output_dir and not os.path.exists(output_dir):
                    os.makedirs(output_dir, exist_ok=True)
                    logger.debug(
                        f"Created directory for single file rename: {output_dir}"
                    )
                # Overwrite if exists
                if os.path.exists(output_file):
                    os.remove(output_file)
                os.rename(file_list[0], output_file)
                logger.info(f"Renamed single file '{file_list[0]}' to '{output_file}'")
            else:
                logger.error(f"Single input file not found: {file_list[0]}")
                raise FileNotFoundError(f"Input file missing: {file_list[0]}")
            return
        except OSError as e:
            logger.exception(
                f"Failed to rename single file '{file_list[0]}' to '{output_file}': {e}"
            )
            raise

    # Proceed with ffmpeg for multiple files
    output_dir = os.path.dirname(output_file) or "."
    concat_list_path = os.path.join(output_dir, "concat_list.txt")

    try:
        # Ensure output directory exists
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
            logger.debug(f"Created output directory {output_dir}")

        # Create the concatenation list file
        with open(concat_list_path, "w", encoding="utf-8") as f:
            for file_path in file_list:
                # Check if the file actually exists before adding to list
                if os.path.exists(file_path):
                    # Use relative paths if possible, ensure correct quoting/escaping for ffmpeg
                    # Simplest robust way is often absolute paths with forward slashes or careful quoting
                    abs_path = os.path.abspath(file_path).replace("\\", "/")
                    f.write(f"file '{abs_path}'\n")
                else:
                    logger.error(
                        f"File listed for concatenation not found: {file_path}. Skipping."
                    )
                    # Decide: raise error or just skip? Skipping for robustness.
                    # raise FileNotFoundError(f"File missing for concatenation: {file_path}")

        # Determine codec based on output extension
        ext = os.path.splitext(output_file)[1].lower().lstrip(".")
        codec = config.CODEC_MAP.get(ext, config.DEFAULT_CODEC)

        # Build ffmpeg command
        # Use -y to overwrite output without asking
        concat_command = [
            config.FFMPEG_COMMAND,
            "-y",  # Overwrite output file if it exists
            "-f",
            "concat",
            "-safe",
            "0",  # Allows absolute paths in concat list
            "-i",
            concat_list_path,
            "-c:a",
            codec,
            output_file,
        ]
        logger.info(f"Executing ffmpeg: {' '.join(concat_command)}")

        # Run ffmpeg
        result = subprocess.run(
            concat_command,
            check=True,  # Raise CalledProcessError on failure
            capture_output=True,  # Capture stdout/stderr
            text=True,  # Decode stdout/stderr as text
        )
        logger.debug(f"ffmpeg stdout: {result.stdout}")
        logger.debug(
            f"ffmpeg stderr: {result.stderr}"
        )  # Log stderr as well, often contains useful info
        logger.info(f"Successfully concatenated files to {output_file}")

    except FileNotFoundError:
        logger.error(
            f"'{config.FFMPEG_COMMAND}' command not found. Ensure ffmpeg is installed and in your system's PATH."
        )
        raise
    except subprocess.CalledProcessError as e:
        logger.error(f"ffmpeg concatenation failed with exit code {e.returncode}.")
        logger.error(f"ffmpeg stderr: {e.stderr}")
        raise  # Re-raise the error after logging
    except IOError as e:
        logger.exception(f"File I/O error during concatenation setup: {e}")
        raise
    except Exception as e:
        logger.exception(f"Unexpected error during audio concatenation: {e}")
        raise
    finally:
        # Clean up the temporary list file regardless of success or failure
        if os.path.exists(concat_list_path):
            try:
                os.remove(concat_list_path)
                logger.debug(f"Removed temporary concat list: {concat_list_path}")
            except OSError as e:
                logger.error(
                    f"Failed to remove temporary concat list {concat_list_path}: {e}"
                )


def cleanup_files(file_list: list[str]):
    """Removes temporary files."""
    logger.info(f"Cleaning up {len(file_list)} temporary files.")
    for file_path in file_list:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.debug(f"Deleted temporary file: {file_path}")
            except OSError as e:
                logger.error(f"Failed to delete temporary file {file_path}: {e}")
        else:
            logger.warning(f"Temporary file not found for deletion: {file_path}")


# --- Presets Management ---


def load_presets(filename=config.PRESETS_FILE) -> dict:
    """Loads instruction presets from a JSON file."""
    try:
        with open(filename, "r", encoding="utf-8") as file:
            presets = json.load(file)
        logger.info(f"Loaded {len(presets)} presets from {filename}")
        return presets if isinstance(presets, dict) else {}
    except FileNotFoundError:
        logger.info(f"Presets file '{filename}' not found. Returning empty dictionary.")
        return {}
    except json.JSONDecodeError as e:
        logger.error(
            f"Error decoding JSON from {filename}: {e}. Returning empty dictionary."
        )
        return {}
    except IOError as e:
        logger.exception(
            f"Error reading presets file {filename}: {e}. Returning empty dictionary."
        )
        return {}
    except Exception as e:
        logger.exception(
            f"Unexpected error loading presets from {filename}: {e}. Returning empty dictionary."
        )
        return {}


def save_presets(presets: dict, filename=config.PRESETS_FILE):
    """Saves instruction presets to a JSON file."""
    try:
        with open(filename, "w", encoding="utf-8") as file:
            json.dump(presets, file, indent=4)
        logger.info(f"Saved {len(presets)} presets to {filename}")
        return True
    except IOError as e:
        logger.exception(f"Error writing presets to {filename}: {e}")
        return False
    except TypeError as e:  # Handle cases where presets is not serializable
        logger.exception(f"Error serializing presets data: {e}")
        return False
    except Exception as e:
        logger.exception(f"Unexpected error saving presets to {filename}: {e}")
        return False
