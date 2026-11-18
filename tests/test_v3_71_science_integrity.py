"""Regress the two technically successful but editorially misleading #71 MP4s.

These checks never claim that semantic similarity proves event identity; they
prevent topic drift at stock-selection time and inject science text verified
against NOAA/AOML and USGS/NPS educational resources.
"""
import json
from pathlib import Path

import pytest

from fact_checked_topics import (ground_verified_documentary,
                                 verified_documentary_kind)
from media_first import _grounded_candidates
from science_fact_guard import validate_unsourced_quantities


VOLCANO = "How Do Volcanoes Create New Islands?"
HURRICANE = "What Happens Inside a Powerful Hurricane?"


def test_71_volcanic_island_footage_never_contains_unrelated_lightning():
    plans = _grounded_candidates(VOLCANO, llm=None)
    query_list = [p["visual_search_query"].casefold() for p in plans]
    assert "volcano erupting" in query_list
    assert "volcanic lava" in query_list
    assert any("island" in q for q in query_list)
    assert not any("lightning" in q or "storm" in q for q in query_list)


def test_71_groq_lightning_hallucination_cannot_reenter_palette():
    class MockLLM:
        def complete_json(self, system, prompt, schema):
            return {"shots": [
                {"object": "lightning", "query": "lightning splits island"},
                {"object": "lava", "query": "volcanic lava flow"},
                {"object": "smartphone", "query": "smartphone closeup filming"},
            ]}
    plans = _grounded_candidates(VOLCANO, MockLLM())
    query_list = [p["visual_search_query"].casefold() for p in plans]
    assert not any("lightning" in q or "smartphone" in q for q in query_list)
    assert "volcanic lava flow" in query_list


def test_71_hurricane_specific_shots_take_priority_and_calm_trees_excluded():
    plans = _grounded_candidates(HURRICANE, llm=None)
    queries = [p["visual_search_query"].casefold() for p in plans]
    assert queries[0] == "hurricane satellite clouds"
    assert "hurricane eyewall clouds" in queries
    assert "trees blowing in wind" not in queries
    assert any("ocean" in q for q in queries)


@pytest.mark.parametrize("topic,kind", [
    (VOLCANO, "volcanic_island"),
    (HURRICANE, "hurricane_eye"),
])
def test_71_editorial_topic_recognition(topic, kind):
    assert verified_documentary_kind(topic) == kind


@pytest.mark.parametrize("topic", [
    "Why Do Some Beaches Have Black Sand?",
    "What Happens When Lightning Strikes a Volcano?",
    "How Do Dolphins Communicate Underwater?",
])
def test_unrelated_topics_keep_normal_script_pipeline(topic):
    original = {"title": "Whatever", "scenes": [{"narration": "Original."}]}
    assert ground_verified_documentary(original, topic, "en", 4) is original


@pytest.mark.parametrize("topic", [VOLCANO, HURRICANE])
@pytest.mark.parametrize("count", [3, 4])
@pytest.mark.parametrize("language", ["en", "de"])
def test_known_source_backed_story_no_fabricated_claims(topic, count, language):
    fabricated = {"title": "Lightning builds floating islands",
                  "description": "200 km/h and 300 watts",
                  "scenes": [{"narration":
                             "Lightning splits floating volcanic islands after 30 millibars."}]}
    verified = ground_verified_documentary(fabricated, topic, language, count)
    assert len(verified["scenes"]) == count
    text = json.dumps(verified, ensure_ascii=False).casefold()
    for false_claim in ("floating", "float like", "lightning splits",
                        "lightning's secret", "30 millibars", "200 km/h",
                        "300 watts", "follow for more"):
        assert false_claim not in text
    for sentence in verified["scenes"]:
        assert 5 <= len(sentence["narration"].split()) <= 23
    assert verified["category"] == "education"


def test_known_hurricane_script_contains_no_unsupported_quantities():
    from types import SimpleNamespace
    data = ground_verified_documentary({}, HURRICANE, "en", 4)
    script = SimpleNamespace(scenes=[SimpleNamespace(**x) for x in data["scenes"]])
    validate_unsourced_quantities(script, HURRICANE)


def test_no_documentary_end_cta_is_drawn():
    render = (Path(__file__).parents[1] / "scripts" / "render_job.py").read_text()
    assert "end_cta=''" in render
