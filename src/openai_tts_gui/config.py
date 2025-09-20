import logging
import os
import platform
import sys
from importlib import metadata

from platformdirs import user_data_dir
from PyQt6.QtGui import QColor

# --- General Settings ---
APP_NAME = "OpenAI TTS"
APP_VERSION = "0.7.0"
# per-user app data directory
DATA_DIR = user_data_dir(APP_NAME, appauthor=False)
os.makedirs(DATA_DIR, exist_ok=True)
LOG_FILE = os.path.join(DATA_DIR, "tts_app.log")
PRESETS_FILE = os.path.join(DATA_DIR, "presets.json")
API_KEY_FILE = os.path.join(DATA_DIR, "api_key.enc")  # obfuscated fallback file path
# default output directory (created on demand)
DEFAULT_OUTPUT_DIR = os.path.expanduser(os.path.join("~", "Music", "OpenAI-TTS"))
os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)

# --- OpenAI Client Settings ---
OPENAI_TIMEOUT = 60.0  # seconds
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL") or None

# --- API Settings ---
TTS_MODELS = ["tts-1", "tts-1-hd", "gpt-4o-mini-tts"]
GPT_4O_MINI_TTS_MODEL = "gpt-4o-mini-tts"  # Specific model needing instructions
TTS_VOICES = [
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "fable",
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
# Optional parallelism: 1 disables, >1 enables parallel chunk generation
PARALLELISM = int(os.getenv("TTS_PARALLELISM", "1"))
PARALLELISM = max(1, min(PARALLELISM, 8))

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

# --- Theme Colors ---
# Define color palettes for themes
DARK_THEME = {
    "background": QColor("#2E2E2E"),
    "text": QColor("#FFFFFF"),
    "widget_background": QColor("#3E3E3E"),
    "button_background": QColor("#555555"),
    "button_text": QColor("#FFFFFF"),
    "border": QColor("#555555"),
    "progress_bar_chunk": QColor("#66A3FF"),
}

LIGHT_THEME = {
    "background": QColor("#FFFFFF"),
    "text": QColor("#000000"),
    "widget_background": QColor("#F0F0F0"),
    "button_background": QColor("#E0E0E0"),
    "button_text": QColor("#000000"),
    "border": QColor("#CCCCCC"),
    "progress_bar_chunk": QColor("#007BFF"),
}

# --- FFMPEG ---
# Default command, assumes ffmpeg is in PATH
FFMPEG_COMMAND = "ffmpeg"
FFMPEG_MIN_VERSION = (4, 3, 0)
# If ffmpeg is not in PATH, you might need to specify the full path:
# FFMPEG_COMMAND = "/path/to/your/ffmpeg" # Example for Linux/macOS
# FFMPEG_COMMAND = r"C:\path\to\your\ffmpeg.exe" # Example for Windows

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
DEFAULT_CODEC = "copy"  # Used if format unknown, usually safe for concat

# Force consistent output params to avoid ffmpeg/env drift
OUTPUT_SAMPLE_RATE = 48_000
OUTPUT_CHANNELS = 2
OUTPUT_BITRATE = "192k"  # where applicable
# Per-format ffmpeg parameter overrides (None means omit)
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


# Helper function to build stylesheet string
def build_stylesheet(theme):
    # Retained for fallback/non-Fluent mode. When Fluent is enabled we skip this.
    return f"""
        QWidget {{
            background-color: {theme['background'].name()};
            color: {theme['text'].name()};
        }}
        QMainWindow, QDialog {{
            background-color: {theme['background'].name()};
        }}
        QTextEdit, QLineEdit, QComboBox, QListWidget {{
            background-color: {theme['widget_background'].name()};
            color: {theme['text'].name()};
            border: 1px solid {theme['border'].name()};
            padding: 2px;
        }}
        QPushButton {{
            background-color: {theme['button_background'].name()};
            color: {theme['button_text'].name()};
            border: 1px solid {theme['border'].name()};
            padding: 5px;
            min-width: 80px;
        }}
        QPushButton:hover {{
            background-color: {theme['widget_background'].name()};
        }}
        QPushButton:pressed {{
            background-color: {theme['border'].name()};
        }}
        QMenuBar {{
            background-color: {theme['widget_background'].name()};
            color: {theme['text'].name()};
        }}
        QMenuBar::item:selected {{
            background-color: {theme['button_background'].name()};
        }}
        QMenu {{
            background-color: {theme['widget_background'].name()};
            color: {theme['text'].name()};
        }}
        QMenu::item:selected {{
            background-color: {theme['button_background'].name()};
        }}
        QProgressBar {{
            border: 1px solid {theme['border'].name()};
            text-align: center;
            color: {theme['text'].name()};
            background-color: {theme['widget_background'].name()};
        }}
        QProgressBar::chunk {{
            background-color: {theme['progress_bar_chunk'].name()};
            width: 10px; /* Or adjust as needed */
            margin: 0.5px;
        }}
        QLabel {{
             color: {theme['text'].name()}; /* Ensure labels also get the text color */
        }}
        QSplitter::handle {{
             background-color: {theme['border'].name()};
             height: 3px; /* Or width depending on orientation */
        }}
        QToolTip {{
             background-color: {theme['widget_background'].name()};
             color: {theme['text'].name()};
             border: 1px solid {theme['border'].name()};
        }}
    """


def env_snapshot():
    """Return minimal environment/library snapshot for sidecars."""
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
