"""Regression of the exact user ocean-waves video failing #3 after four real clips.

Do not disable the science gate globally: use a narrow NOAA-backed,
fixed narration dossier only for ordinary wind-driven ocean surface waves.
"""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from fact_checked_topics import verified_documentary_kind, ground_verified_documentary
from science_sources import discover_evidence, screen_narration
from media_first import VerifiedPalette, validate_narration_timing

TOPIC = "Why Do Ocean Waves Form?"


def test_ocean_waves_have_official_noaa_dossier_and_no_wikipedia_guessing():
    offline = Mock()
    assert verified_documentary_kind(TOPIC) == "ocean_waves"
    proof = discover_evidence(TOPIC, "en", session=offline)
    assert proof.method == "curated_editor_reviewed"
    assert len(proof.sources) >= 2
    assert all("noaa.gov" in x["url"] for x in proof.sources)
    offline.get.assert_not_called()


@pytest.mark.parametrize("topic", [
    "How do tsunami waves form?",
    "Why are rogue ocean waves so big?",
    "How do earthquakes cause waves?",
    "Why do tides form in the ocean?",
    "How do swells form?",
    "What makes ocean currents move?",
])
def test_ocean_dossier_does_not_skip_independent_review_for_unrelated_science(topic):
    assert verified_documentary_kind(topic) != "ocean_waves"


@pytest.mark.parametrize("language", ["en", "de"])
@pytest.mark.parametrize("scene_count", [3, 4])
def test_official_story_is_exact_and_fits_real_stock_duration(tmp_path, language, scene_count):
    original = {"title": "An imaginary fact", "scenes": [
        {"narration": "Lightning created all ocean waves yesterday."}]}
    data = ground_verified_documentary(original, TOPIC, language, scene_count)
    scenes = [SimpleNamespace(**item) for item in data["scenes"]]
    assert len(scenes) == scene_count
    assert not any("Lightning" in x.narration for x in scenes)
    assert all(5 <= len(x.narration.split()) <= 24 for x in scenes)
    prepared = SimpleNamespace(scenes=scenes)
    palette = VerifiedPalette(TOPIC, [{}] * scene_count, [
        SimpleNamespace(duration=11.0) for _ in range(scene_count)], set(), [])
    validate_narration_timing(palette, prepared, language)
    science = tmp_path / f"{language}-{scene_count}.json"
    screen_narration(prepared, discover_evidence(TOPIC, language),
                     None, path=science)
    result = json.loads(science.read_text())
    assert result["state"] == "curated_editor_reviewed"
    assert len(result["sources"]) >= 2


def test_ocean_dossier_never_launders_arbitrary_llm_facts(tmp_path):
    script = SimpleNamespace(scenes=[
        SimpleNamespace(narration="A sea wave is formed by volcanoes.") for _ in range(4)])
    output = tmp_path / "science.json"
    with pytest.raises(RuntimeError, match="science_claim_unverified"):
        screen_narration(script, discover_evidence(TOPIC, "en"),
                         None, path=output)
    assert json.loads(output.read_text())["state"] == "failed"


def test_dossier_is_applied_to_exact_topic_in_real_runtime():
    root = Path(__file__).parents[1]
    runtime = (root / "scripts" / "studio_runtime.py").read_text()
    assert "ground_verified_documentary" in runtime
    assert "align_script_to_palette" in runtime
    assert "screen_narration(" in (root / "scripts" / "render_job.py").read_text()
