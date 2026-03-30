from __future__ import annotations

import logging
import os
import platform
import sys
from importlib import metadata
from typing import Final

from platformdirs import user_data_dir

DEFAULT_APP_VERSION: Final[str] = "1.2.0"


def _resolve_app_version() -> str:
    try:
        return metadata.version("OpenAI_TTS_GUI")
    except metadata.PackageNotFoundError:
        return DEFAULT_APP_VERSION
    except Exception:
        return DEFAULT_APP_VERSION


def _read_int_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(value, maximum))


# --- General Settings ---
APP_NAME = "OpenAI TTS"
APP_VERSION = _resolve_app_version()
# per-user app data directory
DATA_DIR = user_data_dir(APP_NAME, appauthor=False)
LOG_FILE = os.path.join(DATA_DIR, "tts_app.log")
PRESETS_FILE = os.path.join(DATA_DIR, "presets.json")
API_KEY_FILE = os.path.join(DATA_DIR, "api_key.enc")
APP_SETTINGS_FILE = os.path.join(DATA_DIR, "app_settings.json")
DEFAULT_OUTPUT_DIR = os.path.expanduser(os.path.join("~", "Music", "OpenAI-TTS"))


def ensure_directories() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)


# --- OpenAI Client Settings ---
OPENAI_TIMEOUT = 60.0  # seconds
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL") or None

# --- API Settings ---
TTS_MODELS = ["tts-1", "tts-1-hd", "gpt-4o-mini-tts"]
GPT_4O_MINI_TTS_MODEL = "gpt-4o-mini-tts"
TTS_VOICES = [
    "alloy",
    "ash",
    "ballad",
    "cedar",
    "coral",
    "echo",
    "fable",
    "marin",
    "onyx",
    "nova",
    "sage",
    "shimmer",
    "verse",
]
TTS_FORMATS = ["mp3", "opus", "aac", "flac", "wav", "pcm"]
DEFAULT_SPEED = 1.0
MIN_SPEED = 0.25
MAX_SPEED = 4.0
MAX_CHUNK_SIZE = 4096
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

# Force raw audio streaming instead of SSE; keep configurable for advanced users
STREAM_FORMAT = os.getenv("TTS_STREAM_FORMAT", "audio") or "audio"
if STREAM_FORMAT not in {"audio", "sse"}:
    STREAM_FORMAT = "audio"

# Optional parallelism: 1 disables, >1 enables parallel chunk generation
PARALLELISM = _read_int_env("TTS_PARALLELISM", 1, minimum=1, maximum=8)

# --- Encryption Key (Simple Obfuscation) ---
# WARNING: This is NOT cryptographically secure. It only obfuscates the key.
# Anyone with access to the source code can easily decrypt the key.
# For stronger security, consider using OS keyring or a more robust encryption library.
OBFUSCATION_KEY = b"my_simple_secret_key_for_xor"  # CHANGE THIS TO SOMETHING ELSE
USE_KEYRING = True  # Store API key in OS keyring when available

# --- UI Settings ---
DEFAULT_WINDOW_WIDTH = 700
DEFAULT_WINDOW_HEIGHT = 500
FLUENT_ENABLED = True  # enable Fluent theming/widgets

# --- FFMPEG ---
FFMPEG_COMMAND = "ffmpeg"
FFMPEG_MIN_VERSION = (4, 3, 0)

# --- File Mappings ---
FORMAT_EXTENSION_MAP = {
    "mp3": ".mp3",
    "opus": ".opus",
    "aac": ".aac",
    "flac": ".flac",
    "wav": ".wav",
    "pcm": ".pcm",
}

# Fluent accent color (used by qfluentwidgets when theming)
# Keep it consistent with the dark theme progress color by default.
FLUENT_ACCENT_HEX = "#66A3FF"

FORMAT_FILTER_MAP = {
    "mp3": "MP3 Files (*.mp3)",
    "opus": "Opus Files (*.opus)",
    "aac": "AAC Files (*.aac)",
    "flac": "FLAC Files (*.flac)",
    "wav": "WAV Files (*.wav)",
    "pcm": "PCM (raw) Files (*.pcm)",
    "all": "All Files (*.*)",
}

CODEC_MAP = {
    "mp3": "libmp3lame",
    "flac": "flac",
    "aac": "aac",
    "opus": "libopus",
    "wav": "pcm_s16le",
    "pcm": "pcm_s16le",
}
DEFAULT_CODEC = "copy"

# Force consistent output params to avoid ffmpeg/env drift
OUTPUT_SAMPLE_RATE = 48_000
OUTPUT_CHANNELS = 2
OUTPUT_BITRATE = "192k"
CODEC_PARAMS = {
    "mp3": {"ar": OUTPUT_SAMPLE_RATE, "ac": OUTPUT_CHANNELS, "b:a": OUTPUT_BITRATE},
    "aac": {"ar": OUTPUT_SAMPLE_RATE, "ac": OUTPUT_CHANNELS, "b:a": OUTPUT_BITRATE},
    "opus": {"ar": OUTPUT_SAMPLE_RATE, "ac": OUTPUT_CHANNELS, "b:a": OUTPUT_BITRATE},
    "flac": {"ar": OUTPUT_SAMPLE_RATE, "ac": OUTPUT_CHANNELS, "b:a": None},
    "wav": {"ar": OUTPUT_SAMPLE_RATE, "ac": OUTPUT_CHANNELS, "b:a": None},
    "pcm": {"ar": OUTPUT_SAMPLE_RATE, "ac": OUTPUT_CHANNELS, "b:a": None},
}

# --- Logging ---
LOGGING_LEVEL = logging.DEBUG
LOGGING_FORMAT = "%(asctime)s:%(levelname)s:%(name)s:%(message)s"


def env_snapshot() -> dict[str, str]:
    """Return a minimal environment/library snapshot for sidecars."""
    try:
        openai_ver = metadata.version("openai")
    except Exception:
        openai_ver = "unknown"
    try:
        pyqt_ver = metadata.version("PyQt6")
    except Exception:
        pyqt_ver = "unknown"
    return {
        "app_name": APP_NAME,
        "app_version": APP_VERSION,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "openai": openai_ver,
        "pyqt6": pyqt_ver,
    }
