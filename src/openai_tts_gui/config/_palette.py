from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from PyQt6.QtGui import QColor, QPalette

ACCENT: Final = "#7890AE"
ACCENT_HOVER: Final = "#8BA1BC"
ACCENT_PRESSED: Final = "#5F7899"


def _theme_colors(values: tuple[tuple[str, str], ...]) -> Mapping[str, QColor]:
    return MappingProxyType({name: QColor(color) for name, color in values})


DARK_THEME: Final = _theme_colors(
    (
        ("background", "#202327"),
        ("panel_background", "#202327"),
        ("widget_background", "#282D33"),
        ("button_background", "#30363E"),
        ("button_hover", "#39404A"),
        ("text", "#ECEFF3"),
        ("muted_text", "#B3BAC5"),
        ("disabled_text", "#7D8794"),
        ("button_text", "#ECEFF3"),
        ("border", "#444C57"),
        ("panel_border", "#353C45"),
        ("status_background", "#202327"),
        ("status_text", "#B3BAC5"),
        ("progress_bar_chunk", ACCENT),
    )
)

LIGHT_THEME: Final = _theme_colors(
    (
        ("background", "#EFF1F5"),
        ("panel_background", "#F8FAFC"),
        ("widget_background", "#FFFFFF"),
        ("button_background", "#DCE0E8"),
        ("button_hover", "#E2E8F0"),
        ("text", "#334155"),
        ("muted_text", "#64748B"),
        ("disabled_text", "#8A94A6"),
        ("button_text", "#4C4F69"),
        ("border", "#BCC0CC"),
        ("panel_border", "#CBD5E1"),
        ("status_background", "#DCE0E8"),
        ("status_text", "#4C4F69"),
        ("progress_bar_chunk", ACCENT),
    )
)

DARK_FUSION_PALETTE: Final = MappingProxyType(
    {
        QPalette.ColorRole.Window: DARK_THEME["background"],
        QPalette.ColorRole.WindowText: DARK_THEME["text"],
        QPalette.ColorRole.Base: DARK_THEME["widget_background"],
        QPalette.ColorRole.AlternateBase: DARK_THEME["background"],
        QPalette.ColorRole.ToolTipBase: DARK_THEME["widget_background"],
        QPalette.ColorRole.ToolTipText: DARK_THEME["text"],
        QPalette.ColorRole.Text: DARK_THEME["text"],
        QPalette.ColorRole.Button: DARK_THEME["button_background"],
        QPalette.ColorRole.ButtonText: DARK_THEME["button_text"],
        QPalette.ColorRole.BrightText: QColor("#FCA5A5"),
        QPalette.ColorRole.Link: QColor(ACCENT),
        QPalette.ColorRole.Highlight: QColor(ACCENT),
        QPalette.ColorRole.HighlightedText: QColor("#FFFFFF"),
    }
)

DARK_DISABLED_FUSION_PALETTE: Final = MappingProxyType(
    {
        QPalette.ColorRole.Text: DARK_THEME["disabled_text"],
        QPalette.ColorRole.ButtonText: DARK_THEME["disabled_text"],
    }
)
