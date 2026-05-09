from __future__ import annotations

import html
from textwrap import dedent

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QDoubleValidator
from PyQt6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QGroupBox,
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

LABEL_WIDTH = 56
MODEL_WIDTH = 170
VOICE_WIDTH = 144
SPEED_WIDTH = 72
FORMAT_WIDTH = 96
SECTION_HEADER_HEIGHT = 36


def _section_group(object_name: str) -> tuple[QGroupBox, QVBoxLayout]:
    group = QGroupBox()
    group.setObjectName(object_name)
    layout = QVBoxLayout(group)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(7)
    return group, layout


def _section_header(title: str) -> tuple[QHBoxLayout, QLabel]:
    header = QHBoxLayout()
    header.setContentsMargins(0, 0, 0, 0)
    title_label = QLabel(title)
    title_label.setObjectName("sectionTitle")
    title_label.setMinimumHeight(SECTION_HEADER_HEIGHT)
    title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    header.addWidget(title_label)
    return header, title_label


def _field_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setMinimumWidth(LABEL_WIDTH)
    label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    return label


def build_text_area(window) -> QWidget:
    w = QWidget()
    layout = QVBoxLayout(w)
    layout.setContentsMargins(12, 12, 12, 8)
    layout.setSpacing(8)

    layout.addWidget(QLabel("Text for TTS:"))
    window.text_edit = QTextEdit()
    window.text_edit.setObjectName("textEdit")
    window.text_edit.setPlaceholderText("Enter the text you want to convert to speech...")
    window.text_edit.setMinimumHeight(280)
    window.text_edit.setSizePolicy(
        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
    )
    layout.addWidget(window.text_edit, 1)

    counts = QHBoxLayout()
    window.char_count_label = QLabel("Character Count: 0")
    window.chunk_count_label = QLabel(f"Chunks (max {settings.MAX_CHUNK_SIZE} chars): 0")
    window.parallelism_label = QLabel(f"Parallel workers: up to {settings.PARALLELISM}")
    counts.addWidget(window.char_count_label)
    counts.addWidget(window.chunk_count_label)
    counts.addWidget(window.parallelism_label)
    counts.addStretch()
    layout.addLayout(counts)
    return w


def build_controls_area(window) -> QWidget:
    w = QWidget()
    layout = QVBoxLayout(w)
    layout.setContentsMargins(12, 8, 12, 12)
    layout.setSpacing(8)

    deck = QSplitter(Qt.Orientation.Horizontal)
    deck.setObjectName("controlsSplitter")
    deck.setChildrenCollapsible(False)

    voice_group, voice_layout = _section_group("voiceSettingsGroup")
    voice_header, _voice_title = _section_header("Voice Settings")
    voice_layout.addLayout(voice_header)

    voice_grid = QGridLayout()
    voice_grid.setContentsMargins(0, 0, 0, 0)
    voice_grid.setHorizontalSpacing(8)
    voice_grid.setVerticalSpacing(6)
    voice_grid.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    voice_grid.setColumnStretch(2, 1)

    window.model_combo = QComboBox()
    window.model_combo.setObjectName("modelCombo")
    window.model_combo.addItems(settings.TTS_MODELS)
    window.model_combo.setFixedWidth(MODEL_WIDTH)
    voice_grid.addWidget(_field_label("Model:"), 0, 0)
    voice_grid.addWidget(window.model_combo, 0, 1)

    window.voice_combo = QComboBox()
    window.voice_combo.setObjectName("voiceCombo")
    window.voice_combo.addItems(settings.TTS_VOICES)
    window.voice_combo.setFixedWidth(VOICE_WIDTH)
    voice_grid.addWidget(_field_label("Voice:"), 1, 0)
    voice_grid.addWidget(window.voice_combo, 1, 1)

    window.speed_input = QLineEdit(str(settings.DEFAULT_SPEED))
    window.speed_input.setObjectName("speedInput")
    window.speed_input.setValidator(
        QDoubleValidator(settings.MIN_SPEED, settings.MAX_SPEED, 2, window)
    )
    window.speed_input.setFixedWidth(SPEED_WIDTH)
    voice_grid.addWidget(_field_label("Speed:"), 2, 0)
    voice_grid.addWidget(window.speed_input, 2, 1)

    window.format_combo = QComboBox()
    window.format_combo.setObjectName("formatCombo")
    window.format_combo.addItems(settings.TTS_FORMATS)
    window.format_combo.setFixedWidth(FORMAT_WIDTH)
    voice_grid.addWidget(_field_label("Format:"), 3, 0)
    voice_grid.addWidget(window.format_combo, 3, 1)
    voice_layout.addLayout(voice_grid)
    voice_layout.addStretch(1)
    deck.addWidget(voice_group)

    instructions_group, instructions_layout = _section_group("instructionsGroup")
    instructions_header = QHBoxLayout()
    instructions_header.setContentsMargins(0, 0, 0, 0)
    window.instructions_label = QLabel("Instructions")
    window.instructions_label.setObjectName("sectionTitle")
    window.instructions_label.setMinimumHeight(SECTION_HEADER_HEIGHT)
    window.instructions_label.setAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    )
    window.manage_presets_button = QPushButton("Presets")
    window.manage_presets_button.setObjectName("managePresetsButton")
    window.manage_presets_button.setFixedHeight(SECTION_HEADER_HEIGHT)
    instructions_header.addWidget(window.instructions_label)
    instructions_header.addStretch(1)
    instructions_header.addWidget(window.manage_presets_button)
    instructions_layout.addLayout(instructions_header)

    window.instructions_edit = QTextEdit()
    window.instructions_edit.setObjectName("instructionsEdit")
    window.instructions_edit.setPlaceholderText(
        f"Optional voice, tone, and pacing guidance for {settings.GPT_4O_MINI_TTS_MODEL}."
    )
    window.instructions_edit.setMinimumHeight(60)
    window.instructions_edit.setSizePolicy(
        QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
    )
    instructions_layout.addWidget(window.instructions_edit, 1)
    deck.addWidget(instructions_group)
    deck.setStretchFactor(0, 0)
    deck.setStretchFactor(1, 1)
    deck.setSizes([330, 720])

    output_group, output_layout = _section_group("outputRunGroup")
    output_header, _output_title = _section_header("Output & Run")
    output_layout.addLayout(output_header)

    path_row = QHBoxLayout()
    path_row.setSpacing(8)
    path_row.addWidget(_field_label("Save As:"))
    window.path_entry = QLineEdit()
    window.path_entry.setObjectName("pathEntry")
    window.path_entry.setPlaceholderText("Select output file path...")
    path_row.addWidget(window.path_entry)
    window.select_path_button = QPushButton("Browse...")
    window.select_path_button.setObjectName("selectPathButton")
    path_row.addWidget(window.select_path_button)
    output_layout.addLayout(path_row)

    action_row = QHBoxLayout()
    action_row.setSpacing(8)
    window.progress_bar = QProgressBar()
    window.progress_bar.setObjectName("progressBar")
    window.progress_bar.setValue(0)
    action_row.addWidget(window.progress_bar)

    window.create_button = QPushButton("Create TTS")
    window.create_button.setObjectName("primaryButton")
    action_row.addWidget(window.create_button)

    window.cancel_button = QPushButton("Cancel")
    window.cancel_button.setObjectName("cancelButton")
    window.cancel_button.setEnabled(False)
    action_row.addWidget(window.cancel_button)

    window.copy_ids_button = QPushButton("Copy Request IDs")
    window.copy_ids_button.setObjectName("copyRequestIdsButton")
    window.copy_ids_button.setEnabled(False)
    window.copy_ids_button.clicked.connect(window._copy_request_ids)
    action_row.addWidget(window.copy_ids_button)
    output_layout.addLayout(action_row)

    window.parallelism_status_label = QLabel("Active chunk workers: idle")
    window.parallelism_status_label.setObjectName("parallelismStatusLabel")
    output_layout.addWidget(window.parallelism_status_label)

    layout.addWidget(deck, 1)
    layout.addWidget(output_group, 0)

    return w


def build_about_page(window) -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(16)

    window.about_text = QTextBrowser()
    window.about_text.setObjectName("aboutText")
    window.about_text.setOpenExternalLinks(True)
    window.about_text.setReadOnly(True)
    layout.addWidget(window.about_text)

    back_row = QHBoxLayout()
    back_row.addStretch()
    window.open_log_button = QPushButton("Open Log Folder")
    window.open_log_button.setObjectName("openLogButton")
    window.open_log_button.clicked.connect(
        lambda: window._open_containing_folder(settings.LOG_FILE)
    )
    back_row.addWidget(window.open_log_button)
    window.about_back_button = QPushButton("Back to Application")
    window.about_back_button.setObjectName("aboutBackButton")
    window.about_back_button.clicked.connect(window._show_main_page)
    back_row.addWidget(window.about_back_button)
    layout.addLayout(back_row)
    return page


def build_central_widget(window) -> QStackedWidget:
    splitter = QSplitter(Qt.Orientation.Vertical)
    splitter.addWidget(build_text_area(window))
    splitter.addWidget(build_controls_area(window))
    splitter.setStretchFactor(0, 3)
    splitter.setStretchFactor(1, 1)
    splitter.setSizes([int(window.height() * 0.78), int(window.height() * 0.22)])

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
    window.parallelism_action = QAction("Chunk parallelism...", window)
    window.parallelism_action.triggered.connect(window._set_parallelism)
    if settings_menu is not None:
        settings_menu.addAction(window.parallelism_action)
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
    from ..core.ffmpeg import get_ffmpeg_version

    snap = settings.env_snapshot()
    ffv = html.escape(get_ffmpeg_version() or "Unavailable")
    return dedent(
        f"""
        <h2>{html.escape(settings.APP_NAME)} {html.escape(settings.APP_VERSION)}</h2>
        <p>
            OpenAI TTS GUI converts text into speech via OpenAI's TTS service.
            Fine-tune voices, models, and export formats without scripting.
        </p>
        <h3>Highlights</h3>
        <ul>
            <li>Pick an OpenAI voice, tweak speed, and export in your preferred format.</li>
            <li>Save reusable instruction presets for guidance-capable models.</li>
            <li>Monitor generation progress, cancel work in flight, and optionally keep chunks.</li>
        </ul>
        <h3>Quick Tips</h3>
        <ul>
            <li>Add the API key under <em>API Key &gt; Set/Update</em>.</li>
            <li>Use the preset manager to store prompt snippets.</li>
            <li>Adjust chunk parallelism under <em>Settings &gt; Chunk parallelism</em>.</li>
            <li>See README.md for workflow examples.</li>
        </ul>
        <h3>Parallel Processing Risks</h3>
        <ul>
            <li>
                Higher parallelism can trigger OpenAI rate limits,
                especially on smaller or non-corporate accounts.
            </li>
            <li>
                When rate limits hit, the app slows itself down and retries,
                so larger values are not always faster.
            </li>
            <li>Start with 2 or 3 workers and only increase if your runs stay stable.</li>
        </ul>
        <h3>Environment</h3>
        <ul>
            <li><strong>Python</strong>: {html.escape(snap.get("python") or "Unknown")}</li>
            <li><strong>Platform</strong>: {html.escape(snap.get("platform") or "Unknown")}</li>
            <li><strong>OpenAI</strong>: {html.escape(snap.get("openai") or "Unknown")}</li>
            <li><strong>PyQt6</strong>: {html.escape(snap.get("pyqt6") or "Unknown")}</li>
            <li><strong>FFmpeg</strong>: {ffv}</li>
            <li><strong>Log</strong>: <code>{html.escape(settings.LOG_FILE)}</code></li>
            <li><strong>Data</strong>: <code>{html.escape(settings.DATA_DIR)}</code></li>
        </ul>
        """
    ).strip()
