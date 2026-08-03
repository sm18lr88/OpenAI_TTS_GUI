from __future__ import annotations

from typing import TYPE_CHECKING, Final

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .. import config

if TYPE_CHECKING:
    from .main_window import TTSWindow

LABEL_WIDTH: Final = 56
MODEL_WIDTH: Final = 170
VOICE_WIDTH: Final = 144
SPEED_WIDTH: Final = 72
FORMAT_WIDTH: Final = 96
SECTION_HEADER_HEIGHT: Final = 36


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


def build_controls_panel(window: TTSWindow) -> QWidget:
    panel = QWidget()
    layout = QVBoxLayout(panel)
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
    window.model_combo.addItems(config.TTS_MODELS)
    window.model_combo.setFixedWidth(MODEL_WIDTH)
    voice_grid.addWidget(_field_label("Model:"), 0, 0)
    voice_grid.addWidget(window.model_combo, 0, 1)
    window.voice_combo = QComboBox()
    window.voice_combo.setObjectName("voiceCombo")
    window.voice_combo.addItems(config.TTS_VOICES)
    window.voice_combo.setFixedWidth(VOICE_WIDTH)
    voice_grid.addWidget(_field_label("Voice:"), 1, 0)
    voice_grid.addWidget(window.voice_combo, 1, 1)
    window.speed_input = QLineEdit(str(config.DEFAULT_SPEED))
    window.speed_input.setObjectName("speedInput")
    window.speed_input.setValidator(QDoubleValidator(config.MIN_SPEED, config.MAX_SPEED, 2, window))
    window.speed_input.setFixedWidth(SPEED_WIDTH)
    voice_grid.addWidget(_field_label("Speed:"), 2, 0)
    voice_grid.addWidget(window.speed_input, 2, 1)
    window.format_combo = QComboBox()
    window.format_combo.setObjectName("formatCombo")
    window.format_combo.addItems(config.TTS_FORMATS)
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
        f"Optional voice, tone, and pacing instructions for {config.GPT_4O_MINI_TTS_MODEL}."
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
    window.path_entry.setPlaceholderText("Select an output file path...")
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
    return panel
