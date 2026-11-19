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
