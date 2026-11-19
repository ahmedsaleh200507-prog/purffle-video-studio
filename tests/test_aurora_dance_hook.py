"""Regression from produced aurora #79: the dance question must be answered.

This tests the actual 18.2s source review failure without fabricating views.
"""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from fact_checked_topics import verified_documentary_kind, ground_verified_documentary
from science_sources import discover_evidence, screen_narration
from retention_storyboard import audit_storyboard
from media_first import VerifiedPalette, validate_narration_timing

TOPIC = "Why Do Northern Lights Dance Across the Sky?"


def test_question_routes_to_dance_not_generic_glow():
    assert verified_documentary_kind(TOPIC) == "northern_lights_dance"
    assert verified_documentary_kind("Why Do Northern Lights Glow?") == "northern_lights_glow"
    assert verified_documentary_kind("How Do Ocean Waves Form?") == "ocean_waves"
    assert verified_documentary_kind("Warum tanzen Nordlichter am Himmel?") == "northern_lights_dance"


def test_official_noaa_nasa_sources_are_pinned_not_arbitrary_search():
    fake = Mock()
    bundle = discover_evidence(TOPIC, "en", session=fake)
    assert bundle.method == "curated_editor_reviewed"
    assert any("spaceweather.gov" in row["url"] for row in bundle.sources)
    assert any("nasa.gov" in row["url"] for row in bundle.sources)
    fake.get.assert_not_called()


@pytest.mark.parametrize("scene_count", [3, 4])
@pytest.mark.parametrize("language", ["en", "de"])
def test_approved_aurora_scripts_open_with_dance_and_explain_it(
        tmp_path, scene_count, language):
    output = ground_verified_documentary({}, TOPIC, language, scene_count=scene_count)
    assert len(output["scenes"]) == scene_count
    joined = " ".join(x["narration"] for x in output["scenes"]).casefold()
    assert "glow" not in output["title"][language].casefold()
    assert "dance" in output["title"]["en"].casefold()
    assert ("magnetic" in joined and ("sway" in joined or "twist" in joined)
            if language == "en" else ("magnet" in joined and
               ("tanzen" in joined or "bewegen" in joined)))
    assert ("sky seems to dance" in output["scenes"][0]["narration"].casefold()
            if language == "en" else "tanzen" in output["scenes"][0]["narration"].casefold())
    script = SimpleNamespace(scenes=[SimpleNamespace(**s) for s in output["scenes"]])
    palette = VerifiedPalette(TOPIC, [{} for _ in range(scene_count)],
                              [SimpleNamespace(duration=10) for _ in range(scene_count)],
                              set(), [])
    validate_narration_timing(palette, script, language)
    audit_storyboard(TOPIC, script, language)
    report = tmp_path / "science.json"
    screen_narration(script, discover_evidence(TOPIC, language), None, path=report)
    assert json.loads(report.read_text())["state"] == "curated_editor_reviewed"


def test_old_18_second_glow_only_script_is_rejected_for_dancing_topic(tmp_path):
    # Actual #79 script opened with a definition, and never explained why
    # the light curtains MOVE. It must not pass scientific screening again.
    old = [
        "Northern lights are colorful displays high in Earth's atmosphere.",
        "Energetic electrons follow Earth's magnetic field toward polar regions.",
        "They collide with oxygen and nitrogen, causing these gases to release light.",
        "That glowing light forms colorful curtains across polar night skies.",
    ]
    script = SimpleNamespace(scenes=[SimpleNamespace(narration=x) for x in old])
    path = tmp_path / "science-report.json"
    with pytest.raises(RuntimeError, match="science_claim_unverified"):
        screen_narration(script, discover_evidence(TOPIC, "en"), None, path=path)
    assert json.loads(path.read_text())["state"] == "failed"


def test_new_script_is_not_forced_to_exactly_thirty_seconds():
    from retention_storyboard import choose_duration_seconds
    assert choose_duration_seconds(TOPIC, 3, fact_count=2) != 30
