import logging
import os
import subprocess
import sys
from contextlib import suppress

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QColor, QDoubleValidator
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

# --- Fluent Widgets & Theming ---
from qfluentwidgets import (
    ComboBox,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    MessageBox,
    NavigationInterface,
    NavigationItemPosition,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    TextEdit,
    Theme,
    setTheme,
    setThemeColor,
)

import config  # Import configuration
from tts import TTSProcessor  # Use the processor class
from utils import (
    get_ffmpeg_version,
    load_presets,
    read_api_key,
    save_api_key,
    save_presets,
    split_text,
)

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
        self.load_button = PrimaryPushButton("Load Selected")
        self.save_button = PushButton("Save Current Instructions")
        self.delete_button = PushButton("Delete Selected")

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
        self.preset_list.itemDoubleClicked.connect(self.load_selected)  # Double-click to load

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
            try:
                InfoBar.warning(
                    parent=self,
                    title="No Selection",
                    content="Please select a preset to load.",
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=5000,
                    closable=True,
                )
            except Exception:
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
                try:
                    InfoBar.warning(
                        parent=self,
                        title="Invalid Name",
                        content="Preset name cannot be empty.",
                        position=InfoBarPosition.TOP_RIGHT,
                        duration=5000,
                        closable=True,
                    )
                except Exception:
                    QMessageBox.warning(self, "Invalid Name", "Preset name cannot be empty.")
                return
            if name in self._presets:
                mb = MessageBox(
                    "Overwrite Preset?",
                    f"A preset named '{name}' already exists. Overwrite it?",
                    self,
                )
                if mb.exec() == 0:
                    return

            self._presets[name] = self._current_instructions
            if save_presets(self._presets):
                logger.info(
                    f"Saved preset '{name}' with instructions: {self._current_instructions[:50]}..."
                )
                self.load_presets()  # Refresh list
                try:
                    InfoBar.success(
                        parent=self,
                        title="Preset Saved",
                        content=f"Preset '{name}' saved successfully.",
                        position=InfoBarPosition.TOP_RIGHT,
                        duration=5000,
                        closable=True,
                    )
                except Exception:
                    QMessageBox.information(
                        self, "Preset Saved", f"Preset '{name}' saved successfully."
                    )
            else:
                try:
                    InfoBar.error(
                        parent=self,
                        title="Error",
                        content="Failed to save presets to file.",
                        position=InfoBarPosition.TOP_RIGHT,
                        duration=8000,
                        closable=True,
                    )
                except Exception:
                    QMessageBox.critical(self, "Error", "Failed to save presets to file.")
        elif ok and not name.strip():
            try:
                InfoBar.warning(
                    parent=self,
                    title="Invalid Name",
                    content="Preset name cannot be empty.",
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=5000,
                    closable=True,
                )
            except Exception:
                QMessageBox.warning(self, "Invalid Name", "Preset name cannot be empty.")

    @pyqtSlot()
    def delete_selected(self):
        """Delete the selected preset."""
        selected_item = self.preset_list.currentItem()
        if selected_item:
            name = selected_item.text()
            mb = MessageBox(
                "Confirm Deletion",
                f"Are you sure you want to delete the preset '{name}'?",
                self,
            )
            if mb.exec() == 1:
                if name in self._presets:
                    del self._presets[name]
                    if save_presets(self._presets):
                        logger.info(f"Deleted preset '{name}'")
                        self.load_presets()  # Refresh list
                    else:
                        try:
                            InfoBar.error(
                                parent=self,
                                title="Error",
                                content="Failed to save presets file after deletion.",
                                position=InfoBarPosition.TOP_RIGHT,
                                duration=8000,
                                closable=True,
                            )
                        except Exception:
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
            try:
                InfoBar.warning(
                    parent=self,
                    title="No Selection",
                    content="Please select a preset to delete.",
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=5000,
                    closable=True,
                )
            except Exception:
                QMessageBox.warning(self, "No Selection", "Please select a preset to delete.")


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
            logger.warning("No API key found during initialization (checked env var and file).")

    def _init_ui(self):
        """Initialize the main user interface."""
        self.setWindowTitle(config.APP_NAME)
        self.setGeometry(100, 100, config.DEFAULT_WINDOW_WIDTH, config.DEFAULT_WINDOW_HEIGHT)

        # Build main TTS page (existing layout)
        splitter = QSplitter(Qt.Orientation.Vertical)
        # --- Top Part: Text Input ---
        text_widget = self._setup_text_area()
        splitter.addWidget(text_widget)
        # --- Bottom Part: Controls ---
        controls_widget = self._setup_controls_area()
        splitter.addWidget(controls_widget)
        splitter.setSizes([int(self.height() * 0.6), int(self.height() * 0.4)])
        self.main_page = splitter

        # Build About page
        self.about_page = QWidget()
        about_layout = QVBoxLayout(self.about_page)
        about_layout.setContentsMargins(12, 12, 12, 12)
        self.about_text = TextEdit()
        self.about_text.setReadOnly(True)
        about_layout.addWidget(self.about_text)

        # Stacked pages
        self.stack = QStackedWidget()
        self.stack.addWidget(self.main_page)
        self.stack.addWidget(self.about_page)

        # Navigation interface
        self.navigation = NavigationInterface(self, showMenuButton=True, showReturnButton=False)
        try:
            self.navigation.addItem(
                routeKey="tts",
                icon=FluentIcon.SPEAKER,
                text="TTS",
                onClick=lambda: self.stack.setCurrentWidget(self.main_page),
                position=NavigationItemPosition.TOP,
            )
            self.navigation.addItem(
                routeKey="about",
                icon=FluentIcon.INFO,
                text="About",
                onClick=lambda: self._show_about_page(),
                position=NavigationItemPosition.BOTTOM,
            )
        except Exception:
            # Fallback icons if FluentIcon isn't available in this version
            self.navigation.addItem(
                routeKey="tts",
                icon=None,
                text="TTS",
                onClick=lambda: self.stack.setCurrentWidget(self.main_page),
                position=NavigationItemPosition.TOP,
            )
            self.navigation.addItem(
                routeKey="about",
                icon=None,
                text="About",
                onClick=lambda: self._show_about_page(),
                position=NavigationItemPosition.BOTTOM,
            )

        # Central container with (nav | stack)
        central = QWidget()
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.navigation)
        h.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        # Build the standard menu bar
        self._setup_menubar()

        # Init signals and defaults
        self._connect_signals()
        self.update_counts()
        self.update_instructions_enabled()
        # Ensure attribute always exists for closeEvent safety
        self.tts_processor = self.tts_processor  # no-op; kept for clarity

    def _setup_menubar(self):
        """Creates the application menu bar."""
        menubar = self.menuBar()

        # --- Settings Menu ---
        settings_menu = menubar.addMenu("Settings")

        # Theme Submenu
        theme_menu = settings_menu.addMenu("Theme")
        light_action = QAction(
            "Light", self, triggered=lambda: self._apply_theme(config.LIGHT_THEME)
        )
        dark_action = QAction("Dark", self, triggered=lambda: self._apply_theme(config.DARK_THEME))
        theme_menu.addAction(light_action)
        theme_menu.addAction(dark_action)

        settings_menu.addSeparator()

        # Retain Files Option
        self.retain_files_action = QAction("Retain intermediate chunk files", self, checkable=True)
        self.retain_files_action.setChecked(False)  # Default to not retaining
        self.retain_files_action.setToolTip(
            "Keeps the individual audio files generated for each text chunk."
        )
        settings_menu.addAction(self.retain_files_action)

        # --- API Key Menu ---
        api_key_menu = menubar.addMenu("API Key")
        # env_key_action = QAction(
        #     "Use System Environment Variable (if set)", self
        # )  # Consider adding this
        # env_key_action.triggered.connect(self._use_env_api_key)
        # api_key_menu.addAction(env_key_action)
        load_key_action = QAction(
            "Reload from secure store",
            self,
            triggered=self._load_api_key_from_file,
        )
        set_key_action = QAction("Set/Update API Key...", self, triggered=self._set_custom_api_key)
        api_key_menu.addAction(load_key_action)
        api_key_menu.addAction(set_key_action)

        # --- Help Menu ---
        help_menu = menubar.addMenu("Help")
        about_action = QAction("About", self, triggered=self._show_about)
        help_menu.addAction(about_action)

    def _setup_text_area(self) -> QWidget:
        """Creates the text input area widget."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)  # Add some padding

        layout.addWidget(QLabel("Text for TTS:"))
        self.text_edit = TextEdit()
        self.text_edit.setAcceptRichText(False)  # Ensure plain text
        self.text_edit.setPlaceholderText("Enter the text you want to convert to speech...")
        layout.addWidget(self.text_edit)

        # Character and chunk count labels
        count_layout = QHBoxLayout()
        self.char_count_label = QLabel("Character Count: 0")
        self.chunk_count_label = QLabel(f"Chunks (max {config.MAX_CHUNK_SIZE} chars): 0")
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
        self.model_combo = ComboBox()
        self.model_combo.addItems(config.TTS_MODELS)
        self.model_combo.setToolTip(
            "Select the TTS model (HD is higher quality, gpt-4o-mini supports instructions)."
        )
        settings_layout.addWidget(self.model_combo)

        settings_layout.addWidget(QLabel("Voice:"))
        self.voice_combo = ComboBox()
        self.voice_combo.addItems(config.TTS_VOICES)
        self.voice_combo.setToolTip("Select the desired voice.")
        settings_layout.addWidget(self.voice_combo)

        settings_layout.addWidget(QLabel("Speed:"))
        self.speed_input = LineEdit()
        self.speed_input.setText(str(config.DEFAULT_SPEED))
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
        self.format_combo = ComboBox()
        self.format_combo.addItems(config.TTS_FORMATS)
        self.format_combo.setToolTip("Select the output audio format.")
        settings_layout.addWidget(self.format_combo)
        layout.addLayout(settings_layout)

        # --- Instructions ---
        instructions_layout = QHBoxLayout()
        # Left column: label on top, Presets button below
        left_col = QVBoxLayout()
        self.instructions_label = QLabel("Instructions:")
        self.instructions_label.setToolTip(
            f"Optional instructions for the '{config.GPT_4O_MINI_TTS_MODEL}' model only."
        )
        self.manage_presets_button = PushButton("Presets")
        self.manage_presets_button.setToolTip("Load, save, or delete instruction presets.")
        left_col.addWidget(self.instructions_label)
        left_col.addWidget(self.manage_presets_button)
        left_col.addStretch()
        instructions_layout.addLayout(left_col)

        # Right column: full-width, growable instructions editor
        self.instructions_edit = TextEdit()
        self.instructions_edit.setPlaceholderText(
            "Provide guidance on voice, tone, pacing (only affects "
            f"'{config.GPT_4O_MINI_TTS_MODEL}')..."
        )
        # Let instructions expand to absorb extra vertical space instead of layout spacing
        self.instructions_edit.setMinimumHeight(60)
        self.instructions_edit.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        instructions_layout.addWidget(self.instructions_edit, 1)  # give editor stretch

        # Give the instructions row vertical stretch so it grows/shrinks,
        # while other rows remain fixed
        layout.addLayout(instructions_layout, 1)

        # --- Save Path ---
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Save As:"))
        self.path_entry = LineEdit()
        self.path_entry.setPlaceholderText("Select output file path...")
        path_layout.addWidget(self.path_entry)
        self.select_path_button = PushButton("Browse...")
        self.select_path_button.setToolTip("Select the file name and location to save the audio.")
        path_layout.addWidget(self.select_path_button)
        layout.addLayout(path_layout)

        # --- Progress Bar & Create Button ---
        action_layout = QHBoxLayout()
        self.progress_bar = ProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")  # Show percentage
        action_layout.addWidget(self.progress_bar)

        self.create_button = PrimaryPushButton("Create TTS")
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
        """Applies Fluent theme (with fallback stylesheet if disabled)."""
        self._current_theme = theme_colors
        if getattr(config, "FLUENT_ENABLED", True):
            # Map our light/dark to Fluent Theme; set accent color as well.
            is_dark = theme_colors == config.DARK_THEME
            setTheme(Theme.DARK if is_dark else Theme.LIGHT)
            with suppress(Exception):
                setThemeColor(QColor(getattr(config, "FLUENT_ACCENT_HEX", "#66A3FF")))
            # Clear any legacy stylesheet to avoid conflicts
            self.setStyleSheet("")
            logger.info("Applied Fluent theme: %s", "Dark" if is_dark else "Light")
        else:
            # Legacy stylesheet fallback
            stylesheet = config.build_stylesheet(theme_colors)
            self.setStyleSheet(stylesheet)
            logger.info(
                "Applied legacy stylesheet theme: %s",
                "Dark" if theme_colors == config.DARK_THEME else "Light",
            )

    # --- API Key Management ---

    @pyqtSlot()
    def _load_api_key_from_file(self):
        """Handles the 'Reload from file' action."""
        logger.info(f"Attempting to reload API key from {config.API_KEY_FILE}.")
        key = read_api_key()
        if key:
            self._api_key = key
            self._show_message(
                "API Key Reloaded",
                "Successfully loaded API key from keyring or file.",
                level="info",
            )
            logger.info("API key successfully reloaded from file.")
        else:
            self._show_message(
                "API Key Not Found",
                "Could not find an API key. Set one via the menu.",
                level="warning",
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
                    self._show_message(
                        "API Key Set",
                        "API key saved (OS keyring preferred; file fallback updated).",
                        level="info",
                    )
                else:
                    self._show_message(
                        "Error",
                        f"Failed to save the API key to {config.API_KEY_FILE}.",
                        level="critical",
                    )
                    logger.error("Failed to save custom API key.")
            else:
                self._show_message("Empty Key", "API key cannot be empty.", level="warning")
                logger.warning("User attempted to set an empty API key.")

    def _check_api_key_on_startup(self):
        """Checks for API key after UI is shown and prompts if missing."""
        if not self._api_key:
            logger.warning("No API key available on startup.")
            self._show_message(
                "API Key Missing",
                (
                    "No OpenAI API key found.\n"
                    "Set one using the 'API Key' menu ('Set/Update API Key...').\n"
                    f"Stored in keyring (if available) and '{config.API_KEY_FILE}'."
                ),
                level="warning",
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
        self.chunk_count_label.setText(f"Chunks (max {config.MAX_CHUNK_SIZE} chars): {num_chunks}")
        # logger.debug("Updated counts: chars=%d, chunks=%d", char_count, num_chunks)

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

    # --- Help / About ---
    @pyqtSlot()
    def _show_about(self):
        # Keep menu-based About as a toast and navigate to the About page
        self._show_message("About", f"{config.APP_NAME} {config.APP_VERSION}", level="info")
        self._show_about_page()

    def _show_about_page(self):
        snap = config.env_snapshot()
        ffv = get_ffmpeg_version()
        text = (
            f"{config.APP_NAME} {config.APP_VERSION}\n\n"
            f"Python: {snap.get('python')}\n"
            f"Platform: {snap.get('platform')}\n"
            f"OpenAI: {snap.get('openai')}\n"
            f"PyQt6: {snap.get('pyqt6')}\n"
            f"FFmpeg: {ffv}\n"
            f"Log: {config.LOG_FILE}\n"
            f"Data dir: {config.DATA_DIR}"
        )
        self.about_text.setPlainText(text)
        self.stack.setCurrentWidget(self.about_page)

    # ------- Methods merged from the duplicate class definition -------
    @pyqtSlot()
    def select_save_path(self):
        """Opens a dialog to select the output file save path."""
        selected_format = self.format_combo.currentText()
        file_filter = config.FORMAT_FILTER_MAP.get(selected_format, config.FORMAT_FILTER_MAP["all"])
        current_path = self.path_entry.text()
        start_dir = os.path.dirname(current_path) if current_path else config.DEFAULT_OUTPUT_DIR
        os.makedirs(start_dir, exist_ok=True)

        default_ext = config.FORMAT_EXTENSION_MAP.get(selected_format, ".mp3")
        default_filename = f"output{default_ext}"
        start_path = os.path.join(start_dir, default_filename)

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save TTS Audio As",
            start_path,
            file_filter,
        )
        if file_path:
            _, selected_ext = os.path.splitext(file_path)
            required_ext = config.FORMAT_EXTENSION_MAP.get(selected_format, ".mp3")
            if selected_ext.lower() != required_ext.lower():
                file_path = os.path.splitext(file_path)[0] + required_ext
                logger.info(f"Corrected file extension to {required_ext}")
            self.path_entry.setText(file_path)
            logger.info(f"Selected save path: {file_path}")
        else:
            logger.info("Save path selection cancelled.")

    @pyqtSlot()
    def open_preset_dialog(self):
        """Opens the preset management dialog."""
        logger.info("Opening preset management dialog.")
        current_instructions = self.instructions_edit.toPlainText()
        dialog = PresetDialog(current_instructions, self)
        dialog.preset_selected.connect(self._apply_preset)
        dialog.exec()

    def _apply_preset(self, instructions: str):
        """Applies the loaded preset instructions to the text box."""
        self.instructions_edit.setPlainText(instructions)
        logger.info("Applied selected preset instructions.")

    def start_tts_creation(self):
        """Validates inputs and starts the TTS generation process."""
        logger.info("TTS creation requested.")
        if not self._api_key:
            logger.error("TTS aborted: No API key available.")
            self._show_message(
                "API Key Missing",
                "Please set your OpenAI API key in the 'API Key' menu before proceeding.",
                level="warning",
            )
            return
        text_to_speak = self.text_edit.toPlainText().strip()
        if not text_to_speak:
            logger.warning("TTS aborted: Text input is empty.")
            self._show_message(
                "Empty Text",
                "Please enter some text to convert to speech.",
                level="warning",
            )
            return
        output_path = self.path_entry.text().strip()
        if not output_path:
            selected_format = self.format_combo.currentText()
            default_ext = config.FORMAT_EXTENSION_MAP.get(selected_format, ".mp3")
            output_dir = config.DEFAULT_OUTPUT_DIR
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f"output{default_ext}")
            self.path_entry.setText(output_path)
            logger.info("No path provided; defaulting to %s", output_path)
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir, exist_ok=True)
                logger.info(f"Created output directory: {output_dir}")
            except OSError as e:
                logger.error(f"TTS aborted: Failed to create output directory '{output_dir}': {e}")
                self._show_message(
                    "Directory Error",
                    f"Could not create the output directory:\n{e}",
                    level="critical",
                )
                return
        try:
            speed_float = float(self.speed_input.text().strip())
            if not (config.MIN_SPEED <= speed_float <= config.MAX_SPEED):
                raise ValueError("Speed out of range")
        except ValueError:
            logger.warning(
                "Invalid speed input '%s'. Using default %s.",
                self.speed_input.text(),
                config.DEFAULT_SPEED,
            )
            self._show_message(
                "Invalid Speed",
                (
                    f"Speed must be a number between {config.MIN_SPEED} and "
                    f"{config.MAX_SPEED}. Using {config.DEFAULT_SPEED}."
                ),
                level="warning",
            )
            speed_float = config.DEFAULT_SPEED
            self.speed_input.setText(str(speed_float))
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
        params_redacted = {k: ("***" if k == "api_key" else v) for k, v in params.items()}
        logger.info("Starting TTS with parameters: %s", params_redacted)
        self._set_ui_enabled(False)
        self.progress_bar.setValue(0)
        self.tts_processor = TTSProcessor(params)
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
        )
        self.manage_presets_button.setEnabled(
            enabled and self.model_combo.currentText() == config.GPT_4O_MINI_TTS_MODEL
        )
        self.path_entry.setEnabled(enabled)
        self.select_path_button.setEnabled(enabled)
        self.create_button.setEnabled(enabled)
        with suppress(Exception):
            self.menuBar().setEnabled(enabled)

    @pyqtSlot(str)
    def _handle_tts_success(self, message: str):
        """Handles successful completion of the TTS process."""
        logger.info(f"TTS process completed successfully: {message}")
        self._set_ui_enabled(True)
        self.progress_bar.setValue(100)
        self._show_message("TTS Complete", message, level="info")
        try:
            mb = MessageBox("Open Folder?", "Open the output folder now?", self)
            if mb.exec() == 1:
                self._open_containing_folder(self.path_entry.text().strip())
        except Exception:
            pass

    @pyqtSlot(str)
    def _handle_tts_error(self, error_message: str):
        """Handles errors that occurred during the TTS process."""
        logger.error(f"TTS process failed: {error_message}")
        self._set_ui_enabled(True)
        self.progress_bar.setValue(0)
        self._show_message("TTS Error", f"An error occurred:\n{error_message}", level="critical")

    def _show_message(self, title: str, message: str, level: str = "info"):
        """Displays a Fluent InfoBar with appropriate style."""
        _show_infobar(self, title, message, level)

    def _open_containing_folder(self, path: str):
        """Open the OS file manager at the output folder."""
        try:
            folder = os.path.dirname(path) or "."
            if sys.platform.startswith("win"):
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception as e:
            logger.warning("Failed to open folder: %s", e)

    def closeEvent(self, event):
        """Handle window close event safely even if no processor was created."""
        proc = getattr(self, "tts_processor", None)
        if proc is not None and hasattr(proc, "isRunning") and proc.isRunning():
            mb = MessageBox(
                "Confirm Exit",
                "TTS generation is in progress. Are you sure you want to exit?",
                self,
            )
            if mb.exec() == 1:
                logger.info("User confirmed exit during active TTS process.")
                event.accept()
            else:
                event.ignore()
                return
        else:
            logger.info("Application closing.")
            event.accept()


# --- Helpers (Fluent notifications) ---
def _show_infobar(parent, title: str, message: str, level: str = "info"):
    """Show a transient InfoBar in the top-right corner."""
    level = (level or "info").lower()
    try:
        if level in ("success", "ok", "info"):
            InfoBar.success(
                title,
                message,
                parent=parent,
                position=InfoBarPosition.TOP_RIGHT,
                duration=3500,
                closable=True,
            )
        elif level in ("warning", "warn"):
            InfoBar.warning(
                title,
                message,
                parent=parent,
                position=InfoBarPosition.TOP_RIGHT,
                duration=4500,
                closable=True,
            )
        else:
            InfoBar.error(
                title,
                message,
                parent=parent,
                position=InfoBarPosition.TOP_RIGHT,
                duration=6000,
                closable=True,
            )
    except Exception:
        # Fallback to modal message boxes if InfoBar fails
        try:
            if level in ("success", "ok", "info"):
                QMessageBox.information(parent, title, message)
            elif level in ("warning", "warn"):
                QMessageBox.warning(parent, title, message)
            else:
                QMessageBox.critical(parent, title, message)
        except Exception:
            pass
