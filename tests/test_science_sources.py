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
    bundle = discover_evidence("How can underwater volcanoes form islands?", "en", session=client)
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
