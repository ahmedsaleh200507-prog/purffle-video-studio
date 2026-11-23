"""Offline fallback must always yield a real complete H264/AAC MP4 when FFmpeg works.

Purposefully isolate the proof from Gemini, Groq, stock sites and GitHub keys.
Do not mark a red/green screen, JSON report or diagnostic preview as success.
"""
import json
import shutil
import subprocess
from pathlib import Path
import pytest

import offline_video
from offline_video import make_video, _kind, _text_scenes


def test_rocket_and_german_eclipse_have_actual_topic_facts():
    assert _kind("How Do Rockets Land Back on Earth?") == "rocket"
    assert _kind("Wie entsteht eine Sonnenfinsternis?") == "eclipse"
    kind, scenes, matched=_text_scenes(
        "Wie entsteht eine Sonnenfinsternis?", "de", "short")
    assert kind=="eclipse" and len(scenes)==4 and matched
    assert all("Sonnenfinsternis" in x or "Mond" in x or
               "Sonne" in x or "Kernschatten" in x
               for x in scenes)


def test_all_uploaded_shorts_have_no_503_429_dependency():
    for topic, lang in (
        ("How Do Rockets Land Back on Earth?", "en"),
        ("Wie entsteht eine Sonnenfinsternis?", "de"),
        ("Why Do Meteors Burn Up in the Sky?", "en"),
        ("Wie entstehen Tornados?", "de"),
        ("Why Does Lava Glow Red?", "en"),
    ):
        k,script,matched=_text_scenes(topic,lang,"short")
        assert k!="general" and matched and len(script)==4
        assert all(len(scene)>20 for scene in script)


def test_all_uploaded_long_topics_available_without_groq():
    for topic, lang in (
        ("How Do Electric Cars Work?", "en"),
        ("Wie entstehen Polarlichter und warum bewegen sie sich?", "de"),
        ("How Does El Niño Change Weather Around the World?", "en"),
        ("Wie funktionieren moderne Computerchips?", "de"),
        ("How Do Space Telescopes Explore the Universe?", "en"),
    ):
        kind,scenes,matched=_text_scenes(topic,lang,"long")
        assert kind!="general" and matched and len(scenes)==14


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="FFmpeg/FFprobe required")
def test_complete_real_32_second_short_not_diagnostic(tmp_path):
    result=make_video(
        topic="Why Does Lava Glow Red?",language="en",mode="short",
        output=tmp_path/"fallback-video.mp4")
    assert result["status"]=="ok"
    assert result["quality_mode"]=="offline_2d_fallback"
    assert result["visual_mode"]=="original_2d_graphics_no_stock"
    assert 29 <= result["duration"] <= 34
    assert result["resolution"]=="1080x1920"
    assert (tmp_path/"fallback-video.mp4").stat().st_size>15000
    assert (tmp_path/"captions.srt").exists()
    probe=json.loads(subprocess.check_output([
        "ffprobe","-v","error","-show_format","-show_streams",
        "-of","json",str(tmp_path/"fallback-video.mp4")]))
    assert any(x["codec_type"]=="audio" for x in probe["streams"])
    assert any(x["codec_type"]=="video" and
               x["width"]==1080 and x["height"]==1920
               for x in probe["streams"])


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="FFmpeg/FFprobe required")
def test_complete_long_documentary_render_pipeline_not_preview(tmp_path,monkeypatch):
    # Only shorten duration for CI; production LONG_SECONDS stays 602.
    monkeypatch.setattr(offline_video,"LONG_SECONDS",28)
    result=make_video(
        topic="How Do Space Telescopes Explore the Universe?",
        language="en",mode="long",output=tmp_path/"long-video.mp4")
    assert result["status"]=="ok"
    assert result["resolution"]=="1920x1080"
    assert 26 <= result["duration"] <= 31
    assert result["quality_mode"]=="offline_2d_fallback"
    script=json.loads((tmp_path/"script.json").read_text())
    assert len(script["scenes"])==14
    assert (tmp_path/"credits.json").exists()
    assert (tmp_path/"captions.srt").exists()


def test_error_routes_to_full_video_not_incomplete_preview():
    repo=Path(__file__).parents[1]
    shorts=(repo/"scripts/batch.py").read_text()
    long=(repo/"scripts/long_video.py").read_text()
    assert "mode='short'" in shorts
    assert "output=target/'fallback-video.mp4'" in shorts
    assert "mode=\"long\"" in long
    assert 'output=output/"long-video.mp4"' in long
    assert 'status="ok"' in long
