"""Regression for real #70 ZIP: Lightning Shorts with irrelevant roots searches.

User supplied a single video, with a valid tree clip for scene 1 and 132
rejections in scene 2 (tree roots + an impossible 'tap' action).
The final movie didn't render. The narrator also invented an Elm Street
incident and an unsupported 300,000-volt measurement.
"""
import json

import pytest

from fact_checked_topics import ground_lightning_explainer
from studio_runtime import StrictVisuals, thematic_scene_plans
from media_validation import SceneMatcher, SceneSpec, ValidationError


TOPIC = "Why Does Lightning Strike the Same Place Again and Again?"
BAD_LLM = {
    "title": "Lightning's Favorite Spot: The Hidden Reason",
    "description": "A fictional lightning incident on Elm Street",
    "hashtags": ["#storm"], "tags": ["Elm Street"],
    "scenes": [
        {
            "narration": "The oak on Elm Street was hit 12 times!",
            "main_character": "", "object": "tree roots", "action": "tap",
            "location": "ground", "time": "",
            "visual_search_query": "tree roots moist soil",
        },
        {
            "narration": "Scientists measured 300,000 volts above other trees!",
            "main_character": "", "object": "tree", "action": "measure",
            "location": "Elm Street", "time": "",
            "visual_search_query": "tree electric charge measurement",
        },
    ],
}


def test_exact_70_topic_replaces_made_up_facts_with_grounded_short():
    original = json.loads(json.dumps(BAD_LLM))
    new = ground_lightning_explainer(original, TOPIC, "en")
    assert original == BAD_LLM  # source not mutated
    assert len(new["scenes"]) == 5
    assert all(5 < len(s["narration"]) < 170 for s in new["scenes"])
    alltext = json.dumps(new, ensure_ascii=False).lower()
    assert "elm street" not in alltext
    assert "300,000" not in alltext
    assert "12 times" not in alltext
    assert "scientists measured" not in alltext
    assert "indoors" in alltext
    assert "upward spark" in alltext
    assert "same spot" in alltext
    assert len({s["visual_search_query"] for s in new["scenes"]}) == 5
    for s in new["scenes"]:
        assert s["search_query"] == s["visual_search_query"]
        assert s["main_character"] == ""
        assert s["action"] == "ambient"
        assert s["object"] in {"cloud", "tree", "lightning"}


def test_german_support_without_english_voice_script():
    new = ground_lightning_explainer(BAD_LLM, TOPIC, "de")
    assert "Ein Blitz" in new["scenes"][0]["narration"]
    assert "Geh" in new["scenes"][-1]["narration"] or "geh" in new["scenes"][-1]["narration"]
    assert new["scenes"][0]["visual_search_query"] == "lightning storm"


def test_other_science_topics_and_specific_user_stories_are_not_replaced():
    for topic in (
        "Why does lightning strike a volcano?",
        "The Lightning Strike on Elm Street in 1987",
        "How do trees grow underground?",
        "Why do hurricanes form?",
    ):
        assert ground_lightning_explainer(BAD_LLM, topic, "en") is BAD_LLM


def test_70_topic_has_four_distinct_general_filmable_broll_queries():
    plan = dict(main_character="", object="tree roots", action="tap",
                location="ground", time="", visual_search_query="tree roots moist soil")
    replans = thematic_scene_plans(plan, TOPIC)
    assert [p["visual_search_query"] for p in replans] == [
        "lightning storm", "storm clouds", "trees blowing in wind", "dark storm sky",
    ]
    assert all(p["action"] == "ambient" for p in replans)
    assert all(p["object"] in {"lightning", "cloud", "tree", "sky"} for p in replans)
    assert thematic_scene_plans(plan, "Why do birds fly?") == []


@pytest.mark.parametrize("obj,query,metadata", [
    ("lightning", "lightning storm", "lightning and thunderstorms"),
    ("tree", "trees blowing in wind", "trees nature wind"),
    ("cloud", "storm clouds", "clouds stormy dark sky"),
    ("sky", "dark storm sky", "dark storm sky clouds"),
])
def test_grounded_ambient_metadata_will_not_demand_fictional_root_action(
        obj, query, metadata):
    scene = SceneSpec(object=obj, action="ambient", visual_search_query=query)
    assert SceneMatcher.validate_metadata(scene, metadata) >= .15


def test_offtopic_metadata_still_rejected():
    scene = SceneSpec(object="lightning", action="ambient",
                      visual_search_query="lightning storm")
    with pytest.raises(ValidationError):
        SceneMatcher.validate_metadata(scene, "chef preparing pasta in restaurant")


def test_70_fallback_can_select_checked_new_lightning_clip(tmp_path, monkeypatch):
    visual = StrictVisuals.__new__(StrictVisuals)
    visual.report = {"scenes": [], "state": "searching"}
    monkeypatch.setattr(visual, "_save", lambda: None)
    seen_queries = []

    def select(idx, query, prompt, topic, need, dest):
        plan = json.loads(prompt)
        seen_queries.append(plan["visual_search_query"])
        if plan["visual_search_query"] != "lightning storm":
            visual.report["scenes"].append(
                {"index": idx + 1, "status": "failed", "plan": plan,
                 "rejections": [{"reason": "metadata lacks object/action grounding"}]})
            raise RuntimeError("No suitable verified REAL VIDEO for scene 2")
        visual.report["scenes"].append(
            {"index": idx + 1, "status": "selected", "plan": plan,
             "source": "pixabay", "sha256": "different lightning clip",
             "license": {"id": "Pixabay"}, "match": {"visual_score": 0.29}})
        return "a different validated lightning clip"

    monkeypatch.setattr(visual, "for_scene", select)
    plan = dict(main_character="", object="tree roots", action="tap",
                location="ground", time="", visual_search_query="tree roots moist soil")
    got = visual.for_scenes([("tree roots moist soil", json.dumps(plan), 5)],
                            TOPIC, tmp_path)
    assert got == ["a different validated lightning clip"]
    assert seen_queries == ["tree roots moist soil", "tree roots", "lightning storm"]
    final = visual.report["scenes"][0]
    assert final["visual_mode"] == "thematic_context"
    assert final["illustrative_not_exact_event"] is True
    assert final["requested_query"] == "tree roots moist soil"
    assert len(final["search_attempts"]) == 2
