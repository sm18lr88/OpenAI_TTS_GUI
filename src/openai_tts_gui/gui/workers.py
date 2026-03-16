import logging

from PyQt6.QtCore import QThread, pyqtSignal

from ..config import settings
from ..tts._service import TTSService

logger = logging.getLogger(__name__)


class TTSWorker(QThread):
    progress_updated = pyqtSignal(int)
    tts_complete = pyqtSignal(str)
    tts_error = pyqtSignal(str)
    status_update = pyqtSignal(str)

    def __init__(self, params: dict, parent=None):
        super().__init__(parent)
        self.params = params

    def run(self):
        try:
            api_key = str(self.params.get("api_key") or "")
            timeout_value = float(getattr(settings, "OPENAI_TIMEOUT", 60.0))
            base_url = (
                settings.OPENAI_BASE_URL if getattr(settings, "OPENAI_BASE_URL", None) else None
            )

            service = TTSService(api_key=api_key, base_url=base_url, timeout=timeout_value)
            message = service.generate(
                text=self.params["text"],
                output_path=self.params["output_path"],
                model=self.params["model"],
                voice=self.params["voice"],
                response_format=self.params["response_format"],
                speed=self.params["speed"],
                instructions=self.params.get("instructions", ""),
                retain_files=self.params.get("retain_files", False),
                on_progress=self._emit_progress,
                on_status=self._emit_status,
            )
            self.tts_complete.emit(message)
        except Exception as e:
            logger.exception(f"TTS processing failed: {e}")
            self.tts_error.emit(str(e))
        finally:
            logger.info("TTSWorker thread finished.")

    def _emit_progress(self, value: int):
        self.progress_updated.emit(value)

    def _emit_status(self, status: str):
        self.status_update.emit(status)
