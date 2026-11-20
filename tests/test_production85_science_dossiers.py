"""Production #85 six source-backed science questions: avoid unsafe Groq reviewers.

These dossiers have narrowly whitelisted topics. Every exact EN/DE sentence
must match the source-reviewed script, not an arbitrary model-generated claim.
"""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from fact_checked_topics import ground_verified_documentary, verified_documentary_kind
from science_sources import discover_evidence, screen_narration
from media_first import VerifiedPalette, validate_narration_timing
from retention_storyboard import audit_storyboard


TOPICS = [
    ("What Makes a Volcano Suddenly Erupt?", "volcano_eruption", "volcano"),
    ("Why Do Icebergs Suddenly Break Apart?", "iceberg_breakup", "iceberg"),
    ("Why Do Whales Jump Out of the Ocean?", "whale_breaching", "whale"),
    ("Why Do Some Sharks Have to Keep Swimming?", "shark_ventilation", "shark"),
    ("Why Do Sea Turtles Sleep Underwater?", "sea_turtle_rest", "turtle"),
    ("Why Can a Waterfall Freeze Without Stopping?", "waterfall_freezing", "waterfall"),
]


@pytest.mark.parametrize("topic,kind,object_name", TOPICS)
@pytest.mark.parametrize("scene_count", [3, 4])
@pytest.mark.parametrize("language", ["en", "de"])
def test_curated_science_has_sources_and_exact_validated_3_or_4_scene_script(
        tmp_path, topic, kind, object_name, scene_count, language):
    assert verified_documentary_kind(topic) == kind
    client = Mock()
    evidence = discover_evidence(topic, language, session=client)
    assert evidence.method == "curated_editor_reviewed"
    assert len(evidence.sources) == 2
    assert all(str(x["url"]).startswith("https://") for x in evidence.sources)
    client.get.assert_not_called()
    ground = ground_verified_documentary(
        {}, topic, language, scene_count=scene_count)
    assert len(ground["scenes"]) == scene_count
    assert all(x["object"] == object_name for x in ground["scenes"])
    script = SimpleNamespace(scenes=[
        SimpleNamespace(**x) for x in ground["scenes"]])
    palette = VerifiedPalette(
        topic, [{} for _ in range(scene_count)],
        [SimpleNamespace(duration=10) for _ in range(scene_count)],
        set(), [])
    validate_narration_timing(palette, script, language)
    audit_storyboard(topic, script, language)
    no_llm = Mock()
    filename = tmp_path / f"{kind}-{scene_count}-{language}.json"
    screen_narration(script, evidence, no_llm, path=filename)
    assert json.loads(filename.read_text())["state"] == "curated_editor_reviewed"
    no_llm.complete_json.assert_not_called()


@pytest.mark.parametrize("other", [
    "Why Do Volcanoes Create Islands?",
    "Why Do Ships Sink?",
    "Why Do Sharks Attack Surfers?",
    "Where Do Sea Turtles Lay Eggs?",
    "Why Do Whales Beach Themselves?",
    "Why Are Icebergs White?",
    "Why Do Waterfalls Form?",
])
def test_narrow_dossiers_cannot_bypass_review_for_unrelated_questions(other):
    assert verified_documentary_kind(other) not in {
        "volcano_eruption", "iceberg_breakup", "whale_breaching",
        "shark_ventilation", "sea_turtle_rest", "waterfall_freezing"}


@pytest.mark.parametrize("topic,kind,object_name", TOPICS)
def test_false_science_cannot_use_editor_reviewed_route(
        tmp_path, topic, kind, object_name):
    evidence = discover_evidence(topic)
    scenes = [SimpleNamespace(narration="The object flies through space using magic.")]
    script = SimpleNamespace(scenes=scenes)
    with pytest.raises(RuntimeError, match="science_claim_unverified"):
        screen_narration(script, evidence, Mock(),
                         path=tmp_path / "invalid-science.json")
