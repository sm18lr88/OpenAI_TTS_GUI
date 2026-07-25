from __future__ import annotations

import pytest

from openai_tts_gui.gui import TTSWindow


def test_window_forwarding_routes_each_extracted_collaborator(qtbot, monkeypatch) -> None:
    # Given: a visible window whose collaborator operations are observable.
    window = TTSWindow()
    qtbot.addWidget(window)
    window.show()
    calls: list[str] = []

    monkeypatch.setattr(window._window_settings, "update_counts", lambda: calls.append("settings"))
    monkeypatch.setattr(
        window._result_actions,
        "refresh_request_ids_button",
        lambda: calls.append("results"),
    )
    monkeypatch.setattr(
        window._run_wiring,
        "cancel_tts_creation",
        lambda: calls.append("run"),
    )

    # When: the TTSWindow compatibility slots are invoked.
    window.update_counts()
    window._refresh_request_ids_button()
    window.cancel_tts_creation()

    # Then: each public/legacy window slot routes to its cohesive owner.
    assert calls == ["settings", "results", "run"]


def test_window_forwarding_rejects_aliases_unknown_names_and_missing_collaborators(qtbot) -> None:
    # Given: a fully initialized window with concrete collaborators.
    window = TTSWindow()
    qtbot.addWidget(window)

    # When / Then: only shipped legacy names resolve; aliases and deleted owners do not.
    with pytest.raises(AttributeError):
        _ = window.copy_request_ids
    with pytest.raises(AttributeError):
        _ = window.unknown_window_operation
    del window._result_actions
    with pytest.raises(AttributeError):
        _ = window._copy_request_ids
