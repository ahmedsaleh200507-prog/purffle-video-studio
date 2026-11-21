"""#84 regressions: an attractive sky-only clip must NOT replace the main subject.

No provider access, model downloads, AI services or private narrator required.
This tests filtering and ranking contracts, not calibrated object detection.
"""
from types import SimpleNamespace

import pytest

from topic_footage import (
    is_sudden_volcano_eruption_topic,
    explosive_volcano_evidence_in_metadata,
    explosive_volcano_last_shot_prompts,
    is_glowing_ocean_topic, bioluminescence_visible_in_metadata,
    contradicts_floating_ship, deterministic_stock_shots,
    is_steel_ship_floating_topic, opening_subject_prompts,
)
from opening_impact import _semantic_subject_screen, prioritize_opening
from attention_hook import compact_hook_lines
from media_first import _grounded_candidates


SHIP = "Why Do Steel Ships Float?"


def test_root_cause_84_rejects_abandoned_ship_not_only_in_hook():
    assert is_steel_ship_floating_topic(SHIP)
    assert contradicts_floating_ship(SHIP, (
        "https://coverr.co/videos/an-abandoned-ship-in-tierra-del-fuego"))
    assert contradicts_floating_ship(SHIP, "a rusty shipwreck on rocky shoreline")
    assert contradicts_floating_ship(SHIP, "a vessel inside a dry-dock")
    assert not contradicts_floating_ship(SHIP, "cargo ship sailing at sea")
    assert not contradicts_floating_ship("Why Do Shipwrecks Happen?",
                                        "an abandoned shipwreck")


def test_root_cause_84_prioritizes_floating_cargo_vessel_queries():
    queries = [p["visual_search_query"] for p in _grounded_candidates(SHIP)]
    assert queries[:3] == [
        "cargo ship sailing at sea",
        "container ship floating water",
        "cargo freighter side view waterline",
    ]
    assert "ship outdoors" not in queries[:4]
    assert all("ship" in q or "freighter" in q for q in queries[:4])


def test_first_second_semantic_gate_rejects_empty_sky_ocean_even_with_motion():
    spec = opening_subject_prompts(SHIP)
    assert spec["subject"] == "floating_cargo_ship"
    positive = _semantic_subject_screen(
        [object(), object()], spec,
        scorer=lambda frames, captions: [
            [.32, .22, .18], [.34, .21, .18]])
    assert positive["verified"]
    assert positive["subject_minus_scenery"] >= .08
    empty_ocean = _semantic_subject_screen(
        [object(), object()], spec,
        scorer=lambda frames, captions: [
            [.22, .35, .16], [.24, .37, .18]])
    assert not empty_ocean["verified"]
    assert empty_ocean["reason"] == "opening_subject_not_prominent_enough"


def test_semantic_gate_fails_when_frame_or_model_result_missing():
    spec = opening_subject_prompts(SHIP)
    assert not _semantic_subject_screen([], spec)["verified"]
    with pytest.raises(RuntimeError, match="opening_subject_unverified"):
        _semantic_subject_screen([object(), object()], spec,
                                 scorer=lambda *_: [[.3,.2]])


def test_opening_chooses_visible_subject_over_higher_motion_scenery():
    items = [
        SimpleNamespace(path=f"clip-{i}", extra={"match": {"crop_focus_x": .7}})
        for i in range(3)]
    plans = [{"visual_search_query": q} for q in
             ("ship footage", "cargo ship sailing", "container ship harbor")]
    reports = [
        {"match": {"visual_score": .3},
         "license": {"source_page": f"https://example.com/ships-{i}"}}
        for i in range(3)]
    def pixels(path):
        return {"verified": True,
                "impact": {"clip-0": 96, "clip-1": 70, "clip-2": 49}[path],
                "hot_lava_ratio": 0.0}
    called = []
    def semantic(path, specification, focus):
        called.append((path, specification["subject"], focus))
        okay = path != "clip-0"
        return {"verified": okay, "subject_minus_scenery": .05 if okay else -.1}
    selected = prioritize_opening(
        SHIP, items, plans, reports,
        analyzer=pixels, semantic_analyzer=semantic)
    assert selected["original_scene"] == 2
    assert items[0].path == "clip-1"
    assert reports[0]["license"]["source_page"].endswith("ships-1")
    assert selected["clip_scores"][0]["verified"] is False
    assert selected["crop_focus_aware"]
    assert called == [(f"clip-{i}", "floating_cargo_ship", .7) for i in range(3)]


def test_no_semantically_related_hook_fails_before_voice_production():
    items = [SimpleNamespace(path=f"clip-{i}") for i in range(3)]
    plans = [{"visual_search_query": "ship outdoors"} for _ in items]
    reports = [{"match": {"visual_score": .5}} for _ in items]
    with pytest.raises(RuntimeError, match="opening_quality_unverified"):
        prioritize_opening(
            SHIP, items, plans, reports,
            analyzer=lambda _: {"verified": True, "impact": 95, "hot_lava_ratio": 0.0},
            semantic_analyzer=lambda *_: {
                "verified": False, "subject_minus_scenery": -.04})
    assert [x.path for x in items] == ["clip-0", "clip-1", "clip-2"]


@pytest.mark.parametrize("topic", [
    SHIP,
    "Why Can Giant Waves Overwhelm Ships?",
    "Why Do Icebergs Suddenly Break Apart?",
    "Why Do Sea Turtles Sleep Underwater?",
    "What Makes a Volcano Suddenly Erupt?",
    "Why Do Whales Jump Out of the Ocean?",
    "Why Can a Waterfall Freeze?",
    "Why Do Some Sharks Have to Keep Swimming?",
    "What Happens When a Meteor Enters Earth's Atmosphere?",
    "Why Does the Ocean Glow Blue at Night?",
    "Why Do Northern Lights Dance Across the Sky?",
])
def test_more_tangible_shorts_have_visible_first_frame_anchor(topic):
    assert opening_subject_prompts(topic) is not None


@pytest.mark.parametrize("topic", [
    SHIP,
    "Why Can Giant Waves Overwhelm Ships?",
    "Why Do Icebergs Suddenly Break Apart?",
    "Why Do Sea Turtles Sleep Underwater?",
    "What Makes a Volcano Suddenly Erupt?",
    "Why Do Whales Jump Out of the Ocean?",
    "Why Do Some Sharks Have to Keep Swimming?",
])
def test_short_hooks_use_2_lines_and_at_most_seven_words(topic):
    lines = compact_hook_lines(topic)
    assert 1 <= len(lines) <= 2
    assert sum(len(line.split()) for line in lines) <= 7


def test_existing_other_topics_keep_original_narration_hook():
    assert not is_steel_ship_floating_topic("Why Do Submarines Sink?")
    assert opening_subject_prompts("An abstract hypothetical idea") is None
    assert " ".join(compact_hook_lines("Why Is the Sky Blue?")) == "WHY IS THE SKY BLUE?"


def test_every_production_clip_is_gated_after_license_quality_and_clip_match():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] /
              "scripts" / "studio_runtime.py").read_text()
    assert source.index("match = self.matcher.match(") < source.index(
        "subject_result = _semantic_subject_screen(") < source.index(
        "self._remember(item, url_key, digest)")


def test_production_85_blue_ocean_requires_bioluminescence_not_empty_sea():
    topic = "Why Does the Ocean Glow Blue at Night?"
    assert is_glowing_ocean_topic(topic)
    assert not is_glowing_ocean_topic("Why Is the Ocean Blue During the Day?")
    assert not bioluminescence_visible_in_metadata(
        "underwater sea blue ocean waves horizon sky")
    assert bioluminescence_visible_in_metadata(
        "bioluminescent glowing plankton moving sea at night")
    plans = _grounded_candidates(topic)
    assert plans
    assert all(bioluminescence_visible_in_metadata(
        x["visual_search_query"]) for x in plans)
    assert not any("underwater sea" in x["visual_search_query"]
                   for x in plans)
    from pathlib import Path
    runtime = (Path(__file__).resolve().parents[1] /
               "scripts" / "studio_runtime.py").read_text()
    assert "offtopic_bioluminescence" in runtime


def test_production_86_dramatic_final_cannot_use_calm_misty_volcano():
    topic = "What Makes a Volcano Suddenly Erupt?"
    assert is_sudden_volcano_eruption_topic(topic)
    assert not is_sudden_volcano_eruption_topic(
        "Why Do Volcanoes Create Islands?")
    assert not explosive_volcano_evidence_in_metadata(
        "volcano smoking crater mountains fog peaceful landscape")
    assert not explosive_volcano_evidence_in_metadata(
        "https://pixabay.com/videos/volcano-mountain-cloud-fog")
    assert explosive_volcano_evidence_in_metadata(
        "active volcano with a huge ash eruption plume")
    assert explosive_volcano_evidence_in_metadata(
        "volcano exploding lava fountain at night")
    prompt = explosive_volcano_last_shot_prompts()
    assert prompt["subject"] == "active_volcanic_eruption"
    bad = _semantic_subject_screen(
        [object(), object()], prompt,
        scorer=lambda frames, captions: [
            [.21, .35, .34], [.23, .36, .32]])
    assert not bad["verified"]
    good = _semantic_subject_screen(
        [object(), object()], prompt,
        scorer=lambda frames, captions: [
            [.34, .19, .18], [.32, .20, .16]])
    assert good["verified"]
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    runtime = (root / "scripts" / "studio_runtime.py").read_text()
    stock = (root / "scripts" / "topic_footage.py").read_text()
    assert "volcano_final_action_mismatch" in runtime
    assert "explosive_volcano_last_shot_prompts" in runtime
    assert '("volcano", "volcano smoking crater")' not in stock


def test_production_86_narration_matches_lava_opening_not_invisible_ash_blast():
    from fact_checked_topics import ground_verified_documentary
    topic = "What Makes a Volcano Suddenly Erupt?"
    for lang in ("en", "de"):
        for scene_count in (3, 4):
            scenes = ground_verified_documentary(
                {}, topic, lang, scene_count=scene_count)["scenes"]
            first = scenes[0]["narration"].casefold()
            assert ("lava" in first)
            assert ("volcano" in first or "vulkan" in first)
            assert len(first.split()) >= 12
