"""105 three-topic live proof regressions: truthful sources without paid API."""
from types import SimpleNamespace
from unittest.mock import Mock

from fact_checked_topics import verified_documentary_kind, ground_verified_documentary
from science_sources import discover_evidence, screen_narration


def test_105_octopus_stops_using_blue_ringed_species_as_heart_reference():
    topic = "Why do octopuses have three hearts?"
    assert verified_documentary_kind(topic) == "octopus_three_hearts"
    network = Mock()
    evidence = discover_evidence(topic, "en", session=network)
    assert evidence.method == "curated_editor_reviewed"
    assert len(evidence.sources) == 2
    assert "ocean.si.edu" in evidence.sources[0]["url"]
    assert "horniman.ac.uk" in evidence.sources[1]["url"]
    network.get.assert_not_called()


def test_105_german_thunder_uses_noaa_approved_dossier_without_wikipedia():
    topic = "Warum sehen wir den Blitz vor dem Donner?"
    assert verified_documentary_kind(topic) == "lightning_thunder_delay"
    network = Mock()
    evidence = discover_evidence(topic, "de", session=network)
    assert evidence.method == "curated_editor_reviewed"
    assert all("noaa" in x["url"] or "nssl" in x["url"]
               for x in evidence.sources)
    network.get.assert_not_called()


def test_105_steel_ship_remains_recognized():
    assert verified_documentary_kind("Why do steel ships float?") == "steel_ship_buoyancy"


def test_105_official_octopus_script_has_three_complete_filmable_scenes(tmp_path):
    topic = "Why do octopuses have three hearts?"
    evidence = discover_evidence(topic, "en")
    data = ground_verified_documentary({"topic": topic}, topic, "en", scene_count=3)
    assert len(data["scenes"]) == 3
    assert all(x["object"] == "octopus" for x in data["scenes"])
    assert all(x["visual_search_query"] == "octopus swimming underwater" for x in data["scenes"])
    assert "gills" in data["scenes"][1]["narration"]
    script = SimpleNamespace(
        scenes=[SimpleNamespace(narration=x["narration"]) for x in data["scenes"]])
    output = tmp_path / "octopus-science-report.json"
    screen_narration(script, evidence, llm=None, path=output)
    import json
    assert json.loads(output.read_text())["state"] == "curated_editor_reviewed"


def test_105_official_german_narration_exact_match_fails_closed_on_change(tmp_path):
    topic = "Warum sehen wir den Blitz vor dem Donner?"
    evidence = discover_evidence(topic, "de")
    data = ground_verified_documentary({"topic": topic}, topic, "de", scene_count=3)
    assert "Licht" in data["scenes"][1]["narration"]
    script = SimpleNamespace(
        scenes=[SimpleNamespace(narration=x["narration"]) for x in data["scenes"]])
    screen_narration(script, evidence, llm=None, path=tmp_path/"good.json")
    script.scenes[1].narration = "Der Donner ist schneller als das Licht."
    import pytest
    with pytest.raises(RuntimeError, match="science_claim_unverified"):
        screen_narration(script, evidence, llm=None, path=tmp_path/"bad.json")


def test_105_curated_draft_does_not_call_groq(monkeypatch):
    from official_draft import approved_dossier_draft
    from purffle_shorts import script as mod

    def safe_normalizer(payload, subject, style, lang):
        assert style == "facts"
        return SimpleNamespace(
            scenes=[SimpleNamespace(narration=x["narration"]) for x in payload["scenes"]],
            language=lang)

    monkeypatch.setattr(mod, "normalize", safe_normalizer)
    for topic, lang in (
        ("Why do octopuses have three hearts?", "en"),
        ("Warum sehen wir den Blitz vor dem Donner?", "de"),
        ("Why do steel ships float?", "en"),
    ):
        official = discover_evidence(topic, lang)
        script, picked, writer = approved_dossier_draft(topic, lang, official)
        assert len(script.scenes) == 3
        assert picked.subject == topic and writer == "approved_official_dossier"
    assert approved_dossier_draft(
        "Why are clouds fluffy?", "en", SimpleNamespace(method="model_screened_reference")
    ) is None
