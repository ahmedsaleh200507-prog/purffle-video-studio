"""Offline contract tests for new source-grounded V3 narration (not live proof)."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from science_sources import (Evidence, active_evidence, discover_evidence,
                             evidence_prompt, screen_narration, use_evidence)

REFERENCE = (
    "Volcanoes form when molten rock called magma reaches Earth's surface. "
    "Underwater volcanic eruptions can accumulate layers of lava and rock. "
    "Over many eruptions, the volcanic mountain may rise above sea level "
    "and form an island. New volcanic islands remain connected to the "
    "seafloor, while waves gradually reshape the coastline."
)


class FakeResponse:
    status_code = 200
    headers = {}
    def __init__(self, data):
        self.data = data
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def iter_content(self, size):
        yield json.dumps(self.data).encode()


def wiki_session():
    data = {"query": {"pages": [
        {"title": "Volcanic island", "pageid": 12, "extract": REFERENCE},
        {"title": "Unrelated jazz music", "pageid": 45,
         "extract": "Jazz is a music genre. " * 50},
    ]}}
    client = Mock()
    client.get.return_value = FakeResponse(data)
    return client


def mock_bundle():
    return Evidence("How can underwater volcanoes form islands?", ({
        "id": "wiki-1", "title": "Volcanic island",
        "url": "https://en.wikipedia.org/wiki/Volcanic_island",
        "tier": "community_edited_reference", "excerpt": REFERENCE,
    },), "model_screened_reference")


def scene(text="Underwater volcanoes can build islands from successive lava layers."):
    return SimpleNamespace(scenes=[SimpleNamespace(narration=text)])


def reply(quote, supported=True, source_id="wiki-1"):
    class LLM:
        def complete_json(self, system, prompt, schema):
            return {"checks": [{"scene": 1, "supported": supported,
                                 "source_id": source_id, "quote": quote,
                                 "reason": "Directly present in source"}]}
    return LLM()


def test_verified_dossier_wins_without_network():
    session = Mock()
    bundle = discover_evidence("How Do Volcanoes Create New Islands?", "en", session=session)
    assert bundle.method == "curated_editor_reviewed"
    assert all(s["url"].startswith("https://www.") for s in bundle.sources)
    session.get.assert_not_called()


def test_search_uses_fixed_wikimedia_host_bounded_extracts_and_metadata():
    client = wiki_session()
    bundle = discover_evidence("Why Do Underwater Mountains Become Islands?", "en", session=client)
    assert bundle.method == "model_screened_reference"
    assert len(bundle.sources) == 1
    assert bundle.sources[0]["title"] == "Volcanic island"
    assert bundle.sources[0]["tier"] == "community_edited_reference"
    args, kwargs = client.get.call_args
    assert args == ("https://en.wikipedia.org/w/api.php",)
    assert kwargs["params"]["exintro"] == 1
    assert kwargs["allow_redirects"] is False
    assert kwargs["stream"] is True


def test_german_wikipedia_uses_german_endpoint():
    client = Mock()
    client.get.return_value = FakeResponse({"query": {"pages": [
        {"title": "Insel", "pageid": 1, "extract": "Vulkanische Inseln entstehen, "
         + "wenn Ausbrüche Lava und Gestein am Meeresboden aufbauen. " * 8}
    ]}})
    bundle = discover_evidence("Wie entstehen Unterwasservulkane Inseln?", "de", session=client)
    assert client.get.call_args.args[0] == "https://de.wikipedia.org/w/api.php"
    assert bundle.method == "model_screened_reference"


def test_valid_source_quote_passes_with_explicit_model_screening_warning(tmp_path):
    out = tmp_path / "science-report.json"
    quote = "Underwater volcanic eruptions can accumulate layers of lava and rock."
    screen_narration(scene(), mock_bundle(), reply(quote), path=out)
    report = json.loads(out.read_text())
    assert report["state"] == "model_screened_reference"
    assert report["scene_checks"][0]["supported"]
    assert "NOT establish" in report["warning"]
    assert "excerpt" not in report["sources"][0]
    assert len(report["sources"]) == 1


@pytest.mark.parametrize("quote,supported,source_id", [
    ("Scientists confirmed islands float free of the ocean floor.", True, "wiki-1"),
    ("Underwater volcanic eruptions can accumulate layers of lava and rock.", False, "wiki-1"),
    ("Underwater volcanic eruptions can accumulate layers of lava and rock.", True, "fake-science"),
    ("lava", True, "wiki-1"),
])
def test_invented_or_unsupported_source_citation_blocks_audio(tmp_path, quote, supported, source_id):
    path = tmp_path / "science-report.json"
    with pytest.raises(RuntimeError, match="science_claim_unverified"):
        screen_narration(scene(), mock_bundle(),
                         reply(quote, supported, source_id), path=path)
    assert json.loads(path.read_text())["state"] == "failed"


def test_rejects_claim_of_always_when_source_does_not_claim_always(tmp_path):
    quote = "Underwater volcanic eruptions can accumulate layers of lava and rock."
    with pytest.raises(RuntimeError, match="science_claim_unverified"):
        screen_narration(
            scene("Underwater volcanoes always create brand new floating islands."),
            mock_bundle(), reply(quote), path=tmp_path / "science-report.json")


def test_network_failure_is_not_silently_accepted():
    client = Mock()
    client.get.side_effect = TimeoutError("secret part of original URL")
    with pytest.raises(RuntimeError, match="science_sources_unavailable"):
        discover_evidence("How do parrots learn to talk?", "en", session=client)


def test_llm_unavailable_rejects_claims(tmp_path):
    llm = Mock()
    llm.complete_json.side_effect = ValueError("unexpected response")
    target = tmp_path / "science-report.json"
    with pytest.raises(RuntimeError, match="science_claim_unverified"):
        screen_narration(scene(), mock_bundle(), llm, path=target)
    assert json.loads(target.read_text())["state"] == "failed"


def test_use_evidence_context_restored_and_prompt_contains_no_phantom_sources():
    assert active_evidence() is None
    bundle = mock_bundle()
    with use_evidence(bundle):
        assert active_evidence() == bundle
        assert "Underwater volcanic eruptions" in evidence_prompt(bundle)
    assert active_evidence() is None


def test_render_source_stage_precedes_draft_and_tts():
    path = Path(__file__).parents[1] / "scripts" / "render_job.py"
    source = path.read_text()
    assert source.index("stage = 'science_sources'") < source.index("studio.draft(")
    assert source.index("screen_narration(") < source.index("studio.produce(")
    assert "SCIENCE_REPORT" in source


def test_batch_reports_science_root_causes_not_false_provider_errors():
    from batch import classify_failure
    assert classify_failure(
        "science_sources_unavailable: no topic-relevant reference extracts",
        "provider health says http_429 in unrelated log") == "science_reference_unavailable"
    assert classify_failure(
        "science_claim_unverified: unsupported narration scene",
        "other source said invalid video") == "science_claim_unsupported"



def test_octopus_plural_alias_finds_real_singular_encyclopedia_article():
    """The trending octopuses topic previously returned zero source extracts."""
    client = Mock()
    client.get.side_effect = [
        FakeResponse({"query":{"pages":[]}}),
        FakeResponse({"query":{"pages":[{
            "title":"Octopus", "pageid":11,
            "extract":("An octopus is an eight-armed marine mollusc in the "
                       "cephalopod class. It has three hearts and uses gills. " * 6)
        }]}}),
    ]
    bundle = discover_evidence("Why Do Octopuses Have Three Hearts?",
                               "en",session=client)
    assert bundle.method == "model_screened_reference"
    assert bundle.sources[0]["title"] == "Octopus"
    assert bundle.sources[0]["url"] == "https://en.wikipedia.org/wiki/Octopus"
    assert "three hearts" in bundle.sources[0]["excerpt"]
    assert client.get.call_count == 2
    assert client.get.call_args.kwargs["params"]["gsrsearch"] == "octopus"


def test_german_crocodile_compound_alias_is_source_verified_not_invented():
    client = Mock()
    client.get.side_effect = [
        FakeResponse({"query":{"pages":[{"title":"Unrelated bridge",
            "extract":"A bridge can carry traffic over a river. " * 15}]}}),
        FakeResponse({"query":{"pages":[{"title":"Nilkrokodil",
            "extract":"Das Nilkrokodil gehört zur Familie der Krokodile. " * 11}]}}),
    ]
    bundle = discover_evidence(
        "Was unterscheidet Nilkrokodile von Salzwasserkrokodilen?",
        "de",session=client)
    assert bundle.sources[0]["title"] == "Nilkrokodil"
    assert all(s["tier"] == "community_edited_reference" for s in bundle.sources)
    assert client.get.call_count == 2


def test_winter_animal_reference_fallback_does_not_create_fake_sources():
    client = Mock()
    client.get.return_value = FakeResponse({"query":{"pages":[]}})
    with pytest.raises(RuntimeError,match="science_sources_unavailable"):
        discover_evidence("Wie überleben Tiere im Winterwald?",
                          "de",session=client)
    assert client.get.call_count >= 2


def test_structure_failures_redraft_before_voice_but_do_not_fill_missing_action():
    from pathlib import Path
    repo = Path(__file__).resolve().parents[1]
    render=(repo/"scripts"/"render_job.py").read_text()
    runtime=(repo/"scripts"/"studio_runtime.py").read_text()
    assert "except (ValueError, TypeError) as draft_error:" in render
    assert "continue" in render[render.index("except (ValueError, TypeError) as draft_error:"):
                                render.index("from science_fact_guard import validate_unsourced_quantities")]
    assert 'raise ValueError("Missing structured scene fields: "' in runtime
    assert 'if not data["visual_search_query"] or not data["action"]' in runtime



def test_factual_failure_labels_precede_unrelated_groq_limit_logs():
    from batch import classify_failure
    other = "WARNING unrelated API 429 rate limit reached"
    assert classify_failure(
        "retention_storyboard_invalid: generic intro before useful hook",
        other) == "storyboard_quality_rejected"
    assert classify_failure(
        "Missing structured scene fields: action",
        other) == "script_visual_schema_invalid"


# Regression coverage for production ZIP purffle-videos-88 (2026-11-22).
# All HTTP results here are mocked; these tests do not claim live MP4 success.
@pytest.mark.parametrize("topic,language,article", [
    ("Wie wird aus Kuhmist Strom erzeugt?", "de", "Biogas"),
    ("Warum frieren Autoscheiben über Nacht zu?", "de", "Reif (Niederschlag)"),
    ("How Do People Survive a Freezing Night in the Wild?", "en", "Hypothermia"),
    ("Why Do Rocket Launches Create Huge Smoke Clouds?", "en", "Rocket engine"),
])
def test_failed_batch_topics_recover_relevant_existing_articles(topic, language, article):
    client = Mock()
    title = article
    explain = (f"{title} is a subject described by an encyclopedia entry. "
               "The result is reference context, not independent scientific verification. ") * 6
    client.get.side_effect = [
        FakeResponse({"query": {"pages": []}}),
        FakeResponse({"query": {"pages": [
            {"title": title, "pageid": 101, "extract": explain}
        ]}}),
    ]
    result = discover_evidence(topic, language, session=client)
    assert result.method == "model_screened_reference"
    assert result.sources[0]["title"] == title
    assert client.get.call_count == 2
    assert client.get.call_args.kwargs["params"]["gsrsearch"] in (
        "Biogas", "Reif (Niederschlag)", "Hypothermia", "Rocket engine"
    )


def test_distractor_wild_tv_episode_not_accepted_as_survival_advice():
    client = Mock()
    client.get.side_effect = [
        FakeResponse({"query": {"pages": [
            {"title": "List of Man vs. Wild episodes",
             "extract": "A television series with multiple seasons and episodes. " * 8},
            {"title": "Wild China",
             "extract": "A television nature documentary series. " * 8},
        ]}}),
        FakeResponse({"query": {"pages": [
            {"title": "Hypothermia",
             "extract": "Hypothermia occurs as the body's core temperature falls. " * 8},
        ]}}),
    ]
    result = discover_evidence(
        "How Do People Survive a Freezing Night in the Wild?",
        "en", session=client)
    assert [s["title"] for s in result.sources] == ["Hypothermia"]
    assert client.get.call_count == 2


def test_science_reference_transient_http_failure_uses_real_backup_query():
    client = Mock()
    client.get.side_effect = [
        TimeoutError("transient timeout"),
        FakeResponse({"query": {"pages": [
            {"title": "Biogas",
             "extract": "Biogas entsteht durch mikrobielle Zersetzung von Biomasse. " * 8},
        ]}}),
    ]
    bundle = discover_evidence(
        "Wie wird aus Kuhmist Strom erzeugt?", "de", session=client)
    assert bundle.sources[0]["title"] == "Biogas"
    assert client.get.call_count == 2


def test_german_aurora_glow_uses_approved_noaa_nasa_dossier_no_network(tmp_path):
    from fact_checked_topics import (
        verified_documentary_kind, ground_verified_documentary)
    topic = "Warum leuchten Polarlichter?"
    assert verified_documentary_kind(topic) == "northern_lights_glow"
    client = Mock()
    bundle = discover_evidence(topic, "de", session=client)
    assert bundle.method == "curated_editor_reviewed"
    assert len(bundle.sources) >= 2
    client.get.assert_not_called()

    approved = ground_verified_documentary({}, topic, "de", scene_count=3)
    script = SimpleNamespace(scenes=[
        SimpleNamespace(narration=s["narration"])
        for s in approved["scenes"]
    ])
    out = tmp_path / "science-report.json"
    screen_narration(script, bundle, None, path=out)
    assert json.loads(out.read_text())["state"] == "curated_editor_reviewed"

    # Curated status must never let arbitrary, unsupported narration through.
    invented = scene("NASA confirmed auroras always predict tomorrow's weather.")
    with pytest.raises(RuntimeError, match="science_claim_unverified"):
        screen_narration(invented, bundle, None, path=out)
    assert json.loads(out.read_text())["state"] == "failed"


def test_retrieval_with_only_irrelevant_titles_fails_closed():
    client = Mock()
    client.get.return_value = FakeResponse({"query": {"pages": [
        {"title": "Wild China",
         "extract": "A television nature documentary series. " * 12},
    ]}})
    with pytest.raises(RuntimeError, match="science_sources_unavailable"):
        discover_evidence(
            "How Do People Survive a Freezing Night in the Wild?",
            "en", session=client)


def test_frost_search_retries_third_query_when_second_article_title_differs():
    """A valid Raureif article may not lexically match 'Reif (Niederschlag)'."""
    client = Mock()
    client.get.side_effect = [
        FakeResponse({"query": {"pages": []}}),
        FakeResponse({"query": {"pages": [
            {"title": "Raureif",
             "extract": "Raureif bildet sich bei Feuchte und Kälte. " * 12},
        ]}}),
        FakeResponse({"query": {"pages": [
            {"title": "Raureif",
             "extract": "Raureif bildet sich bei Feuchte und Kälte. " * 12},
        ]}}),
    ]
    result = discover_evidence(
        "Warum frieren Autoscheiben über Nacht zu?", "de", session=client)
    assert result.sources[0]["title"] == "Raureif"
    assert client.get.call_count == 3
    assert client.get.call_args.kwargs["params"]["gsrsearch"] == "Raureif"
