"""Failure previews are VIEWABLE, but never silently reported as completed.

No API or stock network calls. FFmpeg/Pillow tests use temporary synthetic
footage; they do not claim a successful real production.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from failure_preview import PREVIEW_NAME, make_failure_preview

FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")
pytestmark = pytest.mark.skipif(not FFMPEG, reason="ffmpeg/ffprobe required")


def _probe(path):
    return json.loads(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_streams",
         "-show_format", "-of", "json", str(path)]))


def _sample_video(path: Path, size="320x568", seconds=2):
    subprocess.run([
        "ffmpeg", "-hide_banner", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=44100",
        "-t", str(seconds), "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)],
        check=True, timeout=50)


def test_failed_short_with_no_script_outputs_playable_9x16_preview(tmp_path):
    pytest.importorskip("PIL")
    path = tmp_path / PREVIEW_NAME
    info = make_failure_preview(
        output=path, topic="Why do octopuses have three hearts?",
        stage="science_review", size=(720, 1280))
    assert info["preview_status"] == "incomplete_not_publishable"
    assert info["preview_kind"] == "diagnostic_card_no_narration"
    assert path.is_file()
    probe = _probe(path)
    video = next(x for x in probe["streams"] if x["codec_type"] == "video")
    assert (video["width"], video["height"]) == (720, 1280)
    assert any(x["codec_type"] == "audio" for x in probe["streams"])
    assert 7.5 < float(probe["format"]["duration"]) < 8.5
    assert "status" not in info and "mp4" not in info


def test_failed_short_preserves_actual_rendered_mp4_as_preview(tmp_path):
    render = tmp_path / "render"
    render.mkdir()
    original = render / "partial.mp4"
    _sample_video(original)
    dest = tmp_path / PREVIEW_NAME
    info = make_failure_preview(
        output=dest, topic="Why do steel ships float?",
        stage="final_opening_qa", size=(720, 1280), rendered_dir=render)
    assert info["preview_kind"] == "unverified_rendered_mp4"
    assert dest.read_bytes() == original.read_bytes()
    assert "not_publishable" in info["preview_status"]
    assert _probe(dest)["format"]["duration"]


def test_long_keeps_earlier_rendered_chapters_with_audio(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    for number in (1, 2):
        _sample_video(work / f"chapter-{number:02d}.mp4",
                      size="320x180", seconds=2)
    dest = tmp_path / PREVIEW_NAME
    info = make_failure_preview(
        output=dest, topic="Why do tornadoes happen?",
        stage="real_stock", size=(1920, 1080),
        long_chapters_dir=work)
    assert info["preview_kind"] == "completed_chapters_only"
    assert info["preview_chapter_count"] == 2
    assert 3.5 < info["preview_duration"] < 4.5
    assert any(s["codec_type"] == "audio" for s in _probe(dest)["streams"])


def test_long_with_no_available_chapter_still_has_playable_preview(tmp_path):
    pytest.importorskip("PIL")
    path = tmp_path / PREVIEW_NAME
    info = make_failure_preview(
        output=path, topic="Why does lightning come before thunder?",
        stage="long_stock_preflight", size=(1920, 1080),
        long_chapters_dir=tmp_path / "empty")
    assert info["preview_kind"] == "diagnostic_card_no_narration"
    assert next(x for x in _probe(path)["streams"]
                if x["codec_type"] == "video")["width"] == 1920


def test_publisher_and_aggregator_cannot_mistake_preview_for_success():
    root = Path(__file__).parents[1]
    batch = (root / "scripts/batch.py").read_text(encoding="utf-8")
    long = (root / "scripts/long_video.py").read_text(encoding="utf-8")
    workflow = (root / ".github/workflows/long-batch.yml").read_text(
        encoding="utf-8")
    assert batch.index("make_failure_preview(") < batch.index(
        "for partial in (target / 'render').rglob('*.mp4')")
    assert "'status': 'failed'" in batch
    assert "result['status'] == 'ok'" in batch
    assert "PREVIEW_INCOMPLETE.mp4" in workflow
    assert "make_failure_preview(" in long
    assert "status=\"ok\"" in long
