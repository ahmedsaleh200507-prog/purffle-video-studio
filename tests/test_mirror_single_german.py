"""Regression tests for source-checked single bathroom mirror video (DE).

All tests run offline. These are NOT claims that stock footage or MP4 exists.
"""
from types import SimpleNamespace
import pytest

from fact_checked_topics import (
    ground_verified_documentary, verified_documentary_kind,
)
from science_sources import discover_evidence, screen_narration
from topic_footage import deterministic_stock_shots, related_to_topic
from media_first import VerifiedPalette, validate_narration_timing
from english_reference_policy import enforce_english_reference_only


TOPIC = "Warum beschlägt der Badezimmerspiegel?"


def test_german_mirror_topic_gets_official_science_dossier():
    assert verified_documentary_kind(TOPIC) == "mirror_condensation"
    assert verified_documentary_kind("Why Does Your Bathroom Mirror Fog Up?") == "mirror_condensation"
    assert verified_documentary_kind("Why is the night sky cloudy?") is None
    evidence = discover_evidence(TOPIC, language="de")
    assert evidence.method == "curated_editor_reviewed"
    assert {x["url"].split("/")[2] for x in evidence.sources} == {
        "www.nesdis.noaa.gov", "scied.ucar.edu"
    }


def test_german_story_only_describes_evaporation_and_condensation(tmp_path):
    for count in (3, 4):
        story = ground_verified_documentary(
            {"scenes": [{"narration": "Made-up wild claim."}]},
            TOPIC, "de", scene_count=count
        )
        assert len(story["scenes"]) == count
        assert story["title"] == "Warum beschlägt der Badezimmerspiegel?"
        assert all("Made-up" not in x["narration"] for x in story["scenes"])
        assert all(6 <= len(x["narration"].split()) <= 18 for x in story["scenes"])
        assert any("Wasserdampf" in x["narration"] for x in story["scenes"])
        evidence = discover_evidence(TOPIC, language="de")
        script = SimpleNamespace(scenes=[SimpleNamespace(**x) for x in story["scenes"]])
        screen_narration(script, evidence, None, path=tmp_path / f"science-{count}.json")
        assert (tmp_path / f"science-{count}.json").is_file()
        palette = VerifiedPalette(TOPIC, [{}] * count,
            [SimpleNamespace(duration=11.0) for _ in range(count)], set(), [])
        validate_narration_timing(palette, script, language="de")


def test_german_mirror_visual_queries_are_about_bathroom():
    candidates = deterministic_stock_shots(TOPIC)
    assert len(candidates) >= 4
    assert candidates[0]["visual_search_query"] == "foggy bathroom mirror"
    assert all(related_to_topic(
        TOPIC, x["object"], x["visual_search_query"]) for x in candidates)
    assert "fog landscape" not in [x["visual_search_query"] for x in candidates]


def test_german_thorsten_not_blocked_by_english_reference_policy():
    enforce_english_reference_only("de", strict=True)
    with pytest.raises(RuntimeError, match="reference_voice_not_ready"):
        enforce_english_reference_only("en", strict=True)
