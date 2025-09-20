import json
from pathlib import Path

from openai_tts_gui.utils import _parse_ffmpeg_semver, write_sidecar_metadata


def test_write_sidecar(tmp_path):
    out = tmp_path / "a.mp3"
    out.write_bytes(b"\x00")
    write_sidecar_metadata(str(out), {"model": "m"})
    sj = Path(str(out) + ".json")
    assert sj.exists()
    data = json.loads(sj.read_text(encoding="utf-8"))
    assert data["model"] == "m"
    assert "timestamp" in data
    assert "ffmpeg" in data
    assert "os" in data


def test_parse_ffmpeg_variants():
    assert _parse_ffmpeg_semver("ffmpeg version 6.0") == (6, 0, 0)
    assert _parse_ffmpeg_semver("ffmpeg version n4.4") == (4, 4, 0)
    # date-based/nightly (treated as "new")
    assert _parse_ffmpeg_semver("ffmpeg version 2024-10-01-git-abcdef") == (2024, 10, 1)
