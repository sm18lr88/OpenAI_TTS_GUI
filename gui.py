import logging
import os
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QFileDialog,
    QComboBox,
    QMessageBox,
    QMenuBar,
    QMenu,
    QInputDialog,
    QDialog,
    QListWidget,
    QSplitter,
    QApplication,
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QTimer
from PyQt6.QtGui import QAction, QPalette, QColor, QDoubleValidator

import config  # Import configuration
from tts import TTSProcessor  # Use the processor class
from utils import split_text, read_api_key, save_api_key, load_presets, save_presets

# Setup logger for this module
logger = logging.getLogger(__name__)

# --- Preset Management Dialog ---


class PresetDialog(QDialog):
    """Dialog for managing instruction presets."""

    preset_selected = pyqtSignal(str)  # Signal to emit selected preset text

    def __init__(self, current_instructions: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Instruction Presets")
        self.setMinimumWidth(400)
        self._current_instructions = current_instructions  # Store for saving
        self._presets = {}

        self._setup_ui()
        self._connect_signals()
        self.load_presets()

    def _setup_ui(self):
        """Initialize UI components."""
        self.layout = QVBoxLayout(self)
        self.preset_list = QListWidget()
        self.preset_list.setToolTip("Double-click to load.")

        button_layout = QHBoxLayout()
        self.load_button = QPushButton("Load Selected")
        self.save_button = QPushButton("Save Current Instructions")
        self.delete_button = QPushButton("Delete Selected")

        button_layout.addWidget(self.load_button)
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.delete_button)

        self.layout.addWidget(QLabel("Available Presets:"))
        self.layout.addWidget(self.preset_list)
        self.layout.addLayout(button_layout)

    def _connect_signals(self):
        """Connect UI signals to slots."""
        self.load_button.clicked.connect(self.load_selected)
        self.save_button.clicked.connect(self.save_current)
        self.delete_button.clicked.connect(self.delete_selected)
        self.preset_list.itemDoubleClicked.connect(
            self.load_selected
        )  # Double-click to load

    def load_presets(self):
        """Load presets from JSON and populate the list."""
        self._presets = load_presets()
        self.preset_list.clear()
        sorted_names = sorted(self._presets.keys(), key=str.lower)
        for name in sorted_names:
            self.preset_list.addItem(name)
        logger.debug(f"Preset dialog updated with {len(self._presets)} presets.")

    @pyqtSlot()
    def load_selected(self):
        """Load selected preset and emit signal."""
        selected_item = self.preset_list.currentItem()
        if selected_item:
            name = selected_item.text()
            instructions = self._presets.get(name, "")
            logger.info(f"Preset '{name}' selected for loading.")
            self.preset_selected.emit(instructions)  # Emit the signal
            self.accept()  # Close dialog
        else:
            QMessageBox.warning(self, "No Selection", "Please select a preset to load.")

    @pyqtSlot()
    def save_current(self):
        """Save current instructions from the main window as a new preset."""
        name, ok = QInputDialog.getText(
            self,
            "Save Preset",
            "Enter a name for the current instructions:",
            QLineEdit.EchoMode.Normal,
            "",  # Suggest an empty name initially
        )
        if ok and name:
            name = name.strip()
            if not name:
                QMessageBox.warning(
                    self, "Invalid Name", "Preset name cannot be empty."
                )
                return
            if name in self._presets:
                reply = QMessageBox.question(
                    self,
                    "Overwrite Preset?",
                    f"A preset named '{name}' already exists. Overwrite it?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.No:
                    return

            self._presets[name] = self._current_instructions
            if save_presets(self._presets):
                logger.info(
                    f"Saved preset '{name}' with instructions: {self._current_instructions[:50]}..."
                )
                self.load_presets()  # Refresh list
                QMessageBox.information(
                    self, "Preset Saved", f"Preset '{name}' saved successfully."
                )
            else:
                QMessageBox.critical(self, "Error", "Failed to save presets to file.")
        elif ok and not name.strip():
            QMessageBox.warning(self, "Invalid Name", "Preset name cannot be empty.")

    @pyqtSlot()
    def delete_selected(self):
        """Delete the selected preset."""
        selected_item = self.preset_list.currentItem()
        if selected_item:
            name = selected_item.text()
            reply = QMessageBox.question(
                self,
                "Confirm Deletion",
                f"Are you sure you want to delete the preset '{name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                if name in self._presets:
                    del self._presets[name]
                    if save_presets(self._presets):
                        logger.info(f"Deleted preset '{name}'")
                        self.load_presets()  # Refresh list
                    else:
                        QMessageBox.critical(
                            self, "Error", "Failed to save presets file after deletion."
                        )
                else:
                    # Should not happen if list is sync with dict, but handle defensively
                    logger.warning(
                        f"Attempted to delete preset '{name}' which was not found in internal dict."
                    )
                    self.load_presets()  # Resync list
        else:
            QMessageBox.warning(
                self, "No Selection", "Please select a preset to delete."
            )


# --- Main Application Window ---


class TTSWindow(QMainWindow):
    """Main window for the OpenAI TTS application."""

    # Define signals for thread communication
    tts_complete = pyqtSignal(str)  # Success message
    tts_error = pyqtSignal(str)  # Error message
    progress_updated = pyqtSignal(int)  # Progress percentage

    def __init__(self):
        super().__init__()
        self._api_key = None
        self._current_theme = config.DARK_THEME  # Default theme
        self.tts_processor = None  # Placeholder for the TTS processor thread

        self._load_initial_api_key()
        self._init_ui()
        self._apply_theme(self._current_theme)  # Apply default theme
        self._check_api_key_on_startup()

        # Timer to ensure API key check message appears after UI is shown
        QTimer.singleShot(100, self._check_api_key_on_startup)

    def _load_initial_api_key(self):
        """Loads API key at startup from env var or file."""
        self._api_key = read_api_key()
        if self._api_key:
            logger.info("API key loaded successfully on initialization.")
        else:
            logger.warning(
                "No API key found during initialization (checked env var and file)."
            )

    def _init_ui(self):
        """Initialize the main user interface."""
        self.setWindowTitle(config.APP_NAME)
        self.setGeometry(
            100, 100, config.DEFAULT_WINDOW_WIDTH, config.DEFAULT_WINDOW_HEIGHT
        )

        self._setup_menubar()

        # Main vertical splitter
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.setCentralWidget(splitter)

        # --- Top Part: Text Input ---
        text_widget = self._setup_text_area()
        splitter.addWidget(text_widget)

        # --- Bottom Part: Controls ---
        controls_widget = self._setup_controls_area()
        splitter.addWidget(controls_widget)

        # Adjust initial splitter sizes (optional)
        splitter.setSizes([int(self.height() * 0.6), int(self.height() * 0.4)])

        self._connect_signals()
        self.update_counts()  # Initial update
        self.update_instructions_enabled()  # Initial update

    def _setup_menubar(self):
        """Creates the application menu bar."""
        menubar = self.menuBar()  # Get the main window's menu bar

        # --- Settings Menu ---
        settings_menu = menubar.addMenu("Settings")

        # Theme Submenu
        theme_menu = settings_menu.addMenu("Theme")
        light_action = QAction(
            "Light", self, triggered=lambda: self._apply_theme(config.LIGHT_THEME)
        )
        dark_action = QAction(
            "Dark", self, triggered=lambda: self._apply_theme(config.DARK_THEME)
        )
        theme_menu.addAction(light_action)
        theme_menu.addAction(dark_action)

        settings_menu.addSeparator()

        # Retain Files Option
        self.retain_files_action = QAction(
            "Retain intermediate chunk files", self, checkable=True
        )
        self.retain_files_action.setChecked(False)  # Default to not retaining
        self.retain_files_action.setToolTip(
            "Keeps the individual audio files generated for each text chunk."
        )
        settings_menu.addAction(self.retain_files_action)

        # --- API Key Menu ---
        api_key_menu = menubar.addMenu("API Key")
        # env_key_action = QAction("Use System Environment Variable (if set)", self) # Consider adding this
        # env_key_action.triggered.connect(self._use_env_api_key)
        # api_key_menu.addAction(env_key_action)
        load_key_action = QAction(
            f"Reload from {config.API_KEY_FILE}",
            self,
            triggered=self._load_api_key_from_file,
        )
        set_key_action = QAction(
            "Set/Update API Key...", self, triggered=self._set_custom_api_key
        )
        api_key_menu.addAction(load_key_action)
        api_key_menu.addAction(set_key_action)

    def _setup_text_area(self) -> QWidget:
        """Creates the text input area widget."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)  # Add some padding

        layout.addWidget(QLabel("Text for TTS:"))
        self.text_edit = QTextEdit()
        self.text_edit.setAcceptRichText(False)  # Ensure plain text
        self.text_edit.setPlaceholderText(
            "Enter the text you want to convert to speech..."
        )
        layout.addWidget(self.text_edit)

        # Character and chunk count labels
        count_layout = QHBoxLayout()
        self.char_count_label = QLabel("Character Count: 0")
        self.chunk_count_label = QLabel(
            f"Chunks (max {config.MAX_CHUNK_SIZE} chars): 0"
        )
        count_layout.addWidget(self.char_count_label)
        count_layout.addStretch()  # Push chunk count to the right
        count_layout.addWidget(self.chunk_count_label)
        layout.addLayout(count_layout)

        return widget

    def _setup_controls_area(self) -> QWidget:
        """Creates the controls area widget."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)  # Add some padding

        # --- Model, Voice, Speed, Format ---
        settings_layout = QHBoxLayout()
        settings_layout.addWidget(QLabel("Model:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(config.TTS_MODELS)
        self.model_combo.setToolTip(
            "Select the TTS model (HD is higher quality, gpt-4o-mini supports instructions)."
        )
        settings_layout.addWidget(self.model_combo)

        settings_layout.addWidget(QLabel("Voice:"))
        self.voice_combo = QComboBox()
        self.voice_combo.addItems(config.TTS_VOICES)
        self.voice_combo.setToolTip("Select the desired voice.")
        settings_layout.addWidget(self.voice_combo)

        settings_layout.addWidget(QLabel("Speed:"))
        self.speed_input = QLineEdit(str(config.DEFAULT_SPEED))
        # Add validator for speed input (e.g., 0.25 to 4.0)
        speed_validator = QDoubleValidator(config.MIN_SPEED, config.MAX_SPEED, 2, self)
        speed_validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.speed_input.setValidator(speed_validator)
        self.speed_input.setToolTip(
            f"Playback speed multiplier ({config.MIN_SPEED}-{config.MAX_SPEED}). 1.0 is normal."
        )
        self.speed_input.setMaximumWidth(50)  # Make speed input smaller
        settings_layout.addWidget(self.speed_input)

        settings_layout.addWidget(QLabel("Format:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(config.TTS_FORMATS)
        self.format_combo.setToolTip("Select the output audio format.")
        settings_layout.addWidget(self.format_combo)
        layout.addLayout(settings_layout)

        # --- Instructions ---
        instructions_layout = QHBoxLayout()
        self.instructions_label = QLabel("Instructions:")
        self.instructions_label.setToolTip(
            f"Optional instructions for the '{config.GPT_4O_MINI_TTS_MODEL}' model only."
        )
        instructions_layout.addWidget(self.instructions_label)

        self.instructions_edit = QTextEdit()
        self.instructions_edit.setPlaceholderText(
            f"Provide guidance on voice, tone, pacing (only affects '{config.GPT_4O_MINI_TTS_MODEL}')..."
        )
        self.instructions_edit.setMaximumHeight(80)  # Limit height
        instructions_layout.addWidget(self.instructions_edit)

        self.manage_presets_button = QPushButton("Presets")
        self.manage_presets_button.setToolTip(
            "Load, save, or delete instruction presets."
        )
        instructions_layout.addWidget(self.manage_presets_button)
        layout.addLayout(instructions_layout)

        # --- Save Path ---
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Save As:"))
        self.path_entry = QLineEdit()
        self.path_entry.setPlaceholderText("Select output file path...")
        path_layout.addWidget(self.path_entry)
        self.select_path_button = QPushButton("Browse...")
        self.select_path_button.setToolTip(
            "Select the file name and location to save the audio."
        )
        path_layout.addWidget(self.select_path_button)
        layout.addLayout(path_layout)

        # --- Progress Bar & Create Button ---
        action_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")  # Show percentage
        action_layout.addWidget(self.progress_bar)

        self.create_button = QPushButton("Create TTS")
        self.create_button.setToolTip("Start generating the text-to-speech audio.")
        action_layout.addWidget(self.create_button)
        layout.addLayout(action_layout)

        return widget

    def _connect_signals(self):
        """Connect signals from UI elements and TTS processor."""
        self.text_edit.textChanged.connect(self.update_counts)
        self.select_path_button.clicked.connect(self.select_save_path)
        self.create_button.clicked.connect(self.start_tts_creation)
        self.model_combo.currentIndexChanged.connect(self.update_instructions_enabled)
        self.manage_presets_button.clicked.connect(self.open_preset_dialog)
        self.format_combo.currentTextChanged.connect(self._update_path_extension)

        # Connect signals from TTSProcessor
        self.progress_updated.connect(self._update_progress_bar)
        self.tts_complete.connect(self._handle_tts_success)
        self.tts_error.connect(self._handle_tts_error)

    # --- Theme Handling ---

    def _apply_theme(self, theme_colors):
        """Applies the selected theme to the application."""
        self._current_theme = theme_colors
        stylesheet = config.build_stylesheet(theme_colors)
        self.setStyleSheet(stylesheet)
        # Force style refresh on specific widgets if needed
        self.text_edit.setStyleSheet(self.styleSheet())
        self.instructions_edit.setStyleSheet(self.styleSheet())
        # ... apply to other widgets if direct stylesheet doesn't cover all cases
        logger.info(
            f"Applied {'Dark' if theme_colors == config.DARK_THEME else 'Light'} theme."
        )

    # --- API Key Management ---

    @pyqtSlot()
    def _load_api_key_from_file(self):
        """Handles the 'Reload from file' action."""
        logger.info(f"Attempting to reload API key from {config.API_KEY_FILE}.")
        key = read_api_key()
        if key:
            self._api_key = key
            QMessageBox.information(
                self,
                "API Key Reloaded",
                f"Successfully loaded API key from {config.API_KEY_FILE}.",
            )
            logger.info("API key successfully reloaded from file.")
        else:
            QMessageBox.warning(
                self,
                "API Key Not Found",
                f"Could not find or decrypt API key in {config.API_KEY_FILE}.\nPlease check the file or set the key via the menu.",
            )
            logger.warning(f"Failed to reload API key from {config.API_KEY_FILE}.")

    @pyqtSlot()
    def _set_custom_api_key(self):
        """Handles the 'Set/Update API Key' action."""
        current_key_display = self._api_key if self._api_key else ""
        api_key, ok = QInputDialog.getText(
            self,
            "Set OpenAI API Key",
            "Enter your OpenAI API key (will be obfuscated on save):",
            QLineEdit.EchoMode.Password,  # Use Password mode initially
            current_key_display,
        )
        if ok:
            api_key = api_key.strip()
            if api_key:
                if save_api_key(api_key):
                    self._api_key = api_key  # Update runtime key
                    logger.info("Custom API key set and saved.")
                    QMessageBox.information(
                        self,
                        "API Key Set",
                        f"API key updated and saved to {config.API_KEY_FILE}.",
                    )
                else:
                    QMessageBox.critical(
                        self,
                        "Error",
                        f"Failed to save the API key to {config.API_KEY_FILE}.",
                    )
                    logger.error("Failed to save custom API key.")
            else:
                QMessageBox.warning(self, "Empty Key", "API key cannot be empty.")
                logger.warning("User attempted to set an empty API key.")

    def _check_api_key_on_startup(self):
        """Checks for API key after UI is shown and prompts if missing."""
        if not self._api_key:
            logger.warning("No API key available on startup.")
            QMessageBox.warning(
                self,
                "API Key Missing",
                f"No OpenAI API key found.\nPlease set one using the 'API Key' menu ('Set/Update API Key...').\n\nThe key will be saved (obfuscated) in '{config.API_KEY_FILE}'.",
            )

    # --- UI Update Slots ---

    @pyqtSlot()
    def update_counts(self):
        """Updates character and estimated chunk counts."""
        text = self.text_edit.toPlainText()
        char_count = len(text)
        # Use the same splitting logic for count estimation
        chunks = split_text(text, config.MAX_CHUNK_SIZE) if text else []
        num_chunks = len(chunks)
        self.char_count_label.setText(f"Character Count: {char_count}")
        self.chunk_count_label.setText(
            f"Chunks (max {config.MAX_CHUNK_SIZE} chars): {num_chunks}"
        )
        # logger.debug(f"Updated counts: chars={char_count}, chunks={num_chunks}") # Too noisy for debug usually

    @pyqtSlot()
    def update_instructions_enabled(self):
        """Enables/disables the instructions text box based on the selected model."""
        is_gpt4o_mini = self.model_combo.currentText() == config.GPT_4O_MINI_TTS_MODEL
        self.instructions_edit.setEnabled(is_gpt4o_mini)
        self.instructions_label.setEnabled(is_gpt4o_mini)
        self.manage_presets_button.setEnabled(is_gpt4o_mini)
        if not is_gpt4o_mini:
            # Optionally clear or just leave the text when disabled
            # self.instructions_edit.clear()
            pass
        logger.debug(f"Instructions editor enabled: {is_gpt4o_mini}")

    @pyqtSlot(str)
    def _update_path_extension(self, selected_format: str):
        """Updates the file extension in the path entry when format changes."""
        current_path = self.path_entry.text()
        if not current_path:
            return  # Don't modify if empty

        # Split path and extension
        path_base, _ = os.path.splitext(current_path)

        # Get the new extension, default to .mp3 if unknown
        new_ext = config.FORMAT_EXTENSION_MAP.get(selected_format, ".mp3")

        # Reconstruct path with new extension
        new_path = path_base + new_ext
        self.path_entry.setText(new_path)
        logger.debug(f"Updated path extension to {new_ext} based on format selection.")

    @pyqtSlot(int)
    def _update_progress_bar(self, value: int):
        """Updates the progress bar value."""
        self.progress_bar.setValue(value)
        # logger.debug(f"Progress bar updated to {value}%") # Can be noisy

    # --- File Dialog ---

    @pyqtSlot()
    def select_save_path(self):
        """Opens a dialog to select the output file save path."""
        selected_format = self.format_combo.currentText()
        file_filter = config.FORMAT_FILTER_MAP.get(
            selected_format, config.FORMAT_FILTER_MAP["all"]
        )
        default_ext = config.FORMAT_EXTENSION_MAP.get(selected_format, ".mp3")
        default_filename = f"output{default_ext}"

        # Suggest directory based on current path if exists, else default
        current_path = self.path_entry.text()
        start_dir = os.path.dirname(current_path) if current_path else "."

        # Construct default path for the dialog
        start_path = os.path.join(start_dir, default_filename)

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save TTS Audio As",
            start_path,  # Suggest a default name and location
            file_filter,
        )

        if file_path:
            # Ensure the selected file has the correct extension for the chosen format
            _, selected_ext = os.path.splitext(file_path)
            required_ext = config.FORMAT_EXTENSION_MAP.get(selected_format, ".mp3")
            if selected_ext.lower() != required_ext.lower():
                file_path = os.path.splitext(file_path)[0] + required_ext
                logger.info(f"Corrected file extension to {required_ext}")

            self.path_entry.setText(file_path)
            logger.info(f"Selected save path: {file_path}")
        else:
            logger.info("Save path selection cancelled.")

    # --- Preset Dialog ---

    @pyqtSlot()
    def open_preset_dialog(self):
        """Opens the preset management dialog."""
        logger.info("Opening preset management dialog.")
        current_instructions = self.instructions_edit.toPlainText()
        dialog = PresetDialog(current_instructions, self)
        dialog.preset_selected.connect(self._apply_preset)  # Connect signal
        dialog.exec()

    @pyqtSlot(str)
    def _apply_preset(self, instructions: str):
        """Applies the loaded preset instructions to the text box."""
        self.instructions_edit.setPlainText(instructions)
        logger.info("Applied selected preset instructions.")

    # --- TTS Creation Logic ---

    @pyqtSlot()
    def start_tts_creation(self):
        """Validates inputs and starts the TTS generation process."""
        logger.info("TTS creation requested.")

        # 1. Check API Key
        if not self._api_key:
            logger.error("TTS aborted: No API key available.")
            self._show_message(
                "API Key Missing",
                "Please set your OpenAI API key in the 'API Key' menu before proceeding.",
                level="warning",
            )
            return

        # 2. Check Text Input
        text_to_speak = self.text_edit.toPlainText().strip()
        if not text_to_speak:
            logger.warning("TTS aborted: Text input is empty.")
            self._show_message(
                "Empty Text",
                "Please enter some text to convert to speech.",
                level="warning",
            )
            return

        # 3. Check Save Path
        output_path = self.path_entry.text().strip()
        if not output_path:
            logger.warning("TTS aborted: Output file path is empty.")
            self._show_message(
                "Invalid Path",
                "Please select a valid file path to save the audio.",
                level="warning",
            )
            return

        # Ensure output directory exists or can be created
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir, exist_ok=True)
                logger.info(f"Created output directory: {output_dir}")
            except OSError as e:
                logger.error(
                    f"TTS aborted: Failed to create output directory '{output_dir}': {e}"
                )
                self._show_message(
                    "Directory Error",
                    f"Could not create the output directory:\n{e}",
                    level="critical",
                )
                return

        # 4. Validate Speed
        try:
            speed_float = float(self.speed_input.text().strip())
            if not (config.MIN_SPEED <= speed_float <= config.MAX_SPEED):
                raise ValueError("Speed out of range")
            logger.debug(f"Speed input parsed: {speed_float}")
        except ValueError:
            logger.warning(
                f"Invalid speed input '{self.speed_input.text()}'. Using default {config.DEFAULT_SPEED}."
            )
            self._show_message(
                "Invalid Speed",
                f"Speed must be a number between {config.MIN_SPEED} and {config.MAX_SPEED}. Using {config.DEFAULT_SPEED}.",
                level="warning",
            )
            speed_float = config.DEFAULT_SPEED
            self.speed_input.setText(str(speed_float))  # Correct the UI

        # 5. Gather all parameters
        selected_model = self.model_combo.currentText()
        instructions_text = ""
        if selected_model == config.GPT_4O_MINI_TTS_MODEL:
            instructions_text = self.instructions_edit.toPlainText().strip()

        params = {
            "api_key": self._api_key,
            "text": text_to_speak,
            "output_path": output_path,
            "model": selected_model,
            "voice": self.voice_combo.currentText(),
            "response_format": self.format_combo.currentText(),
            "speed": speed_float,
            "instructions": instructions_text,
            "retain_files": self.retain_files_action.isChecked(),
        }
        logger.info(
            f"Starting TTS process with parameters: { {k: v if k != 'api_key' else '***' for k,v in params.items()} }"
        )  # Log params safely

        # 6. Disable UI elements and start processing
        self._set_ui_enabled(False)
        self.progress_bar.setValue(0)  # Reset progress bar

        # Create and start the TTS processor thread
        self.tts_processor = TTSProcessor(params)
        # Connect signals from this specific processor instance
        self.tts_processor.progress_updated.connect(self.progress_updated.emit)
        self.tts_processor.tts_complete.connect(self.tts_complete.emit)
        self.tts_processor.tts_error.connect(self.tts_error.emit)
        self.tts_processor.start()

    def _set_ui_enabled(self, enabled: bool):
        """Enable or disable UI elements during processing."""
        self.text_edit.setEnabled(enabled)
        self.model_combo.setEnabled(enabled)
        self.voice_combo.setEnabled(enabled)
        self.speed_input.setEnabled(enabled)
        self.format_combo.setEnabled(enabled)
        self.instructions_edit.setEnabled(
            enabled and self.model_combo.currentText() == config.GPT_4O_MINI_TTS_MODEL
        )  # Keep instruction logic
        self.manage_presets_button.setEnabled(
            enabled and self.model_combo.currentText() == config.GPT_4O_MINI_TTS_MODEL
        )
        self.path_entry.setEnabled(enabled)
        self.select_path_button.setEnabled(enabled)
        self.create_button.setEnabled(enabled)
        # Maybe disable menu items too?
        self.menuBar().setEnabled(enabled)

    # --- TTS Process Callbacks ---

    @pyqtSlot(str)
    def _handle_tts_success(self, message: str):
        """Handles the successful completion of the TTS process."""
        logger.info(f"TTS process completed successfully: {message}")
        self._set_ui_enabled(True)
        self.progress_bar.setValue(100)  # Ensure it reaches 100%
        self._show_message("TTS Complete", message, level="info")

    @pyqtSlot(str)
    def _handle_tts_error(self, error_message: str):
        """Handles errors that occurred during the TTS process."""
        logger.error(f"TTS process failed: {error_message}")
        self._set_ui_enabled(True)
        self.progress_bar.setValue(0)  # Reset progress on error
        # Add more detail to error messages if possible
        self._show_message(
            "TTS Error", f"An error occurred:\n{error_message}", level="critical"
        )

    # --- Utility Methods ---

    def _show_message(self, title: str, message: str, level: str = "info"):
        """Displays a message box with appropriate icon."""
        logger.info(
            f"Displaying message box: Title='{title}', Level='{level}', Message='{message[:100]}...'"
        )
        if level == "info":
            QMessageBox.information(self, title, message)
        elif level == "warning":
            QMessageBox.warning(self, title, message)
        elif level == "critical":
            QMessageBox.critical(self, title, message)
        else:
            QMessageBox.information(self, title, message)  # Default to info

    def closeEvent(self, event):
        """Handle window close event."""
        # Optional: Add confirmation if TTS is running
        if self.tts_processor and self.tts_processor.isRunning():
            reply = QMessageBox.question(
                self,
                "Confirm Exit",
                "TTS generation is in progress. Are you sure you want to exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                logger.info("User confirmed exit during active TTS process.")
                # Optionally try to stop the thread gracefully if implemented
                event.accept()
            else:
                event.ignore()
                return
        else:
            logger.info("Application closing.")
            event.accept()
