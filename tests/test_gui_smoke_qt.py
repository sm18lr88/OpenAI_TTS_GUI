from openai_tts_gui.gui import TTSWindow


def test_window_boots(qtbot):
    w = TTSWindow()
    qtbot.addWidget(w)
    w.show()
    assert w.isVisible()
    w.close()


def test_window_can_grab_pixmap(qtbot, tmp_path):
    w = TTSWindow()
    qtbot.addWidget(w)
    w.show()
    pix = w.grab()
    assert pix.width() > 0 and pix.height() > 0
    # ensure saving works
    out = tmp_path / "snap.png"
    pix.save(str(out))
    assert out.exists() and out.stat().st_size > 0
    w.close()
