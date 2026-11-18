"""Offline V3 contract tests: discover/verify clips BEFORE generating narration."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from media_first import (VerifiedPalette, _grounded_candidates,
                         active_palette, align_script_to_palette,
                         footage_prompt, prepare_verified_palette, use_palette)


TOPIC = "Why Do Some Volcanoes Erupt Without Warning?"


class FakeVisuals:
    def __init__(self, accepted):
        self.accepted = set(accepted)
        self.calls = []
        self.credits = {"A licensed real volcano clip | Pixabay"}
        self.report = {"state": "searching", "scenes": []}
        self.saved = []
        self._shot_deadline = 0

    def for_scene(self, idx, query, prompt, topic, need, directory):
        self.calls.append((query, need, topic))
        plan = json.loads(prompt)
        if query not in self.accepted:
            self.report["scenes"].append({
                "index": idx + 1, "status": "failed", "plan": plan,
                "rejections": [{"reason": "metadata mismatch"}],
            })
            self.report["state"] = "failed"
            raise RuntimeError("No suitable verified REAL VIDEO for scene 1")
        media = SimpleNamespace(
            source="pixabay", id=f"unique-{len(self.calls)}",
            extra={"sha256": str(len(self.calls)) * 64,
                   "quality": {"width": 1080, "height": 1920, "portrait_crop_scale": 1},
                   "license": {"id": "Pixabay"}})
        self.report["scenes"].append({
            "index": idx + 1, "status": "selected", "plan": plan,
            "source": media.source, "id": media.id,
            "match": {"visual_score": 0.32}, "license": {"id": "Pixabay"},
            "sha256": media.extra["sha256"],
        })
        return media

    def _save(self):
        self.saved.append(json.loads(json.dumps(self.report)))


def test_preflight_only_returns_truly_verified_distinct_clips(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_FIRST_REPORT", str(tmp_path / "media-first-plan.json"))
    monkeypatch.setenv("MEDIA_FIRST_WORK_DIR", str(tmp_path / "scratch"))
    visuals = FakeVisuals({"volcano erupting", "volcano landscape", "lightning storm"})
    result = prepare_verified_palette(
        TOPIC, object(), None, visuals=visuals, min_scenes=3, max_scenes=4,
        clip_seconds=10.0)
    assert len(result.items) == 3
    assert list(result.media_map) == [(0, 0), (1, 0), (2, 0)]
    assert result.plans[0]["visual_search_query"] == "volcano erupting"
    assert "volcanic lava" in [x["query"] for x in result.attempts
                               if x["status"] == "rejected"]
    assert visuals.report["state"] == "footage_ready"
    assert len(visuals.report["scenes"]) == 3
    assert [x["index"] for x in visuals.report["scenes"]] == [1, 2, 3]
    assert all(x["visual_mode"] == "media_first_verified"
               for x in visuals.report["scenes"])
    manifest = json.loads((tmp_path / "media-first-plan.json").read_text())
    assert manifest["verified"] == 3
    assert manifest["required"] == 3
    assert len(manifest["selected"]) == 3
    assert len({x["sha256"] for x in manifest["selected"]}) == 3


def test_video_fails_early_without_enough_verified_clips(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_FIRST_REPORT", str(tmp_path / "media-first-plan.json"))
    monkeypatch.setenv("MEDIA_FIRST_WORK_DIR", str(tmp_path / "scratch"))
    visuals = FakeVisuals({"volcano erupting"})
    with pytest.raises(RuntimeError, match="media_preflight_insufficient_footage"):
        prepare_verified_palette(TOPIC, object(), None, visuals=visuals)
    assert visuals.report["state"] == "failed"
    assert visuals.report["scenes"][0]["status"] == "selected"
    report = json.loads((tmp_path / "media-first-plan.json").read_text())
    assert report["verified"] == 1


def test_script_is_locked_to_verified_footage_instead_of_llm_queries():
    plans = [
        {"main_character": "", "object": subject, "action": "ambient",
         "location": "", "time": "", "visual_search_query": query}
        for subject, query in [("volcano", "volcano erupting"),
                               ("lava", "volcanic lava"),
                               ("cloud", "storm clouds")]]
    palette = VerifiedPalette(TOPIC, plans, [object()] * 3, set(), [])
    script = {"title": TOPIC, "scenes": [
        {"narration": "Volcanoes build up pressure", "visual_search_query": "unfilmable pressure gauge"},
        {"narration": "Scientists study volcanoes", "visual_search_query": "microscopic machine"},
        {"narration": "Warning signs may appear", "visual_search_query": "unrelated actor"},
    ]}
    with use_palette(palette):
        assert active_palette() is palette
        prompt = footage_prompt(palette)
        assert "EXACTLY 3 scenes" in prompt
        aligned = align_script_to_palette(script, active_palette())
    assert active_palette() is None
    assert [s["visual_search_query"] for s in aligned["scenes"]] == [
        "volcano erupting", "volcanic lava", "storm clouds"]
    assert all(s["search_query"] == s["visual_search_query"]
               and s["image_prompt"] == "" for s in aligned["scenes"])
    assert [s["narration"] for s in aligned["scenes"]] == [
        "Volcanoes build up pressure", "Scientists study volcanoes",
        "Warning signs may appear"]
    assert script["scenes"][0]["visual_search_query"] == "unfilmable pressure gauge"


def test_extra_llm_scenes_are_merged_without_losing_any_words():
    palette = VerifiedPalette(TOPIC, [
        {"main_character": "", "object": "volcano", "action": "ambient",
         "location": "", "time": "", "visual_search_query": f"volcano query {i}"}
        for i in range(3)], [object()] * 3, set(), [])
    script = {"scenes": [{"narration": x} for x in
                         ("One.", "Two.", "Three.", "Four.", "Five.")]}
    output = align_script_to_palette(script, palette)
    assert len(output["scenes"]) == 3
    assert " ".join(s["narration"] for s in output["scenes"]) == (
        "One. Two. Three. Four. Five.")


def test_unrecognized_subject_fails_without_inventing_random_footage(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_FIRST_REPORT", str(tmp_path / "media-first-plan.json"))
    with pytest.raises(RuntimeError, match="media_preflight_no_topic_palette"):
        prepare_verified_palette("Obscure xyzqvx abstract invention",
                                 object(), llm=None, visuals=FakeVisuals(set()))


def test_llm_cannot_redirect_familiar_topic_to_unrelated_subject():
    class FakeLLM:
        def complete_json(self, system, user, schema):
            return {"shots": [
                {"object": "person", "query": "person using smartphone"},
                {"object": "volcano", "query": "volcano lava flowing"},
                {"object": "astronaut", "query": "astronaut playing tennis"},
            ]}
    plans = _grounded_candidates(TOPIC, FakeLLM())
    assert any(x["visual_search_query"] == "volcano lava flowing" for x in plans)
    assert not any("smartphone" in x["visual_search_query"] for x in plans)
    assert not any("astronaut" in x["visual_search_query"] for x in plans)


def test_render_job_has_media_first_before_voice_by_contract():
    code = (Path(__file__).parents[1] / "scripts" / "render_job.py").read_text()
    start = code.index("stage = 'media_preflight'")
    draft = code.index("studio.draft(")
    production = code.index("studio.produce(")
    assert start < draft < production
    assert "palette.media_map" in code
    assert "PURFFLE_MEDIA_FIRST" in code


@pytest.mark.parametrize("scene_count", [3, 4])
def test_preapproved_lightning_script_fits_verified_clip_count(scene_count):
    from fact_checked_topics import ground_lightning_explainer
    original = {"scenes": [{"narration": "Invented Elm Street 12 hits"}]}
    topic = "Why Does Lightning Strike the Same Place Again and Again?"
    prepared = ground_lightning_explainer(original, topic, "en",
                                          scene_count=scene_count)
    assert len(prepared["scenes"]) == scene_count
    assert "Elm Street" not in json.dumps(prepared)
    assert all(len(s["narration"].split()) <= 25
               for s in prepared["scenes"])
