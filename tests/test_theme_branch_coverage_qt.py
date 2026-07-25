from __future__ import annotations

from openai_tts_gui.config.theme import (
    DARK_QSS,
    LIGHT_QSS,
    LIGHT_THEME,
    apply_fusion_dark,
    build_stylesheet,
)


def test_stylesheet_selects_light_and_dark_theme_and_applies_fusion(qapp) -> None:
    assert build_stylesheet(LIGHT_THEME) == LIGHT_QSS
    assert build_stylesheet(object()) == DARK_QSS

    apply_fusion_dark(qapp)

    assert qapp.styleSheet() == DARK_QSS
