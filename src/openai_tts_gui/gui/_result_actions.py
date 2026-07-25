from __future__ import annotations

import html
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QApplication

from .. import config
from ..core import SidecarParseError, read_sidecar_metadata

if TYPE_CHECKING:
    from .main_window import TTSWindow

logger = logging.getLogger(__name__)


class ResultActions:
    _LEGACY_METHODS = {
        "_refresh_request_ids_button": "refresh_request_ids_button",
        "_completion_message": "completion_message",
        "_read_parallelism_used": "read_parallelism_used",
        "_copy_request_ids": "copy_request_ids",
        "_open_containing_folder": "open_containing_folder",
    }

    def __init__(self, window: TTSWindow) -> None:
        self._window = window

    def resolve_legacy(self, name: str):
        method_name = self._LEGACY_METHODS.get(name)
        return getattr(self, method_name) if method_name is not None else None

    def refresh_request_ids_button(self) -> None:
        output_path = self._window.path_entry.text().strip()
        if not output_path:
            self._window.copy_ids_button.setEnabled(False)
            return
        sidecar = Path(f"{output_path}.json")
        if not sidecar.exists():
            self._window.copy_ids_button.setEnabled(False)
            return
        try:
            request_ids = read_sidecar_metadata(sidecar).request_ids
        except (FileNotFoundError, SidecarParseError):
            request_ids: tuple[str, ...] = ()
        self._window.copy_ids_button.setEnabled(bool(request_ids))

    def completion_message(self, message: str) -> str:
        escaped_message = html.escape(message)
        escaped_url = html.escape(config.SUPPORT_URL, quote=True)
        return f'{escaped_message}\n\nShow <a href="{escaped_url}">appreciation</a>.'

    def read_parallelism_used(self) -> int | None:
        output_path = self._window.path_entry.text().strip()
        if not output_path:
            return None
        sidecar = Path(f"{output_path}.json")
        try:
            return read_sidecar_metadata(sidecar).parallelism_used
        except (FileNotFoundError, SidecarParseError):
            return None

    def copy_request_ids(self) -> None:
        output_path = self._window.path_entry.text().strip()
        if not output_path:
            self._window._notify(
                "No Output", "Generate TTS first to copy request IDs.", level="warning"
            )
            return
        sidecar = Path(f"{output_path}.json")
        try:
            request_ids = read_sidecar_metadata(sidecar).request_ids
            if not request_ids:
                self._window._notify(
                    "No Request IDs", "No request IDs found in sidecar.", level="warning"
                )
                return
            clipboard = QApplication.clipboard()
            if clipboard is None:
                self._window._notify("Copy Failed", "Clipboard unavailable.", level="warning")
                return
            clipboard.setText("\n".join(request_ids))
            self._window._notify("Copied", "Request IDs copied to clipboard.")
        except FileNotFoundError:
            self._window._notify(
                "Sidecar Missing", "Sidecar file not found for this output.", level="warning"
            )
        except SidecarParseError as exc:
            self._window._notify("Copy Failed", str(exc), level="critical")

    def open_containing_folder(self, path: str) -> None:
        try:
            folder = os.path.dirname(path) or "."
            if sys.platform.startswith("win"):
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except OSError as exc:
            logger.warning("Failed to open folder: %s", exc)
