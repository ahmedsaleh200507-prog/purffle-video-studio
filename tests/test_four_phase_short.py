"""Real video Shorts must use a concrete hook, curiosity, development and payoff.

No claim of automatic viral views or guaranteed YouTube monetization.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from retention_storyboard import (
    PHASES, audit_storyboard, editorial_phase_windows,
    save_storyboard_report, storyboard_writer_brief,
)


def script(*sentences):
    return SimpleNamespace(scenes=[
        SimpleNamespace(narration=sentence) for sentence in sentences
    ])


LAVA = script(
    "Glowing lava enters the ocean and sends thick steam above the coast.",
    "Seawater flashes into steam while the surface cools and breaks apart.",
    "The newly formed rocks can collapse, causing dangerous steam explosions along the coast.",
)

OCEAN = script(
    "Some ocean waves glow bright blue because of tiny marine organisms.",
    "Certain plankton flash when the water begins moving around them.",
    "The glow is called bioluminescence, and comes from chemical reactions inside living cells.",
)


def test_four_phase_times_are_the_exact_requested_framework():
    assert [(a,b,c) for a,b,c,_ in PHASES] == [
        ("hook",0,2), ("curiosity",2,8),
        ("development",8,22), ("payoff",22,30)]
    windows = editorial_phase_windows()
    assert windows[0]["start_seconds"] == 0
    assert windows[-1]["end_seconds"] == 30
    shortened = editorial_phase_windows(22.5)
    assert shortened[1]["start_seconds"] == 1.5
    assert shortened[-1]["end_seconds"] == 22.5
    assert shortened[2]["end_seconds"] == 16.5


def test_brief_guides_all_verifiable_three_and_four_scene_shorts():
    for scenes in (3,4):
        words = storyboard_writer_brief(scenes)
        assert "0–2s HOOK" in words
        assert "2–8s CURIOSITY" in words
        assert "8–22s DEVELOPMENT" in words
        assert "22–30s PAYOFF" in words
        assert "NO huge title overlay" in words
        assert "UNIQUE source-grounded explanation" in words
        assert f"{scenes} verified shots" in words
    assert "1 verified shots" in storyboard_writer_brief(1)
    with pytest.raises(ValueError):
        storyboard_writer_brief(0)


@pytest.mark.parametrize("story,topic", [
    (LAVA, "What Happens When Lava Hits the Ocean?"),
    (OCEAN, "Why Does the Ocean Glow Blue at Night?"),
])
def test_science_explanations_pass_with_no_filler(story, topic):
    result = audit_storyboard(topic, story)
    assert result["state"] == "editorial_screen_passed"
    assert result["scene_count"] == 3
    assert result["last_scene_word_count"] >= 7
    assert result["template_target_seconds"] == 30
    assert "not an audience-retention guarantee" in result["scope"]


@pytest.mark.parametrize("first", [
    "Welcome to our channel, where we explore incredible science.",
    "In this video, we will discover something absolutely amazing.",
    "Did you know there are secrets about the ocean?",
])
def test_reject_generic_greetings_and_subscribe_preambles(first):
    with pytest.raises(RuntimeError, match="generic intro"):
        audit_storyboard("Why Do Ocean Waves Form?", script(
            first, "Water moves because wind transfers energy into its surface.",
            "Shallow water makes waves steepen and eventually break near shore."))


def test_reject_repeated_scenes_that_look_mass_produced():
    repeated = "Seawater flashes into steam when glowing lava pours into it."
    with pytest.raises(RuntimeError, match="repeated scene"):
        audit_storyboard("What Happens When Lava Hits the Ocean?", script(
            "Glowing lava enters the ocean and sends steam into the sky.",
            repeated, repeated))


def test_reject_no_answer_and_cta():
    with pytest.raises(RuntimeError, match="CTA"):
        audit_storyboard("Why does the sea glow blue?", script(
            "Certain plankton glow when water moves around their bodies.",
            "Bioluminescence comes from a chemical reaction inside tiny marine organisms.",
            "Like and subscribe to discover even more amazing science videos."))
    with pytest.raises(RuntimeError, match="no substantive final"):
        audit_storyboard("Why does the sea glow blue?", script(
            "Certain plankton glow when water moves around their bodies.",
            "Bioluminescence comes from a chemical reaction inside tiny marine organisms.",
            "It is very amazing indeed today."))


def test_copying_topic_word_for_word_is_not_a_real_hook():
    with pytest.raises(RuntimeError, match="full title repeated"):
        audit_storyboard("Why Do Some Ocean Waves Glow Blue at Night?",
            script("Why Do Some Ocean Waves Glow Blue at Night? It's an interesting mystery.",
                   "Tiny marine organisms may glow when water moves around them.",
                   "Bioluminescence is a chemical process inside these living organisms."))


def test_german_script_keeps_language_and_real_payoff():
    german = script(
        "Glühende Lava fließt ins Meer und lässt große Dampfwolken aufsteigen.",
        "Beim Abkühlen zerbricht Lava in Gesteinsstücke. Die Wolken können saure Gase enthalten.",
        "Manchmal stürzt frisch entstandene Lavaküste ein und löst gefährliche Dampfexplosionen aus.",
    )
    report = audit_storyboard("Was passiert, wenn Lava ins Meer fließt?", german, "de")
    assert report["language"] == "de"


def test_report_has_real_output_duration_not_fake_youtube_analytics(tmp_path):
    report = tmp_path / "retention-report.json"
    original = audit_storyboard("Why does the ocean glow blue?", OCEAN)
    saved = save_storyboard_report(report, original)
    assert saved.is_file()
    assert "actual_video_duration_seconds" not in json.loads(report.read_text())
    save_storyboard_report(report, original, duration_seconds=22.1)
    data = json.loads(report.read_text())
    assert data["actual_video_duration_seconds"] == 22.1
    assert data["editorial_phase_targets_scaled_to_video"][-1]["end_seconds"] == 22.1
    assert "YouTube Studio" in data["warning"]


def test_pipeline_enforces_editorial_audit_before_narrator_and_saves_zip_report():
    root = Path(__file__).resolve().parents[1]
    renderer = (root / "scripts" / "render_job.py").read_text()
    batch = (root / "scripts" / "batch.py").read_text()
    palette = (root / "scripts" / "media_first.py").read_text()
    assert "target_seconds=30" in renderer
    assert renderer.index("audit_storyboard(") < renderer.index("studio.produce(")
    assert renderer.index("screen_narration(") < renderer.index("studio.produce(")
    assert "RETENTION_REPORT=" in batch
    assert "retention_report=" in renderer
    assert "storyboard_writer_brief(" in palette
    assert "hook_overlay=False" in renderer
    assert "PURFFLE_STRICT" in batch
