"""Reliable lava-meets-ocean pilot for a retention-oriented real-footage Short.

USGS source anchors, exact narration and clip duration stay enforced.
"""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from attention_hook import compact_hook_lines
from fact_checked_topics import verified_documentary_kind, ground_verified_documentary
from science_sources import discover_evidence, screen_narration
from media_first import VerifiedPalette, validate_narration_timing


TOPIC = "What Happens When Lava Hits the Ocean?"


def test_lava_ocean_has_verified_topic_and_usgs_official_sources():
    client = Mock()
    assert verified_documentary_kind(TOPIC) == "lava_ocean_entry"
    assert compact_hook_lines(TOPIC) == ["LAVA MEETS OCEAN", "WHAT HAPPENS?"]
    bundle = discover_evidence(TOPIC, "en", session=client)
    assert bundle.method == "curated_editor_reviewed"
    assert len(bundle.sources) >= 2
    assert all(x["url"].startswith("https://www.usgs.gov/") for x in bundle.sources)
    client.get.assert_not_called()


@pytest.mark.parametrize("topic", [
    "Why does lava float in a crater?",
    "How do volcanoes create islands?",
    "How does the ocean glow blue at night?",
    "Lava lamps in an aquarium",
])
def test_lava_template_does_not_override_unrelated_science(topic):
    assert verified_documentary_kind(topic) != "lava_ocean_entry"


@pytest.mark.parametrize("scene_count", [3, 4])
@pytest.mark.parametrize("language", ["en", "de"])
def test_three_and_four_scene_video_is_concise_true_and_source_checked(tmp_path, scene_count, language):
    data = ground_verified_documentary(
        {"title": "invented claims", "scenes": [{"narration": "scientist invented a fake number"}]},
        TOPIC, language, scene_count=scene_count)
    script = SimpleNamespace(scenes=[SimpleNamespace(**sc) for sc in data["scenes"]])
    assert len(script.scenes) == scene_count
    assert all(5 <= len(sc.narration.split()) <= 21 for sc in script.scenes)
    palette = VerifiedPalette(TOPIC, [{} for _ in range(scene_count)],
        [SimpleNamespace(duration=10) for _ in range(scene_count)], set(), [])
    validate_narration_timing(palette, script, language)
    report = tmp_path / "science.json"
    screen_narration(script, discover_evidence(TOPIC, language),
                     None, path=report)
    data = json.loads(report.read_text())
    assert data["state"] == "curated_editor_reviewed"
    assert all(x["url"].startswith("https://www.usgs.gov/") for x in data["sources"])


def test_no_arbitrary_llm_lava_claims_accepted(tmp_path):
    claim = SimpleNamespace(scenes=[
        SimpleNamespace(narration="Lava entering the ocean makes the sea freeze instantly.")])
    path = tmp_path / "science.json"
    with pytest.raises(RuntimeError, match="science_claim_unverified"):
        screen_narration(claim, discover_evidence(TOPIC, "en"), None, path=path)
    assert json.loads(path.read_text())["state"] == "failed"


def test_strict_lava_footage_does_not_accept_generic_ocean_or_surfers():
    from topic_footage import (
        deterministic_stock_shots, is_lava_ocean_topic,
        lava_subject_in_metadata)
    from media_first import _grounded_candidates

    assert is_lava_ocean_topic(TOPIC)
    assert not is_lava_ocean_topic("Why Does the Ocean Glow Blue?")
    assert not is_lava_ocean_topic("How Do Volcanoes Create Islands?")
    proposed = deterministic_stock_shots(TOPIC)
    assert len(proposed) >= 4
    assert proposed[0]["visual_search_query"] == "lava flowing into ocean"
    assert all(lava_subject_in_metadata(p["visual_search_query"]) for p in proposed)
    assert all(lava_subject_in_metadata(p["visual_search_query"]) for p in
               _grounded_candidates(TOPIC, llm=None))
    assert lava_subject_in_metadata("Kilauea volcanic lava pours into seawater")
    assert lava_subject_in_metadata("Lava ocean entry with steam")
    assert not lava_subject_in_metadata("Rugged ocean waves coastline")
    assert not lava_subject_in_metadata("Man swimming near ocean ridge")
    assert not lava_subject_in_metadata("Lava lamp glowing on a desk")


def test_narrator_error_outweighs_secondary_provider_quota():
    from batch import classify_failure
    assert classify_failure(
        "reference_voice_failed: only approved private English narrator can be used",
        "Coverr free API per-job budget reached; http_429 provider") == (
            "approved_english_voice_validation")



def test_first_scene_uses_visually_strong_verified_lava_clip():
    from media_first import prioritize_lava_opening
    # Simulate visually reviewed scene #4 glowing, while clip #1 is palms.
    clips = [SimpleNamespace(path=f"shot-{n}") for n in range(4)]
    plans = [f"plan-{n}" for n in range(4)]
    reports = [{"id": n} for n in range(4)]
    scores = {"shot-0": 0.0, "shot-1": 0.0,
              "shot-2": 0.002, "shot-3": 0.075}
    result = prioritize_lava_opening(
        TOPIC, clips, plans, reports, glow_score=lambda path: scores[path])
    assert result is True
    assert clips[0].path == "shot-3"
    assert plans[0] == "plan-3"
    assert reports[0]["id"] == 3
    assert [v.path for v in clips[1:]] == ["shot-0", "shot-1", "shot-2"]


def test_opening_impact_never_reorders_unrelated_videos():
    from media_first import prioritize_lava_opening
    clips = [SimpleNamespace(path="normal"), SimpleNamespace(path="bright")]
    plans = ["first", "second"]
    reports = [{"index": 1}, {"index": 2}]
    assert prioritize_lava_opening(
        "Why Do Ocean Waves Form?", clips, plans, reports,
        glow_score=lambda path: 1 if path == "bright" else 0) is False
    assert [v.path for v in clips] == ["normal", "bright"]


def test_weak_lava_frames_preserve_existing_clip_order():
    from media_first import prioritize_lava_opening
    clips = [SimpleNamespace(path="a"), SimpleNamespace(path="b")]
    plans, reports = ["a", "b"], [{"i": 1}, {"i": 2}]
    assert prioritize_lava_opening(
        TOPIC, clips, plans, reports,
        glow_score=lambda path: .004 if path == "b" else .003) is False
    assert [c.path for c in clips] == ["a", "b"]
