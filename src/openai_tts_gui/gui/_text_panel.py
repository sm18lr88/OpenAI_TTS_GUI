from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QTextEdit, QVBoxLayout, QWidget

from .. import config

if TYPE_CHECKING:
    from .main_window import TTSWindow


def build_text_panel(window: TTSWindow) -> QWidget:
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(12, 12, 12, 8)
    layout.setSpacing(8)

    layout.addWidget(QLabel("Text for TTS:"))
    window.text_edit = QTextEdit()
    window.text_edit.setObjectName("textEdit")
    window.text_edit.setPlaceholderText("Enter the text you want to convert to speech...")
    window.text_edit.setMinimumHeight(280)
    window.text_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    layout.addWidget(window.text_edit, 1)

    counts = QHBoxLayout()
    window.char_count_label = QLabel("Character Count: 0")
    window.chunk_count_label = QLabel("Chunks: 0")
    window.price_estimate_label = QLabel("Estimated price: $0.00")
    window.parallelism_label = QLabel(f"Parallel workers: 0 (max: {config.settings.PARALLELISM})")
    counts.addWidget(window.char_count_label)
    counts.addWidget(window.chunk_count_label)
    counts.addWidget(window.price_estimate_label)
    counts.addWidget(window.parallelism_label)
    counts.addStretch()
    layout.addLayout(counts)
    return panel
