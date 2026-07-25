from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256

from PyQt6.QtGui import QPalette

from openai_tts_gui.config import apply_fusion_dark
from openai_tts_gui.config._palette import DARK_THEME
from openai_tts_gui.config._stylesheet import (
    DARK_QSS,
    REQUIRED_SELECTOR_COLORS,
    missing_required_selectors,
    selector_color_map,
)

EXPECTED_DARK_QSS_SHA256 = "9296260e66baee422ec06d4fdc1d982ca34b003d047dc39ffe5c7aa715f34f57"
EXPECTED_REQUIRED_SELECTOR_COLORS = {
    "QLabel#sectionTitle": {"color": "#b3bac5"},
    "QTextEdit#textEdit": {"border-color": "#353c45"},
    "QPushButton#primaryButton": {
        "background-color": "#7890AE",
        "color": "#FFFFFF",
    },
    "QPushButton#primaryButton:hover": {
        "background-color": "#8BA1BC",
        "border-color": "#8BA1BC",
    },
    "QProgressBar::chunk": {"background-color": "#7890ae"},
    "QLabel#parallelismStatusLabel": {"color": "#b3bac5"},
}
EXPECTED_PALETTE_ROLES = {
    QPalette.ColorRole.Window: "#202327",
    QPalette.ColorRole.WindowText: "#eceff3",
    QPalette.ColorRole.Base: "#282d33",
    QPalette.ColorRole.Button: "#30363e",
    QPalette.ColorRole.Text: "#eceff3",
    QPalette.ColorRole.Highlight: "#7890ae",
    QPalette.ColorRole.HighlightedText: "#ffffff",
}


def test_dark_stylesheet_preserves_hash_and_required_selector_colors() -> None:
    # Given: the extracted stylesheet contract from the pre-extraction facade.
    # When: the deterministic dark stylesheet is built.
    # Then: its byte-level and required selector/color semantics remain unchanged.
    assert sha256(DARK_QSS.encode()).hexdigest() == EXPECTED_DARK_QSS_SHA256
    semantic_colors = selector_color_map(DARK_QSS)
    assert {
        selector: semantic_colors[selector] for selector in EXPECTED_REQUIRED_SELECTOR_COLORS
    } == EXPECTED_REQUIRED_SELECTOR_COLORS
    assert REQUIRED_SELECTOR_COLORS == EXPECTED_REQUIRED_SELECTOR_COLORS


def test_required_selector_counterexample_identifies_removed_primary_button_rule() -> None:
    # Given: a stylesheet fixture missing the required primary-button selector.
    missing_selector = "QPushButton#primaryButton"
    malformed_stylesheet = DARK_QSS.replace(
        "QPushButton#primaryButton {", "QPushButton#removedPrimaryButton {", 1
    )

    # When: the semantic fixture validates the malformed stylesheet.
    missing = missing_required_selectors(malformed_stylesheet)

    # Then: the required selector removal is reported rather than silently accepted.
    assert missing == (missing_selector,)


def test_palette_data_is_immutable_and_application_facade_preserves_palette(qapp) -> None:
    # Given: the palette data and a fresh QApplication.
    assert isinstance(DARK_THEME, Mapping)
    assert not hasattr(DARK_THEME, "__setitem__")

    # When: the public config facade applies the Fusion dark composition.
    apply_fusion_dark(qapp)

    # Then: the application receives the pre-extraction dark stylesheet and palette roles.
    assert qapp.styleSheet() == DARK_QSS
    assert {
        role: qapp.palette().color(role).name() for role in EXPECTED_PALETTE_ROLES
    } == EXPECTED_PALETTE_ROLES
    assert (
        qapp.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text).name()
        == "#7d8794"
    )
