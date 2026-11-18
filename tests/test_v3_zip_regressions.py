"""Regress uploaded V3 run: parts 1/3 failed without ANY provider searches;
part 4 rendered a hurricane MP4 but its LLM invented precise measurements.
"""
import json
from types import SimpleNamespace

import pytest

from batch import classify_failure
from media_first import _grounded_candidates, prepare_verified_palette
from media_validation import SceneMatcher, SceneSpec, ValidationError
from science_fact_guard import validate_unsourced_quantities
from topic_footage import deterministic_stock_shots, related_to_topic, subject_terms, words


NORTHERN = "What Makes the Northern Lights Dance Across the Sky?"
BLACK_SAND = "Why Do Some Beaches Have Black Sand?"
HURRICANE = "What Happens Inside a Powerful Hurricane?"


@pytest.mark.parametrize("topic,object_name,first_query", [
    (NORTHERN, "aurora", "aurora borealis"),
    (BLACK_SAND, "sand", "black sand beach"),
    (HURRICANE, "hurricane", "hurricane satellite clouds"),
])
def test_real_zip_topics_produce_specific_stock_queries_without_groq(
        topic, object_name, first_query):
    shots = _grounded_candidates(topic, llm=None)
    assert len(shots) >= 3
    assert shots[0]["object"] == object_name
    assert shots[0]["visual_search_query"] == first_query
    assert all(shot["action"] == "ambient" for shot in shots)


def test_unknown_subject_still_refuses_random_filler():
    assert _grounded_candidates("Obscure xyzqvx abstract invention", None) == []


class MockLLM:
    def __init__(self, shots):
        self.shots = shots

    def complete_json(self, system, prompt, schema):
        return {"shots": self.shots}


def test_groq_synonym_aurora_is_accepted_and_smartphone_is_rejected():
    shots = _grounded_candidates(NORTHERN, MockLLM([
        {"object": "aurora", "query": "aurora dancing northern sky"},
        {"object": "person", "query": "person scrolling smartphone"},
        {"object": "lights", "query": "northern lights timelapse"},
    ]))
    queries = [x["visual_search_query"] for x in shots]
    assert "aurora dancing northern sky" in queries
    assert "person scrolling smartphone" not in queries


def test_plural_beaches_volcanoes_and_semantic_grounding():
    assert "beach" in words("beaches")
    assert "volcano" in words("volcanoes")
    assert related_to_topic(BLACK_SAND, "beach", "black sand ocean shore")
    assert related_to_topic(NORTHERN, "aurora", "aurora borealis")
    assert not related_to_topic(BLACK_SAND, "person", "person typing laptop")


@pytest.mark.parametrize("metadata", [
    "aurora borealis time lapse over mountain",
    "northern lights changing colors over mountains",
    "polar aurora shining in the sky",
])
def test_metadata_matches_aurora_stock_synonyms_without_action_tag(metadata):
    subject = SceneSpec(main_character="", object="aurora", action="ambient",
                        visual_search_query="aurora borealis")
    assert SceneMatcher.validate_metadata(subject, metadata) >= .15


def test_arbitrary_sky_scenery_does_not_claim_aurora():
    subject = SceneSpec(main_character="", object="aurora", action="ambient",
                        visual_search_query="aurora borealis")
    with pytest.raises(ValidationError):
        SceneMatcher.validate_metadata(subject, "plain blue sky and puffy clouds")


def test_no_palette_is_a_real_preflight_failure_with_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_FIRST_REPORT", str(tmp_path / "media-first-plan.json"))
    class FakeVisuals:
        report = {"state": "searching", "scenes": []}
        def _save(self):
            pass
    visuals = FakeVisuals()
    with pytest.raises(RuntimeError, match="media_preflight_no_topic_palette"):
        prepare_verified_palette("Obscure xyzqvx abstract invention",
                                 object(), None, visuals=visuals)
    assert visuals.report["state"] == "failed"
    data = json.loads((tmp_path / "media-first-plan.json").read_text())
    assert data["state"] == "failed"
    assert data["attempts"] == []
    assert data["selected"] == []


@pytest.mark.parametrize("narration", [
    "Pressure plummets by 30 millibars in the storm.",
    "Wind speeds reach over 200 km/h.",
    "The ocean dumps 300 watts per square meter into the air.",
    "The temperature fell by 20%.",
    "An oak was hit 12 times in one storm.",
])
def test_unverified_accurate_sounding_statistics_are_rejected_before_tts(narration):
    script = SimpleNamespace(scenes=[SimpleNamespace(narration=narration)])
    with pytest.raises(RuntimeError, match="unverified_quantitative_claim"):
        validate_unsourced_quantities(script, HURRICANE)


def test_normal_fact_explainer_without_unverified_numbers_remains_valid():
    script = SimpleNamespace(scenes=[
        SimpleNamespace(narration="Warm ocean water supplies energy to hurricanes."),
        SimpleNamespace(narration="Air pressure is often lowest near the center."),
    ])
    validate_unsourced_quantities(script, HURRICANE)


def test_preflight_errors_no_longer_report_false_provider_rate_limits():
    message = "media_preflight_no_topic_palette: cannot find filmable subjects"
    log = "Provider health includes circuit_open and rate limit diagnostic words"
    assert classify_failure(message, log) == "topic_palette_empty"
    assert classify_failure(
        "media_preflight_insufficient_footage: 1 of 3", log) == "insufficient_verified_clips"
    assert classify_failure(
        "unverified_quantitative_claim: scene 2", log) == "unverified_factual_claim"
