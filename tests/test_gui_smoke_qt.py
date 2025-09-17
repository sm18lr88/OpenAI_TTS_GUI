from gui import TTSWindow


def test_window_boots(qtbot):
    w = TTSWindow()
    qtbot.addWidget(w)
    w.show()
    assert w.isVisible()
    w.close()
