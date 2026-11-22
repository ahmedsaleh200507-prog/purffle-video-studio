"""Offline regressions reproducing Production #91's six footage-stage failures.

These tests use no paid API, live video downloads or claimed production success.
Every video still needs real HD moving source footage and a science review.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from fact_checked_topics import (
    ground_verified_documentary, verified_documentary_kind)
from science_sources import discover_evidence, screen_narration
from retention_storyboard import audit_storyboard
from media_first import (
    scene_footage_seconds, prepare_verified_palette,
    validate_narration_timing)
from visual_director import build_contract


TOPICS = [
    ("Warum beschlägt der Badezimmerspiegel?", "de", "mirror_condensation"),
    ("Why Do Icebergs Break Apart?", "en", "iceberg_breakup"),
    ("Why Do Whales Jump?", "en", "whale_breaching"),
    ("Why Do We See Lightning Before Hearing Thunder?",
     "en", "lightning_thunder_delay"),
    ("Warum leuchtet das Meer nachts blau?", "de",
     "ocean_glow_bioluminescence"),
]


@pytest.mark.parametrize("topic,lang,kind", TOPICS)
def test_full_science_narration_has_two_short_non_filler_scenes(
        topic, lang, kind, tmp_path):
    assert verified_documentary_kind(topic) == kind
    approved = ground_verified_documentary({}, topic, lang, scene_count=2)
    scenes = approved["scenes"]
    assert len(scenes) == 2
    assert all(s["narration"].strip() and s["object"] for s in scenes)
    assert all(len(s["narration"].split()) >= 7 for s in scenes)
    assert all(scene_footage_seconds(s["narration"], lang) < 14
               for s in scenes)
    spoken = SimpleNamespace(scenes=[SimpleNamespace(**s) for s in scenes])
    assert audit_storyboard(topic, spoken, lang)["state"] == "editorial_screen_passed"
    evidence = discover_evidence(topic, lang)
    assert evidence.method == "curated_editor_reviewed"
    report = tmp_path / "science.json"
    screen_narration(spoken, evidence, None, path=report)
    assert json.loads(report.read_text())["state"] == "curated_editor_reviewed"
    wrong = SimpleNamespace(scenes=[
        SimpleNamespace(narration="A fabricated scientific fact about flying sharks."),
        SimpleNamespace(narration=scenes[1]["narration"]),
    ])
    with pytest.raises(RuntimeError, match="science_claim_unverified"):
        screen_narration(wrong, evidence, None, path=report)


def test_iceberg_illustrative_shot_not_fake_calving():
    topic = "Why Do Icebergs Break Apart?"
    scenes = ground_verified_documentary({}, topic, "en", scene_count=2)["scenes"]
    first = build_contract(SimpleNamespace(**scenes[0]), topic, 1)
    second = build_contract(SimpleNamespace(**scenes[1]), topic, 2)
    assert scenes[0]["visual_search_query"] == "iceberg floating ocean"
    assert first["subject"] == "iceberg"
    assert second["subject"] == "iceberg"
    assert second["event_required"] is False


def test_whale_science_ends_on_relevant_real_whale_not_fake_second_jump():
    topic = "Why Do Whales Jump?"
    scenes = ground_verified_documentary({}, topic, "en", scene_count=2)["scenes"]
    assert "breaching" in scenes[0]["visual_search_query"]
    assert "swimming" in scenes[1]["visual_search_query"]
    second = build_contract(SimpleNamespace(**scenes[1]), topic, 2)
    assert not second["event_required"]


def test_short_approved_scene_no_longer_requires_ten_seconds():
    for phrase, lang in [
        ("Light travels faster than sound. Thunder arrives later.", "en"),
        ("Am kühlen Spiegel kondensiert Wasserdampf zu winzigen Tropfen.", "de"),
    ]:
        need = scene_footage_seconds(phrase, lang)
        assert 4 <= need < 10


class FakeVerifiedVideos:
    """Only the preflight scene-boundary contract is mocked, not its meaning."""

    def __init__(self, missing_scene=None):
        self.missing_scene = missing_scene
        self.calls = []
        self.report = {"scenes": [], "state": "searching"}
        self.credits = set()

    def for_scene(self, idx, query, prompt, topic, need, directory):
        self.calls.append({"idx": idx, "need": need, "query": query})
        if idx == self.missing_scene:
            raise RuntimeError("No suitable verified REAL VIDEO for scene")
        row = {"index": idx + 1, "status": "selected", "source": "pixabay",
               "id": str(idx), "sha256": str(idx) * 64,
               "match": {"visual_score": .42, "director_check": {"verified": True}},
               "license": {"id": "PIXABAY"}}
        self.report["scenes"].append(row)
        return SimpleNamespace(
            source="pixabay", id=str(idx), duration=need + 2,
            extra={"sha256": str(idx) * 64, "match": row["match"],
                   "quality": {"width": 3840, "height": 2160},
                   "license": row["license"]})

    def _save(self):
        pass


def test_preflight_uses_each_approved_sentence_length_and_exact_scene_index(
        tmp_path, monkeypatch):
    topic = "Why Do We See Lightning Before Hearing Thunder?"
    spoken = ground_verified_documentary({}, topic, "en", scene_count=2)["scenes"]
    storyboard = SimpleNamespace(scenes=[SimpleNamespace(**s) for s in spoken])
    monkeypatch.setenv("MEDIA_FIRST_REPORT", str(tmp_path / "manifest.json"))
    monkeypatch.setenv("MEDIA_FIRST_WORK_DIR", str(tmp_path / "clips"))
    fake = FakeVerifiedVideos()
    result = prepare_verified_palette(
        topic, SimpleNamespace(language="en"), visuals=fake,
        storyboard=storyboard, min_scenes=2, max_scenes=2, clip_seconds=10.0)
    assert len(result.items) == 2
    assert [call["idx"] for call in fake.calls] == [0, 1]
    assert [call["need"] for call in fake.calls] == [
        scene_footage_seconds(s["narration"], "en") for s in spoken]
    validate_narration_timing(result, storyboard, "en")
    report = json.loads((tmp_path / "manifest.json").read_text())
    assert report["required"] == report["verified"] == 2


def test_failed_first_scene_never_masquerades_as_second_scene_opening(
        tmp_path, monkeypatch):
    topic = "Why Do We See Lightning Before Hearing Thunder?"
    spoken = ground_verified_documentary({}, topic, "en", scene_count=2)["scenes"]
    storyboard = SimpleNamespace(scenes=[SimpleNamespace(**s) for s in spoken])
    monkeypatch.setenv("MEDIA_FIRST_REPORT", str(tmp_path / "failed.json"))
    monkeypatch.setenv("MEDIA_FIRST_WORK_DIR", str(tmp_path / "clips"))
    fake = FakeVerifiedVideos(missing_scene=0)
    with pytest.raises(RuntimeError, match="media_preflight_insufficient_footage"):
        prepare_verified_palette(
            topic, SimpleNamespace(language="en"), visuals=fake,
            storyboard=storyboard, min_scenes=2, max_scenes=2)
    assert any(call["idx"] == 1 for call in fake.calls)
    report = json.loads((tmp_path / "failed.json").read_text())
    assert report["unavailable_scenes"][0]["scene"] == 1
    assert report["opening_review"]["state"] == "not_selected_incomplete_storyboard"


def test_candidate_opening_gate_runs_before_accepted_clip_is_committed():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] /
              "scripts" / "studio_runtime.py").read_text()
    selection = source.index("opening_candidate = prioritize_opening(")
    committed = source.index("self._remember(item, url_key, digest)")
    assert selection < committed
    assert "if idx == 0 and isinstance(self.matcher, SceneMatcher)" in source
    assert "max_candidates" in source
