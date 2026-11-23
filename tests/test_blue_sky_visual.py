"""Repro: V5 #103 MP4 accepted gray sky as blue-wavelength B-roll."""
from PIL import Image
import pytest

from blue_sky_visual import (
    requires_blue_sky_color, strong_blue_fraction, check_visible_blue_sky)
from visual_director import build_contract, verify_visible_event_or_illustrative_subject


def test_v5_real_proof_second_scene_requires_blue_despite_generic_cloud_query():
    c = build_contract({
        "narration": "Blue wavelengths scatter much more than red ones.",
        "main_character": "", "object": "sunlight", "action": "ambient",
        "location": "open sky", "time": "",
        "visual_search_query": "sunlight through clouds",
    }, "Why is the sky blue?", 2)
    assert c["family"] == "illustrative_subject"
    assert c["visible_blue_sky_expected"] is True
    assert not build_contract({
        "narration": "At sunset the orange sky contrasts with the blue sky.",
        "main_character": "", "object": "sky", "action": "ambient",
        "location": "outdoors", "time": "",
        "visual_search_query": "sunset sky",
    }, "Why is the sky blue?", 3)["visible_blue_sky_expected"]


def test_color_cue_rejects_overcast_gray_but_accepts_daytime_blue():
    blue = Image.new("RGB", (200, 320), (40, 112, 194))
    gray = Image.new("RGB", (200, 320), (130, 138, 150))
    assert strong_blue_fraction(blue) > .9
    assert strong_blue_fraction(gray) < .1
    valid = check_visible_blue_sky(None, 5, .5, frames=[blue, gray, blue])
    assert valid["verified"] is True
    invalid = check_visible_blue_sky(None, 5, .5, frames=[gray, gray, blue])
    assert invalid["verified"] is False
    assert invalid["method"] == "sampled_final_portrait_crop_blue_color_cue"


def test_real_proof_gray_sky_cannot_pass_director_after_clip_match(monkeypatch):
    c = build_contract({
        "narration": "Blue wavelengths scatter much more than red ones.",
        "main_character": "", "object": "sunlight", "action": "ambient",
        "location": "open sky", "time": "",
        "visual_search_query": "sunlight through clouds",
    }, "Why is the sky blue?", 2)
    from blue_sky_visual import check_visible_blue_sky
    monkeypatch.setattr("blue_sky_visual.check_visible_blue_sky",
                        lambda *args, **kwargs: {
                            "verified": False, "blue_coverage": [.12, .20, .26]})
    with pytest.raises(ValueError, match="blue_sky_not_visible"):
        verify_visible_event_or_illustrative_subject(
            "fake-clip.mp4", 5, .5, c,
            {"verification": "local_clip_screening"})


def test_non_sky_topics_and_intentional_sunsets_are_not_color_gated():
    assert not requires_blue_sky_color(
        "Why do ships float?", "Blue waves carry boats.", "ocean")
    assert not requires_blue_sky_color(
        "Why is the sky blue?",
        "At sunset, orange light dominates the sky.", "sky")
    assert requires_blue_sky_color(
        "Warum ist der Himmel blau?",
        "Blaues Licht wird stärker gestreut.", "Himmel")
