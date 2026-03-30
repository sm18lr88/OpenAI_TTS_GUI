from openai_tts_gui.presets import load_presets, save_presets


def test_save_presets_creates_parent_directory(tmp_path):
    dest = tmp_path / "nested" / "presets.json"
    assert save_presets({"demo": "hello"}, filename=str(dest))
    assert load_presets(filename=str(dest)) == {"demo": "hello"}
