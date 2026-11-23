from conftest import write_piper_report
"""Regression tests for ten user-requested Shorts topics and realistic crop quality."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from media_validation import SceneMatcher, SceneSpec, ValidationError
from studio_runtime import thematic_scene_plans, _native_portrait_scale
from render_job import validate_result


TOPICS = (
    ("What Would Happen If You Fell Into a Black Hole?", "sky", "night sky stars"),
    ("Why Is There a Giant Burning Crater in the Desert?", "fire", "burning fire flames"),
    ("The Terrifying Power of the World's Biggest Tsunamis", "wave", "storm waves"),
    ("What Secrets Are Hidden Beneath Antarctica's Ice?", "glacier", "glacier ice"),
    ("Why Do Some Volcanoes Erupt Without Warning?", "volcano", "volcano erupting"),
    ("The Mysterious Creatures Living in the Deepest Ocean", "ocean", "deep ocean underwater"),
    ("What Would Happen If Earth Stopped Spinning?", "earth", "earth from space"),
    ("The Incredible Mystery of the Bermuda Triangle", "ocean", "ocean waves"),
    ("Why Are There Thousands of Abandoned Cities Around the World?", "building", "abandoned building"),
    ("What Really Happens Inside the Eye of a Hurricane?", "storm", "storm clouds"),
)


@pytest.mark.parametrize("topic,subject,query", TOPICS)
def test_all_ten_topics_have_relevant_real_footage_searches(topic, subject, query):
    original = dict(main_character="", object="unfilmable exact event",
                    action="happening", location="", time="",
                    visual_search_query="too specific for stock")
    choices = thematic_scene_plans(original, topic)
    assert choices and choices[0]["object"] == subject
    assert choices[0]["visual_search_query"] == query
    assert len(choices) <= 4
    assert len({choice["visual_search_query"] for choice in choices}) == len(choices)
    assert all(choice["action"] == "ambient" and choice["main_character"] == ""
               for choice in choices)


@pytest.mark.parametrize("subject,query,tags", [
    ("sky", "night sky stars", "blue night sky with stars"),
    ("wave", "storm waves", "powerful ocean waves"),
    ("earth", "earth from space", "earth viewed from space station"),
    ("telescope", "observatory telescope", "astronomy telescope in observatory"),
    ("ship", "ship sailing sea", "ship on the sea"),
    ("airplane", "airplane flying sky", "plane flying through the sky"),
    ("building", "abandoned building", "abandoned building exterior"),
    ("city", "empty city streets", "empty city streets skyline"),
    ("storm", "storm clouds", "storm clouds in the sky"),
])
def test_visual_objects_can_be_tagged_without_unfilmable_ambient_action(
        subject, query, tags):
    spec = SceneSpec(object=subject, action="ambient",
                     visual_search_query=query)
    assert SceneMatcher.validate_metadata(spec, tags) >= .15


def test_unrelated_stock_still_rejected():
    spec = SceneSpec(object="earth", action="ambient",
                     visual_search_query="earth from space")
    with pytest.raises(ValidationError):
        SceneMatcher.validate_metadata(spec, "guy playing guitar indoors")


def test_1080p_landscape_needs_less_than_20_percent_resize():
    scale = _native_portrait_scale({"width": 1920, "height": 1080}, 720, 1280)
    assert 1 < scale < 1.2
    assert _native_portrait_scale({"width": 1280, "height": 720}, 720, 1280) > 1.2
    assert _native_portrait_scale({"width": 1080, "height": 1920}, 720, 1280) <= 1.0


@pytest.mark.parametrize("scale,accepted", [(1.0, True), (1.1852, True), (1.3, False)])
def test_output_uses_bounded_documented_upscale(tmp_path, monkeypatch, scale, accepted):
    monkeypatch.setenv("RESOLUTION", "720x1280")
    monkeypatch.setenv("PURFFLE_MAX_PORTRAIT_UPSCALE", "1.20")
    clip = tmp_path / "short.mp4"
    clip.write_bytes(b"validated clip mock")
    captions = tmp_path / "captions.srt"
    captions.write_text("1\n00:00:00,000 --> 00:00:01,000\nOcean!\n")
    footage = tmp_path / "footage-report.json"
    footage.write_text(json.dumps({"scenes": [{
        "index": 1, "status": "selected", "source": "pixabay",
        "sha256": "some-real-digest", "license": {"id": "PIXABAY"},
        "quality": {"portrait_crop_scale": scale},
        "match": {"visual_score": .31},
    }]}))
    fake = {"width": 720, "height": 1280, "duration": 25.0, "has_audio": True}
    with patch("media_validation.QualityValidator.validate", return_value=fake):
        if accepted:
            info, report = validate_result(clip, {"language": "de", "voice": "piper:de_DE-thorsten-medium", "timing": "aligned"},
                                           captions, footage, voice_report=write_piper_report(clip.parent))
            assert report["scenes"][0]["quality"]["portrait_crop_scale"] == scale
        else:
            with pytest.raises(RuntimeError, match="insufficient_native_resolution"):
                validate_result(clip, {"language": "de", "voice": "piper:de_DE-thorsten-medium", "timing": "aligned"},
                                captions, footage, voice_report=write_piper_report(clip.parent))


def test_unknown_topic_does_not_fall_back_to_random_video():
    original = dict(main_character="", object="phone", action="ringing",
                    location="", time="", visual_search_query="phone ring")
    assert thematic_scene_plans(original, "A completely unknown technical problem") == []
