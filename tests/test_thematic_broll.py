"""Curated, honest thematic B-roll must not become random footage."""
import json

import pytest

from media_validation import SceneMatcher, SceneSpec, ValidationError
from studio_runtime import StrictVisuals, thematic_scene_plans


@pytest.fixture
def scene():
    return {
        "main_character": "", "object": "invisible process",
        "action": "explaining", "location": "", "time": "",
        "visual_search_query": "unavailable very specific footage",
    }


@pytest.mark.parametrize("topic,visible_subject,expected_query", [
    ("What Really Happens to Your Body in the Deepest Part of the Ocean?",
     "ocean", "deep ocean underwater"),
    ("Why Is There a Giant Hole Burning in the Middle of a Desert?",
     "fire", "burning fire flames"),
    ("What Scientists Discovered Beneath Antarctica's Ice Is Incredible",
     "glacier", "glacier ice"),
    ("The Mysterious Island Where Thousands of Snakes Live",
     "snake", "snake slithering"),
    ("Why Does the Ocean Glow Bright Blue at Night?",
     "ocean", "ocean waves at night"),
    ("The Terrifying Truth About the World's Deepest Cave",
     "cave", "cave interior"),
    ("What Happens When Lightning Strikes a Volcano?",
     "volcano", "volcano erupting"),
    ("The Strange Forest Where Trees Grow in Impossible Shapes",
     "forest", "forest trees"),
    ("Why Are There Giant Underwater Lakes at the Bottom of the Ocean?",
     "ocean", "deep ocean underwater"),
    ("The Mysterious Explosion That Flattened Millions of Trees in Siberia",
     "forest", "forest trees"),
])
def test_all_ten_reported_video_topics_have_related_filmable_alternatives(
        scene, topic, visible_subject, expected_query):
    proposals = thematic_scene_plans(scene, topic)
    assert proposals
    assert len(proposals) <= 4
    assert proposals[0]["object"] == visible_subject
    assert proposals[0]["visual_search_query"] == expected_query
    assert all(p["main_character"] == "" and p["action"] == "ambient"
               for p in proposals)
    assert len({p["visual_search_query"] for p in proposals}) == len(proposals)


def test_unknown_topic_never_introduces_unrelated_random_stock(scene):
    assert thematic_scene_plans(scene, "A completely unknown technical problem") == []


@pytest.mark.parametrize("obj,query,metadata", [
    ("volcano", "volcano erupting", "volcanic eruption mountain"),
    ("fire", "burning fire flames", "flames fire burning"),
    ("iceberg", "iceberg floating", "icebergs near the coast"),
    ("snake", "snake slithering", "snake wildlife closeup"),
    ("forest", "forest trees", "forest landscape"),
    ("cave", "cave interior", "cavern with rocks"),
])
def test_ambient_documentary_subject_is_grounded_in_provider_metadata(obj, query, metadata):
    spec = SceneSpec(object=obj, action="ambient", visual_search_query=query)
    assert SceneMatcher.validate_metadata(spec, metadata) >= .15


def test_unrelated_metadata_and_unfilmable_action_still_rejected():
    themed = SceneSpec(object="volcano", action="ambient",
                       visual_search_query="volcano erupting")
    with pytest.raises(ValidationError, match="grounding"):
        SceneMatcher.validate_metadata(themed, "a person sitting at a computer")
    exact = SceneSpec(object="cave", action="exploring",
                      visual_search_query="cave interior")
    with pytest.raises(ValidationError):
        SceneMatcher.validate_metadata(exact, "cavern with rocks")


def test_thematic_fallback_keeps_per_scene_verification_and_disclosure(
        tmp_path, monkeypatch):
    visual = StrictVisuals.__new__(StrictVisuals)
    visual.report = {"scenes": [], "state": "searching"}
    monkeypatch.setattr(visual, "_save", lambda: None)
    queries = []

    def fake_film_search(idx, query, prompt, topic, need, dest_dir):
        plan = json.loads(prompt)
        queries.append(query)
        if query != "deep ocean underwater":
            visual.report["scenes"].append({
                "index": idx + 1, "status": "failed", "plan": plan,
                "rejections": [{"reason": "metadata action not indexed"}],
            })
            raise RuntimeError("No suitable verified REAL VIDEO for scene 1")
        visual.report["scenes"].append({
            "index": idx + 1, "status": "selected", "plan": plan,
            "source": "pixabay", "sha256": "verified-different-clip",
            "match": {"visual_score": .3}, "license": {"id": "PIXABAY"},
        })
        return "verified-real-moving-video"

    monkeypatch.setattr(visual, "for_scene", fake_film_search)
    plan = dict(main_character="", object="pressure gauge", action="recording",
                location="ocean", time="", visual_search_query="pressure gauge underwater")
    returned = visual.for_scenes(
        [("pressure gauge underwater", json.dumps(plan), 5)],
        "What Really Happens to Your Body in the Deepest Part of the Ocean?", tmp_path)
    assert returned == ["verified-real-moving-video"]
    assert queries == ["pressure gauge underwater", "pressure gauge",
                       "deep ocean underwater"]
    assert len(visual.report["scenes"]) == 1
    chosen = visual.report["scenes"][0]
    assert chosen["visual_mode"] == "thematic_context"
    assert chosen["illustrative_not_exact_event"] is True
    assert chosen["requested_query"] == "pressure gauge underwater"
    assert len(chosen["search_attempts"]) == 2


def test_failed_thematic_search_cannot_be_called_success(tmp_path, monkeypatch):
    visual = StrictVisuals.__new__(StrictVisuals)
    visual.report = {"scenes": [], "state": "searching"}
    monkeypatch.setattr(visual, "_save", lambda: None)
    def reject_everything(idx, query, prompt, topic, need, dest_dir):
        visual.report["scenes"].append({
            "index": 1, "status": "failed", "plan": json.loads(prompt),
            "rejections": [],
        })
        raise RuntimeError("No suitable verified REAL VIDEO for scene 1")
    monkeypatch.setattr(visual, "for_scene", reject_everything)
    plan = dict(main_character="", object="forest", action="moving",
                location="", time="", visual_search_query="forest trees")
    with pytest.raises(RuntimeError, match="No suitable verified REAL VIDEO"):
        visual.for_scenes([("forest trees", json.dumps(plan), 4)],
                          "The Strange Forest Where Trees Grow in Impossible Shapes",
                          tmp_path)
    assert all(s["status"] == "failed" for s in visual.report["scenes"])
