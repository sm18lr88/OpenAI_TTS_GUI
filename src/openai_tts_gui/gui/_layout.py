from textwrap import dedent

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QDoubleValidator
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMenuBar,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..config import settings
from ..core.ffmpeg import get_ffmpeg_version


def build_text_area(window) -> QWidget:
    w = QWidget()
    layout = QVBoxLayout(w)
    layout.setContentsMargins(12, 12, 12, 8)
    layout.setSpacing(8)

    layout.addWidget(QLabel("Text for TTS:"))
    window.text_edit = QTextEdit()
    window.text_edit.setPlaceholderText("Enter the text you want to convert to speech...")
    layout.addWidget(window.text_edit)

    counts = QHBoxLayout()
    window.char_count_label = QLabel("Character Count: 0")
    window.chunk_count_label = QLabel(f"Chunks (max {settings.MAX_CHUNK_SIZE} chars): 0")
    counts.addWidget(window.char_count_label)
    counts.addStretch()
    counts.addWidget(window.chunk_count_label)
    layout.addLayout(counts)
    return w


def build_controls_area(window) -> QWidget:
    w = QWidget()
    layout = QVBoxLayout(w)
    layout.setContentsMargins(12, 8, 12, 12)
    layout.setSpacing(10)

    row = QHBoxLayout()
    row.addWidget(QLabel("Model:"))
    window.model_combo = QComboBox()
    window.model_combo.addItems(settings.TTS_MODELS)
    row.addWidget(window.model_combo)

    row.addWidget(QLabel("Voice:"))
    window.voice_combo = QComboBox()
    window.voice_combo.addItems(settings.TTS_VOICES)
    row.addWidget(window.voice_combo)

    row.addWidget(QLabel("Speed:"))
    window.speed_input = QLineEdit(str(settings.DEFAULT_SPEED))
    window.speed_input.setValidator(
        QDoubleValidator(settings.MIN_SPEED, settings.MAX_SPEED, 2, window)
    )
    window.speed_input.setMaximumWidth(60)
    row.addWidget(window.speed_input)

    row.addWidget(QLabel("Format:"))
    window.format_combo = QComboBox()
    window.format_combo.addItems(settings.TTS_FORMATS)
    row.addWidget(window.format_combo)
    layout.addLayout(row)

    instr_row = QHBoxLayout()
    left = QVBoxLayout()
    window.instructions_label = QLabel("Instructions:")
    window.manage_presets_button = QPushButton("Presets")
    left.addWidget(window.instructions_label)
    left.addWidget(window.manage_presets_button)
    left.addStretch()
    instr_row.addLayout(left)

    window.instructions_edit = QTextEdit()
    window.instructions_edit.setPlaceholderText(
        f"Provide guidance on voice/tone/pacing "
        f"(only affects '{settings.GPT_4O_MINI_TTS_MODEL}')..."
    )
    window.instructions_edit.setMinimumHeight(60)
    window.instructions_edit.setSizePolicy(
        QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
    )
    instr_row.addWidget(window.instructions_edit, 1)
    layout.addLayout(instr_row, 1)

    path_row = QHBoxLayout()
    path_row.addWidget(QLabel("Save As:"))
    window.path_entry = QLineEdit()
    window.path_entry.setPlaceholderText("Select output file path...")
    path_row.addWidget(window.path_entry)
    window.select_path_button = QPushButton("Browse...")
    path_row.addWidget(window.select_path_button)
    layout.addLayout(path_row)

    action_row = QHBoxLayout()
    window.progress_bar = QProgressBar()
    window.progress_bar.setValue(0)
    action_row.addWidget(window.progress_bar)

    window.create_button = QPushButton("Create TTS")
    window.create_button.setObjectName("primaryButton")
    action_row.addWidget(window.create_button)
    window.copy_ids_button = QPushButton("Copy Request IDs")
    window.copy_ids_button.setEnabled(False)
    window.copy_ids_button.clicked.connect(window._copy_request_ids)
    action_row.addWidget(window.copy_ids_button)
    layout.addLayout(action_row)

    return w


def build_about_page(window) -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(16)

    window.about_text = QTextBrowser()
    window.about_text.setOpenExternalLinks(True)
    window.about_text.setReadOnly(True)
    layout.addWidget(window.about_text)

    back_row = QHBoxLayout()
    back_row.addStretch()
    window.open_log_button = QPushButton("Open Log Folder")
    window.open_log_button.clicked.connect(
        lambda: window._open_containing_folder(settings.LOG_FILE)
    )
    back_row.addWidget(window.open_log_button)
    window.about_back_button = QPushButton("Back to Application")
    window.about_back_button.clicked.connect(window._show_main_page)
    back_row.addWidget(window.about_back_button)
    layout.addLayout(back_row)
    return page


def build_central_widget(window) -> QStackedWidget:
    splitter = QSplitter(Qt.Orientation.Vertical)
    splitter.addWidget(build_text_area(window))
    splitter.addWidget(build_controls_area(window))
    splitter.setSizes([int(window.height() * 0.6), int(window.height() * 0.4)])

    window.about_page = build_about_page(window)

    stack = QStackedWidget()
    stack.addWidget(splitter)
    stack.addWidget(window.about_page)
    return stack


def build_menubar(window):
    menubar: QMenuBar | None = window.menuBar()
    if menubar is None:
        return

    settings_menu: QMenu | None = menubar.addMenu("Settings")
    window.retain_files_action = QAction("Retain intermediate chunk files", window)
    window.retain_files_action.setCheckable(True)
    if settings_menu is not None:
        settings_menu.addAction(window.retain_files_action)

    api_menu: QMenu | None = menubar.addMenu("API Key")
    reload_action = QAction("Reload from secure store", window)
    reload_action.triggered.connect(window._load_api_key_from_file)
    set_key_action = QAction("Set/Update API Key...", window)
    set_key_action.triggered.connect(window._set_custom_api_key)
    if api_menu is not None:
        api_menu.addAction(reload_action)
        api_menu.addAction(set_key_action)

    help_menu: QMenu | None = menubar.addMenu("Help")
    about_action = QAction("About", window)
    about_action.triggered.connect(window._show_about_page)
    back_action = QAction("Back to Application", window)
    back_action.triggered.connect(window._show_main_page)
    if help_menu is not None:
        help_menu.addAction(about_action)
        help_menu.addAction(back_action)


def about_html() -> str:
    snap = settings.env_snapshot()
    ffv = get_ffmpeg_version() or "Unavailable"
    return dedent(f"""
        <h2>{settings.APP_NAME} {settings.APP_VERSION}</h2>
        <p>
            OpenAI TTS GUI converts text into speech via OpenAI's TTS service.
            Fine-tune voices, models, and export formats without scripting.
        </p>
        <h3>Highlights</h3>
        <ul>
            <li>Pick an OpenAI voice, tweak speed, and export in your preferred format.</li>
            <li>Save reusable instruction presets for guidance-capable models.</li>
            <li>Monitor generation progress and optionally keep intermediate chunks.</li>
        </ul>
        <h3>Quick Tips</h3>
        <ul>
            <li>Add the API key under <em>API Key &gt; Set/Update</em>.</li>
            <li>Use the preset manager to store prompt snippets.</li>
            <li>See README.md for workflow examples.</li>
        </ul>
        <h3>Environment</h3>
        <ul>
            <li><strong>Python</strong>: {snap.get("python") or "Unknown"}</li>
            <li><strong>Platform</strong>: {snap.get("platform") or "Unknown"}</li>
            <li><strong>OpenAI</strong>: {snap.get("openai") or "Unknown"}</li>
            <li><strong>PyQt6</strong>: {snap.get("pyqt6") or "Unknown"}</li>
            <li><strong>FFmpeg</strong>: {ffv}</li>
            <li><strong>Log</strong>: <code>{settings.LOG_FILE}</code></li>
            <li><strong>Data</strong>: <code>{settings.DATA_DIR}</code></li>
        </ul>
    """).strip()
