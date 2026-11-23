"""Two selected English Shorts are prepared, but never rendered with wrong voice."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from fact_checked_topics import ground_verified_documentary, verified_documentary_kind
from science_sources import discover_evidence, screen_narration
from media_first import VerifiedPalette, validate_narration_timing
from topic_footage import deterministic_stock_shots, related_to_topic
from english_reference_policy import enforce_english_reference_only

TOPICS = (
    ("Why Do We See Lightning Before Hearing Thunder?", "lightning_thunder_delay",
     "www.nesdis.noaa.gov", "lightning"),
    ("Why Do the Northern Lights Glow?", "northern_lights_glow",
     "science.nasa.gov", "aurora"),
)


@pytest.mark.parametrize("topic,kind,official,subject", TOPICS)
def test_exact_chosen_topic_matches_official_science(topic,kind,official,subject):
    assert verified_documentary_kind(topic) == kind
    evidence = discover_evidence(topic, "en")
    assert evidence.method == "curated_editor_reviewed"
    assert any(official in source["url"] for source in evidence.sources)
    shots = deterministic_stock_shots(topic)
    assert len(shots) >= 4
    assert shots[0]["object"] == subject
    assert len({x["visual_search_query"] for x in shots}) == len(shots)
    assert all(related_to_topic(topic,x["object"],x["visual_search_query"]) for x in shots)
    assert not any("forest" in x["visual_search_query"] for x in shots)


@pytest.mark.parametrize("topic,kind,official,subject", TOPICS)
@pytest.mark.parametrize("count", [3, 4])
def test_shorts_use_concise_source_reviewed_claims(topic,kind,official,subject,count,tmp_path):
    draft = {"scenes":[{"narration":"A made-up false measurement of 999999 units!"}]}
    doc = ground_verified_documentary(draft, topic, "en", scene_count=count)
    assert len(doc["scenes"]) == count
    assert all("999999" not in x["narration"] for x in doc["scenes"])
    assert all(5 <= len(x["narration"].split()) <= 19 for x in doc["scenes"])
    assert all(x["object"] == subject for x in doc["scenes"])
    script = SimpleNamespace(scenes=[SimpleNamespace(**x) for x in doc["scenes"]])
    evidence = discover_evidence(topic, "en")
    screen_narration(script,evidence,None,path=tmp_path/"science-report.json")
    palette = VerifiedPalette(topic,[{} for _ in range(count)],
        [SimpleNamespace(duration=11.0) for _ in range(count)],set(),[])
    validate_narration_timing(palette,script,language="en")


def test_unrelated_science_not_forced_into_selected_topics():
    for title in ("Why Is the Sky Blue?", "Can Lightning Strike Twice?",
                  "How Do Cats See in the Dark?"):
        assert verified_documentary_kind(title) not in (
            "lightning_thunder_delay","northern_lights_glow")


def test_v4_english_uses_pinned_joe_without_private_secret():
    from english_reference_policy import requires_reference_only, enforce_english_reference_only
    from local_voice import provenance
    assert not requires_reference_only('en')
    enforce_english_reference_only('en')
    assert provenance('en')['model']=='en_US-joe-medium'


def test_both_requests_explicitly_require_same_reference_and_no_mp4_claim():
    import json
    source=(Path(__file__).resolve().parents[1]/
            "requests"/"two-english-shorts-2026-11-19.json")
    queue=json.loads(source.read_text())
    assert queue["state"]=="blocked_reference_voice_not_ready"
    assert queue["reference_sha256"]=="6cc53c46241503f7c6a813ecf98f726eec38bfae33177d624b4ac9190fc41146"
    assert len(queue["videos"])==2
    assert [x["topic"] for x in queue["videos"]]==[x[0] for x in TOPICS]
    assert all(x["language"]=="en" and x["required_narrator"]=="approved_10s_reference_man"
               and x["output_mp4_verified"] is False for x in queue["videos"])
