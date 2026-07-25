from __future__ import annotations

import html
from collections.abc import Callable
from textwrap import dedent
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from .. import config

if TYPE_CHECKING:
    from .main_window import TTSWindow


def build_about_page(window: TTSWindow) -> QWidget:
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
    window.open_log_button.clicked.connect(lambda: window._open_containing_folder(config.LOG_FILE))
    back_row.addWidget(window.open_log_button)
    window.about_back_button = QPushButton("Back to Application")
    window.about_back_button.setObjectName("aboutBackButton")
    window.about_back_button.clicked.connect(window._show_main_page)
    back_row.addWidget(window.about_back_button)
    layout.addLayout(back_row)
    return page


def show_about_page(window: TTSWindow, html_factory: Callable[[], str]) -> None:
    if window._about_html_cache is None:
        window._about_html_cache = html_factory()
        window.about_text.setHtml(window._about_html_cache)
    window.stack.setCurrentWidget(window.about_page)
    window.about_back_button.setFocus()


def show_main_page(window: TTSWindow) -> None:
    window.stack.setCurrentIndex(0)
    window.text_edit.setFocus()


def about_html() -> str:
    from ..core import get_ffmpeg_version

    snap = config.env_snapshot()
    ffv = html.escape(get_ffmpeg_version() or "Unavailable")
    return dedent(
        f"""
        <h2>{html.escape(config.APP_NAME)} {html.escape(config.APP_VERSION)}</h2>
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
            <li>
                Long text is split into chunks of up to {config.MAX_CHUNK_SIZE} characters
                before generation.
            </li>
            <li>Adjust chunk parallelism under <em>Settings &gt; Chunk parallelism</em>.</li>
            <li>See README.md for workflow examples.</li>
        </ul>
        <h3>Support</h3>
        <p>
            Show <a href="{html.escape(config.SUPPORT_URL)}">appreciation</a>
            if this app helps you.
        </p>
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
            <li><strong>Log</strong>: <code>{html.escape(config.LOG_FILE)}</code></li>
            <li><strong>Data</strong>: <code>{html.escape(config.DATA_DIR)}</code></li>
        </ul>
        """
    ).strip()
