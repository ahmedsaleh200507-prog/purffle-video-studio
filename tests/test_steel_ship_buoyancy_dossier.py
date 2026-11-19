"""Production #81 regression: never fail repeated Groq reviewers for known steel-ship physics.

Curated explanation is restricted to this narrow topic and exact
source-reviewed narration. Unrelated topics still use independent review.
"""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from fact_checked_topics import verified_documentary_kind, ground_verified_documentary
from science_sources import discover_evidence, screen_narration
from retention_storyboard import audit_storyboard
from media_first import VerifiedPalette, validate_narration_timing


TOPIC = "Why Do Steel Ships Float?"


def test_production_81_topic_routes_to_independent_physics_dossier():
    assert verified_documentary_kind(TOPIC) == "steel_ship_buoyancy"
    assert verified_documentary_kind("Warum schwimmen Schiffe aus Stahl?") == "steel_ship_buoyancy"


@pytest.mark.parametrize("other", [
    "How Do Submarines Sink?",
    "Why Do Cruise Ships Capsize?",
    "Why Does a Steel Ball Sink?",
    "Why Can an Empty Wooden Boat Float?",
    "Why Is the Ocean Saltier Than a Lake?",
])
def test_not_applied_to_unrelated_questions(other):
    assert verified_documentary_kind(other) != "steel_ship_buoyancy"


def test_two_official_educational_sources_avoid_wikipedia_misrouting():
    fake = Mock()
    bundle = discover_evidence(TOPIC, "en", session=fake)
    assert bundle.method == "curated_editor_reviewed"
    assert len(bundle.sources) == 2
    assert any("openstax.org" in s["url"] for s in bundle.sources)
    assert any("manoa.hawaii.edu" in s["url"] for s in bundle.sources)
    fake.get.assert_not_called()


@pytest.mark.parametrize("scene_count", [3, 4])
@pytest.mark.parametrize("language", ["en", "de"])
def test_verified_three_or_four_scene_story_has_fast_hook_and_real_answer(
        tmp_path, scene_count, language):
    data = ground_verified_documentary({}, TOPIC, language, scene_count=scene_count)
    assert len(data["scenes"]) == scene_count
    assert ("steel" in data["scenes"][0]["narration"].casefold()
            if language == "en" else "stahl" in data["scenes"][0]["narration"].casefold())
    narrative = " ".join(x["narration"] for x in data["scenes"]).casefold()
    assert ("water" in narrative and "buoy" in narrative
            if language == "en" else "wasser" in narrative and "auftrieb" in narrative)
    script = SimpleNamespace(scenes=[SimpleNamespace(**x) for x in data["scenes"]])
    palette = VerifiedPalette(
        TOPIC, [{} for _ in range(scene_count)],
        [SimpleNamespace(duration=10) for _ in range(scene_count)], set(), [])
    validate_narration_timing(palette, script, language)
    audit_storyboard(TOPIC, script, language)
    filename = tmp_path / "science.json"
    screen_narration(script, discover_evidence(TOPIC, language), None, path=filename)
    assert json.loads(filename.read_text())["state"] == "curated_editor_reviewed"


def test_curated_mode_does_not_accept_made_up_science(tmp_path):
    script = SimpleNamespace(scenes=[
        SimpleNamespace(narration="Steel ships float due to magnets and ocean currents."),
        SimpleNamespace(narration="Cargo does not affect displacement."),
        SimpleNamespace(narration="Water has no upward buoyant force."),
        SimpleNamespace(narration="A hollow steel hull is irrelevant to whether it floats."),
    ])
    filename = tmp_path / "science-report.json"
    with pytest.raises(RuntimeError, match="science_claim_unverified"):
        screen_narration(
            script, discover_evidence(TOPIC, "en"), None, path=filename)
    assert json.loads(filename.read_text())["state"] == "failed"


def test_known_topic_does_not_require_groq_reviewer():
    # Failed #81 repeatedly on model JSON ValueError + Groq TPM 429.
    data = ground_verified_documentary({}, TOPIC, "en", scene_count=4)
    script = SimpleNamespace(scenes=[SimpleNamespace(**x) for x in data["scenes"]])
    reviewer = Mock()
    screen_narration(script, discover_evidence(TOPIC, "en"), reviewer)
    reviewer.complete_json.assert_not_called()
