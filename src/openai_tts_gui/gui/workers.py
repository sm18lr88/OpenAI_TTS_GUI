from __future__ import annotations

import logging
import threading
from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal

from ..config import settings
from ..errors import TTSError
from ..tts import TTSService

logger = logging.getLogger(__name__)


class TTSWorker(QThread):
    progress_updated = pyqtSignal(int)
    tts_complete = pyqtSignal(str)
    tts_error = pyqtSignal(str)
    status_update = pyqtSignal(str)
    parallelism_updated = pyqtSignal(int, int)

    def __init__(self, params: dict[str, Any], parent=None):
        super().__init__(parent)
        self.params = params
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        self._cancel_event.set()
        self.requestInterruption()

    def run(self) -> None:
        try:
            api_key = str(self.params.get("api_key") or "")
            service = TTSService(
                api_key=api_key,
                base_url=settings.OPENAI_BASE_URL,
                timeout=settings.OPENAI_TIMEOUT,
            )
            message = service.generate(
                text=str(self.params["text"]),
                output_path=str(self.params["output_path"]),
                model=str(self.params["model"]),
                voice=str(self.params["voice"]),
                response_format=str(self.params["response_format"]),
                speed=float(self.params["speed"]),
                instructions=str(self.params.get("instructions", "")),
                parallelism=int(self.params.get("parallelism", settings.PARALLELISM)),
                retain_files=bool(self.params.get("retain_files", False)),
                on_progress=self._emit_progress,
                on_status=self._emit_status,
                on_parallelism=self._emit_parallelism,
                cancel_event=self._cancel_event,
            )
            self.tts_complete.emit(message)
        except TTSError as exc:
            logger.warning("TTS processing failed: %s", exc)
            self.tts_error.emit(str(exc))
        except Exception as exc:
            logger.exception("Unexpected TTS processing failure: %s", exc)
            self.tts_error.emit(str(exc))
        finally:
            logger.info("TTSWorker thread finished.")

    def _emit_progress(self, value: int) -> None:
        if not self._cancel_event.is_set():
            self.progress_updated.emit(value)

    def _emit_status(self, status: str) -> None:
        self.status_update.emit(status)

    def _emit_parallelism(self, active_workers: int, worker_cap: int) -> None:
        self.parallelism_updated.emit(active_workers, worker_cap)
