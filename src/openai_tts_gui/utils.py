import base64
import hashlib
import json
import logging
import os
import platform
import re
import subprocess
import time
from itertools import cycle
from pathlib import Path
from typing import Any

from . import config  # Import the configuration

keyring: Any | None
try:
    import keyring  # OS keyring (Windows Credential Manager, macOS Keychain, etc.)

    _KEYRING_AVAILABLE = True
except Exception:
    keyring: Any | None = None
    _KEYRING_AVAILABLE = False

_BOUNDARY_RE = re.compile(r"[\.?!;:](?=\s|$)")

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
        punct_match = None
        for m in _BOUNDARY_RE.finditer(chunk):
            punct_match = m
        if punct_match:
            split_index = punct_match.end()

        # If no sentence end found, try splitting at the last space
        if split_index == -1:
            split_index = chunk.rfind(" ") + 1
            if split_index == 0:
                split_index = chunk_size
                logger.warning(
                    f"Forced split at index {current_pos + split_index} without space/punctuation"
                )

        final_chunk = text[current_pos : current_pos + split_index]
        chunks.append(final_chunk)
        current_pos += len(final_chunk)  # Move position; DO NOT skip whitespace/newlines

    logger.debug(f"Text split into {len(chunks)} chunks")
    # Preserve whitespace-only chunks to keep round-trip exactness
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


def read_api_key(filename: str | None = None) -> str | None:
    """Reads and decrypts the API key from the specified file.

    If filename is None, resolves to config.API_KEY_FILE at call time.
    """
    api_key_env = os.environ.get("OPENAI_API_KEY")
    filename = filename or config.API_KEY_FILE
    if api_key_env:
        logger.info("Using API key from OPENAI_API_KEY environment variable.")
        return api_key_env

    # OS keyring (preferred when available)
    if getattr(config, "USE_KEYRING", False) and _KEYRING_AVAILABLE and keyring is not None:
        try:
            if hasattr(keyring, "get_password"):
                key = keyring.get_password("OpenAI_TTS_GUI", "OPENAI_API_KEY")
            else:
                key = None
            if key:
                logger.info("Using API key from OS keyring.")
                return key
        except Exception as e:
            logger.warning(f"Keyring read failed: {e}")

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
        with open(filename, encoding="utf-8") as file:
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
    except OSError as e:
        logger.exception(f"Error reading API key file {filename}: {e}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error reading API key file {filename}: {e}")
        return None


def save_api_key(api_key: str, filename: str | None = None) -> bool:
    """Encrypts and saves the API key to the specified file.

    If filename is None, resolves to config.API_KEY_FILE at call time.
    Returns True if either keyring save or file save succeeded.
    """
    if not api_key:
        logger.warning("Attempted to save an empty API key. Aborting.")
        return False
    filename = filename or config.API_KEY_FILE
    # Try to store in OS keyring first (best practice for Windows/macOS/Linux)
    keyring_ok = False
    if getattr(config, "USE_KEYRING", False) and _KEYRING_AVAILABLE and keyring is not None:
        try:
            if hasattr(keyring, "set_password"):
                keyring.set_password("OpenAI_TTS_GUI", "OPENAI_API_KEY", api_key)
                keyring_ok = True
                logger.info("API key saved to OS keyring (OpenAI_TTS_GUI/OPENAI_API_KEY).")
        except Exception as e:
            logger.warning(f"Failed to save API key to keyring: {e}")

    encrypted_key = encrypt_key(api_key)
    if not encrypted_key:
        logger.error("Failed to encrypt API key for saving.")
        return keyring_ok
    try:
        # Ensure parent directory exists if a path was provided
        parent = Path(filename).parent
        if str(parent):
            os.makedirs(parent, exist_ok=True)
        with open(filename, "w", encoding="utf-8") as file:
            file.write(encrypted_key + "\n")
        logger.info(f"Encrypted API key saved to {filename}")
        file_ok = True
        return file_ok or keyring_ok
    except OSError as e:
        logger.exception(f"Error saving API key to {filename}: {e}")
        return keyring_ok
    except Exception as e:
        logger.exception(f"Unexpected error saving API key to {filename}: {e}")
        return keyring_ok


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
                    logger.debug(f"Created directory for single file rename: {output_dir}")
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
                    # Use relative paths if possible.
                    # For concat robustness, prefer absolute paths with forward slashes,
                    # or careful quoting.
                    abs_path = os.path.abspath(file_path).replace("\\", "/")
                    f.write(f"file '{abs_path}'\n")
                else:
                    logger.error(f"File listed for concatenation not found: {file_path}. Skipping.")
                    # Decide: raise error or just skip? Skipping for robustness.
                    # raise FileNotFoundError(f"File missing for concatenation: {file_path}")

        # Determine codec based on output extension
        ext = os.path.splitext(output_file)[1].lower().lstrip(".")
        codec = config.CODEC_MAP.get(ext, config.DEFAULT_CODEC)
        params = config.CODEC_PARAMS.get(ext, {})

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
        ]
        # Append normalized params
        if params.get("ar"):
            concat_command += ["-ar", str(params["ar"])]
        if params.get("ac"):
            concat_command += ["-ac", str(params["ac"])]
        if params.get("b:a"):
            concat_command += ["-b:a", str(params["b:a"])]
        concat_command += [
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
            "'%s' command not found. Ensure ffmpeg is installed and in your system's PATH.",
            config.FFMPEG_COMMAND,
        )
        raise
    except subprocess.CalledProcessError as e:
        logger.error(f"ffmpeg concatenation failed with exit code {e.returncode}.")
        logger.error(f"ffmpeg stderr: {e.stderr}")
        raise  # Re-raise the error after logging
    except OSError as e:
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
                logger.error(f"Failed to remove temporary concat list {concat_list_path}: {e}")


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
        with open(filename, encoding="utf-8") as file:
            presets = json.load(file)
        logger.info(f"Loaded {len(presets)} presets from {filename}")
        return presets if isinstance(presets, dict) else {}
    except FileNotFoundError:
        logger.info(f"Presets file '{filename}' not found. Returning empty dictionary.")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from {filename}: {e}. Returning empty dictionary.")
        return {}
    except OSError as e:
        logger.exception(f"Error reading presets file {filename}: {e}. Returning empty dictionary.")
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
    except OSError as e:
        logger.exception(f"Error writing presets to {filename}: {e}")
        return False


# --- Sidecar metadata ---
def write_sidecar_metadata(output_file: str, meta: dict):
    """Writes JSON sidecar next to the audio output."""
    sidecar = output_file + ".json"
    meta = dict(meta or {})
    meta.setdefault("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    meta.setdefault("ffmpeg", get_ffmpeg_version())
    meta.setdefault("os", platform.platform())
    with open(sidecar, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    logger.info(f"Wrote sidecar metadata: {sidecar}")


def sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


# --- Preflight / FFmpeg ---
def get_ffmpeg_version() -> str:
    try:
        result = subprocess.run(
            [config.FFMPEG_COMMAND, "-version"],
            capture_output=True,
            text=True,
            check=True,
        )
        first = result.stdout.splitlines()[0].strip()
        return first
    except Exception:
        return "unknown"


def _parse_ffmpeg_semver(line: str) -> tuple[int, int, int] | None:
    # Accepts variants like:
    #  - "ffmpeg version n4.4 ..." or "ffmpeg version 6.0 ..."
    #  - "ffmpeg version 2025-08-04-git-..." (date-based nightly/dev builds)
    import re

    # Standard semver with optional leading 'n'
    m = re.search(r"version\s+(?:n)?(\d+)\.(\d+)(?:\.(\d+))?", line)
    if m:
        major, minor, patch = m.group(1), m.group(2), m.group(3) or "0"
        return int(major), int(minor), int(patch)

    # Date-based git builds (treat as very new; compare lexicographically works vs 4.3.0)
    m2 = re.search(r"version\s+(\d{4})-(\d{2})-(\d{2})-git", line)
    if m2:
        year, month, day = m2.group(1), m2.group(2), m2.group(3)
        return int(year), int(month), int(day)

    return None


def preflight_check() -> tuple[bool, str]:
    """Verify ffmpeg presence and minimum version."""
    try:
        result = subprocess.run(
            [config.FFMPEG_COMMAND, "-version"],
            capture_output=True,
            text=True,
            check=True,
        )
        first = result.stdout.splitlines()[0].strip()
        ver = _parse_ffmpeg_semver(first)
        if ver is None:
            # Many Windows builds (e.g., gyan.dev) report a date-based git version; accept as modern
            low = first.lower()
            if "git" in low or "gyan.dev" in low or "full_build" in low:
                return True, first
            # Unknown format: don't block user; assume OK but log via return message
            return True, first
        ok = tuple(ver) >= tuple(config.FFMPEG_MIN_VERSION)
        if not ok:
            min_req = ".".join(map(str, config.FFMPEG_MIN_VERSION))
            return (False, f"ffmpeg too old: found {first}, require >= {min_req}")
        return True, first
    except FileNotFoundError:
        return False, "ffmpeg not found in PATH. Please install ffmpeg."
    except subprocess.CalledProcessError as e:
        return False, f"ffmpeg invocation failed: {e}"
    except Exception as e:
        return False, f"ffmpeg check error: {e}"
