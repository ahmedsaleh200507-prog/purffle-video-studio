"""Offline regressions for the 10-video failure ZIP from 19 November 2026.

The assertions check causal guards; they are NOT claims that live stock, voice,
science sources or MP4 rendering succeeded.
"""
import json
from types import SimpleNamespace

import pytest

from media_first import _grounded_candidates
from media_validation import SceneMatcher, SceneSpec, ValidationError
from science_fact_guard import validate_unsourced_quantities
from science_sources import Evidence, _search_text, screen_narration


@pytest.mark.parametrize("topic,subject", [
    ("Why Do Icebergs Suddenly Break Apart?", "iceberg"),
    ("What Happens When a Meteor Enters Earth's Atmosphere?", "meteor"),
    ("Why Do Sea Turtles Sleep Underwater?", "turtle"),
])
def test_failed_media_topics_now_generate_topic_grounded_candidates(topic, subject):
    plans = _grounded_candidates(topic, llm=None)
    assert len(plans) >= 4
    assert plans[0]["object"] == subject
    assert all(plan["action"] == "ambient" for plan in plans)
    assert all(subject in plan["visual_search_query"] for plan in plans[:2])


def test_real_turtle_documentary_metadata_is_not_rejected_for_ambient_action():
    spec = SceneSpec(object="turtle", action="ambient",
                     visual_search_query="sea turtle underwater")
    assert SceneMatcher.validate_metadata(
        spec, "Sea turtle swimming underwater in the ocean") >= .20
    with pytest.raises(ValidationError):
        SceneMatcher.validate_metadata(
            spec, "Underwater tropical reef fish")


def test_searched_mechanism_not_unrelated_page_title():
    assert "buoyancy" in _search_text("Why Do Steel Ships Float?")
    assert "ventilation" in _search_text("Why Do Some Sharks Have to Keep Swimming?")
    assert "waterfall" in _search_text("Why Can a Waterfall Freeze Without Stopping?")


def _bundle():
    fact = ("Underwater volcanic eruptions can accumulate layers of lava "
            "and rock. Volcanoes may grow into islands.")
    return Evidence("Why do volcanoes form islands?", ({
        "id": "wiki-1", "title": "Volcanic island",
        "url": "https://en.wikipedia.org/wiki/Volcanic_island",
        "tier": "community_edited_reference",
        "excerpt": fact,
    },), "model_screened_reference")


def _scene():
    return SimpleNamespace(scenes=[
        SimpleNamespace(narration="Underwater volcanic eruptions can build up rock.")
    ])


def test_malformed_science_review_retries_same_script_and_still_requires_quote(
        tmp_path, monkeypatch):
    monkeypatch.setattr("science_sources.time.sleep", lambda seconds: None)
    class FlakyModel:
        calls = 0

        def complete_json(self, system, prompt, schema):
            self.calls += 1
            if self.calls < 3:
                raise ValueError("Malformed model JSON")
            return {"checks": [{
                "scene": 1, "supported": True, "source_id": "wiki-1",
                "quote": "Underwater volcanic eruptions can accumulate layers of lava and rock.",
                "reason": "Literal independent source passage",
            }]}

    model = FlakyModel()
    path = tmp_path / "science-report.json"
    screen_narration(_scene(), _bundle(), model, path=path)
    assert model.calls == 3
    assert json.loads(path.read_text())["state"] == "model_screened_reference"


def test_reviewer_malformed_all_attempts_still_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr("science_sources.time.sleep", lambda seconds: None)
    model = SimpleNamespace(complete_json=lambda *args: {"checks": []})
    path = tmp_path / "science-report.json"
    with pytest.raises(RuntimeError, match="science_review_unavailable"):
        screen_narration(_scene(), _bundle(), model, path=path)
    assert json.loads(path.read_text())["state"] == "failed"


def test_unverified_measurement_still_cannot_get_to_tts():
    script = SimpleNamespace(scenes=[SimpleNamespace(narration=
        "The volcanic plume rises 20,000 feet into the sky.")])
    with pytest.raises(RuntimeError, match="unverified_quantitative_claim"):
        validate_unsourced_quantities(script, "What Makes a Volcano Suddenly Erupt?")


def test_malformed_science_reviewer_is_not_misreported_as_bad_science():
    from batch import classify_failure
    assert classify_failure("science_review_unavailable: invalid_model_json") == (
        "science_reviewer_unavailable")
    assert classify_failure("science_claim_unverified: unsupported narration scene") == (
        "science_claim_unsupported")
