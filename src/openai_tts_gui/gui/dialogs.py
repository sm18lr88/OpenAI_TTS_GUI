import logging

from PyQt6.QtCore import pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ..presets import load_presets, save_presets

logger = logging.getLogger(__name__)


class PresetDialog(QDialog):
    preset_selected = pyqtSignal(str)

    def __init__(self, current_instructions: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Instruction Presets")
        self.setMinimumWidth(400)
        self._current_instructions = current_instructions
        self._presets = {}

        self._setup_ui()
        self._connect_signals()
        self.load_presets()

    def _setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.preset_list = QListWidget()
        self.preset_list.setToolTip("Double-click to load.")

        button_layout = QHBoxLayout()
        self.load_button = QPushButton("Load Selected")
        self.save_button = QPushButton("Save Current Instructions")
        self.delete_button = QPushButton("Delete Selected")

        button_layout.addWidget(self.load_button)
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.delete_button)

        self.main_layout.addWidget(QLabel("Available Presets:"))
        self.main_layout.addWidget(self.preset_list)
        self.main_layout.addLayout(button_layout)

    def _connect_signals(self):
        self.load_button.clicked.connect(self.load_selected)
        self.save_button.clicked.connect(self.save_current)
        self.delete_button.clicked.connect(self.delete_selected)
        self.preset_list.itemDoubleClicked.connect(self.load_selected)

    def load_presets(self):
        self._presets = load_presets()
        self.preset_list.clear()
        for name in sorted(self._presets.keys(), key=str.lower):
            self.preset_list.addItem(name)
        logger.debug("Preset dialog updated with %d presets.", len(self._presets))

    @pyqtSlot()
    def load_selected(self):
        item = self.preset_list.currentItem()
        if not item:
            QMessageBox.warning(self, "No Selection", "Please select a preset to load.")
            return
        name = item.text()
        self.preset_selected.emit(self._presets.get(name, ""))
        self.accept()

    @pyqtSlot()
    def save_current(self):
        name, ok = QInputDialog.getText(
            self,
            "Save Preset",
            "Enter a name for the current instructions:",
        )
        if not ok:
            return
        name = (name or "").strip()
        if not name:
            QMessageBox.warning(self, "Invalid Name", "Preset name cannot be empty.")
            return
        if name in self._presets:
            r = QMessageBox.question(
                self,
                "Overwrite Preset?",
                f"A preset named '{name}' exists. Overwrite?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if r != QMessageBox.StandardButton.Yes:
                return

        self._presets[name] = self._current_instructions
        if save_presets(self._presets):
            self.load_presets()
            QMessageBox.information(self, "Preset Saved", f"Preset '{name}' saved.")
        else:
            QMessageBox.critical(self, "Error", "Failed to save presets file.")

    @pyqtSlot()
    def delete_selected(self):
        item = self.preset_list.currentItem()
        if not item:
            QMessageBox.warning(self, "No Selection", "Please select a preset to delete.")
            return
        name = item.text()
        r = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Delete preset '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if r != QMessageBox.StandardButton.Yes:
            return
        if name in self._presets:
            del self._presets[name]
            if save_presets(self._presets):
                self.load_presets()
            else:
                QMessageBox.critical(self, "Error", "Failed to save presets file after deletion.")
