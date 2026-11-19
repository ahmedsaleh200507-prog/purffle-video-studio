"""Regression for #75: 'Glow by JLo' must never become ocean science evidence.

A narrowly defined ocean bioluminescence explainer uses fixed NOAA/Smithsonian
references and exact factual narration. The general science gate stays active.
"""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from fact_checked_topics import verified_documentary_kind, ground_verified_documentary
from science_sources import discover_evidence, screen_narration
from media_first import VerifiedPalette, validate_narration_timing


TOPIC = "Why Does the Ocean Glow Blue at Night?"


def test_official_sources_not_unrelated_glow_by_jlo():
    remote = Mock()
    assert verified_documentary_kind(TOPIC) == "ocean_glow_bioluminescence"
    facts = discover_evidence(TOPIC, "en", session=remote)
    assert facts.method == "curated_editor_reviewed"
    assert len(facts.sources) >= 2
    assert all(s["tier"] == "editor_reviewed_official_dossier" for s in facts.sources)
    assert any("noaa.gov" in s["url"] for s in facts.sources)
    assert "JLo" not in json.dumps(facts.sources)
    remote.get.assert_not_called()


@pytest.mark.parametrize("topic", [
    "Why is the ocean blue in daylight?",
    "Why does the sunset glow over the ocean?",
    "Why do ocean waves form?",
    "Why does my phone glow blue at night?",
    "What is Glow by JLo?",
])
def test_other_topics_not_misclassified(topic):
    assert verified_documentary_kind(topic) != "ocean_glow_bioluminescence"


@pytest.mark.parametrize("language", ["en", "de"])
@pytest.mark.parametrize("scene_count", [3, 4])
def test_fixed_facts_fit_stock_timing_and_pass_exact_review(tmp_path, language, scene_count):
    data = ground_verified_documentary(
        {"title": "Invented science claim"}, TOPIC, language, scene_count=scene_count)
    narration = [SimpleNamespace(**s) for s in data["scenes"]]
    assert len(narration) == scene_count
    assert all(5 <= len(s.narration.split()) <= 24 for s in narration)
    palette = VerifiedPalette(TOPIC, [{}] * scene_count, [
        SimpleNamespace(duration=11) for _ in range(scene_count)], set(), [])
    validate_narration_timing(palette, SimpleNamespace(scenes=narration), language)
    report = tmp_path / "science.json"
    screen_narration(SimpleNamespace(scenes=narration),
                     discover_evidence(TOPIC, language), None, path=report)
    assert json.loads(report.read_text())["state"] == "curated_editor_reviewed"


def test_arbitrary_llm_claim_cannot_bypass_science_review(tmp_path):
    narration = [SimpleNamespace(narration="Ocean waves glow blue due to magic.")]
    report = tmp_path / "science.json"
    with pytest.raises(RuntimeError, match="science_claim_unverified"):
        screen_narration(SimpleNamespace(scenes=narration),
                         discover_evidence(TOPIC, "en"), None, path=report)
    assert json.loads(report.read_text())["state"] == "failed"
