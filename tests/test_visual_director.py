"""The root fix: source-reviewed sentence -> independently verified REAL shot.

No network access, narrators or provider secrets. A passing test means
contracts and chronology, not that any real-world stock video exists.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from media_first import prepare_verified_palette
from visual_director import (
    build_contract, inspect_action, metadata_allows, visual_scores,
    use_story_scene_target, story_scene_target,
)
from fact_checked_topics import ground_verified_documentary


TOPIC = "What Makes a Volcano Suddenly Erupt?"


def scenes(topic=TOPIC, language="en", count=3):
    return [SimpleNamespace(**scene) for scene in
            ground_verified_documentary({}, topic, language, scene_count=count)["scenes"]]


def test_story_first_contract_tracks_speech_actions_not_generic_topic():
    first, middle, last = [build_contract(s, TOPIC, i+1)
                           for i, s in enumerate(scenes())]
    assert first["family"] == "lava_flow"
    assert "lava" in first["queries"][0]
    assert middle["family"] == "illustrative_subject"
    assert middle["illustrative_science"] is True
    assert last["family"] == "eruption"
    assert any("eruption" in q for q in last["queries"])
    assert not metadata_allows(last, "A quiet fog-covered volcano mountain")
    assert metadata_allows(last, "A massive volcanic eruption with ash plume")
    assert metadata_allows(first, "hot lava moving slowly down volcano")
    assert not metadata_allows(first, "blue ocean horizon no lava")


def test_event_contract_does_not_map_invisible_science_to_fake_ice_breaking():
    subject = SimpleNamespace(
        narration="When gases escape, they can break magma apart and drive explosive eruptions.",
        object="volcano", action="ambient",
        visual_search_query="volcano erupting lava")
    assert build_contract(subject, TOPIC, 3)["family"] == "eruption"
    ice = SimpleNamespace(
        narration="Large icebergs can break apart in the ocean.",
        object="iceberg", action="ambient",
        visual_search_query="iceberg floating ocean")
    assert build_contract(ice, "Why Do Icebergs Break Apart?", 1)["family"] == "breaking"


def test_visual_contract_is_multi_frame_not_provider_title_only():
    contract = build_contract(scenes()[-1], TOPIC, 3)
    calm = visual_scores(contract, [[.21, .31], [.23, .33], [.22, .32]])
    assert calm["verified"] is False
    eruption = visual_scores(contract, [[.20,.28], [.31,.19], [.25,.26]])
    assert eruption["verified"] is True
    assert eruption["sampled_scene_frames"] == 3
    with pytest.raises(RuntimeError, match="unverified_scores"):
        visual_scores(contract, [[.2, float("nan")]])
    with pytest.raises(RuntimeError, match="unverified_frames"):
        inspect_action("missing.mp4", 10, .5, contract, frames=[])


def test_scene_target_context_never_leaks_to_unrelated_english_or_german_job():
    assert story_scene_target() is None
    with use_story_scene_target(3):
        assert story_scene_target() == 3
    assert story_scene_target() is None


class FakeRealVisuals:
    def __init__(self, approved):
        self.approved = approved
        self.report = {"scenes": [], "state": "searching"}
        self.credits = {"licensed test fixture"}
        self.saved = []
        self._shot_deadline = 0
        self.calls = []

    def for_scene(self, idx, query, prompt, topic, need, dest_dir):
        spec = json.loads(prompt)
        contract = spec["_visual_contract"]
        self.calls.append((idx, query, contract["index"]))
        if query not in self.approved:
            raise RuntimeError("No suitable verified REAL VIDEO for scene")
        marker = str(len(self.calls))
        row = {
            "index": idx+1, "status": "selected",
            "source": "pixabay", "id": marker,
            "match": {"visual_score": .42,
                      "director_check": {"verified": True, "family": contract["family"]}},
            "sha256": marker * 64, "license": {"id": "PIXABAY"},
        }
        self.report["scenes"].append(row)
        return SimpleNamespace(
            source="pixabay", id=marker,
            extra={"sha256": row["sha256"], "match": row["match"],
                   "quality": {"width": 2160, "height": 3840},
                   "license": row["license"]})

    def _save(self):
        self.saved.append(dict(self.report))


def test_director_preserves_spoken_order_and_retries_search_aliases(tmp_path,monkeypatch):
    monkeypatch.setenv("MEDIA_FIRST_REPORT", str(tmp_path / "manifest.json"))
    monkeypatch.setenv("MEDIA_FIRST_WORK_DIR", str(tmp_path / "clips"))
    source_scenes = scenes()
    c = [build_contract(x, TOPIC, i+1) for i,x in enumerate(source_scenes)]
    allowed = {c[0]["queries"][1], c[1]["queries"][0], c[2]["queries"][2]}
    fake = FakeRealVisuals(allowed)
    storyboard = SimpleNamespace(scenes=source_scenes)
    palette = prepare_verified_palette(
        TOPIC, object(), storyboard=storyboard, visuals=fake,
        min_scenes=3, max_scenes=3)
    assert len(palette.items) == 3
    assert palette.plans[0]["visual_search_query"] == c[0]["queries"][1]
    assert palette.plans[1]["visual_search_query"] == c[1]["queries"][0]
    assert palette.plans[2]["visual_search_query"] == c[2]["queries"][2]
    assert [s["index"] for s in fake.report["scenes"]] == [1,2,3]
    manifest = json.loads((tmp_path/"manifest.json").read_text())
    assert manifest["director_mode"]
    assert manifest["verified"] == 3
    assert len(manifest["selected"]) == 3
    assert not manifest["unavailable_scenes"]
    assert [x["family"] for x in c] == [
        "lava_flow", "illustrative_subject", "eruption"]


def test_director_fails_closed_when_last_scene_only_has_misty_mountain(
        tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_FIRST_REPORT", str(tmp_path / "failed.json"))
    monkeypatch.setenv("MEDIA_FIRST_WORK_DIR", str(tmp_path / "clips"))
    source_scenes = scenes()
    c = [build_contract(x, TOPIC, i+1) for i,x in enumerate(source_scenes)]
    fake = FakeRealVisuals({c[0]["queries"][0], c[1]["queries"][0]})
    with pytest.raises(RuntimeError, match="director requires accurate coverage"):
        prepare_verified_palette(
            TOPIC, object(), storyboard=SimpleNamespace(scenes=source_scenes),
            visuals=fake, min_scenes=3, max_scenes=3)
    report = json.loads((tmp_path/"failed.json").read_text())
    assert report["verified"] == 2
    assert report["unavailable_scenes"][0]["scene"] == 3
    assert fake.report["state"] == "failed"


def test_production_calls_science_review_before_stock_then_locked_speaker():
    producer = (Path(__file__).resolve().parents[1] /
                "scripts" / "render_job.py").read_text()
    assert producer.index("studio.draft(") < producer.index(
        "screen_narration(") < producer.index(
        "prepare_verified_palette(") < producer.index("studio.produce(")
    assert "storyboard=screenplay" in producer
    assert "palette.media_map" in producer
    assert "enforce_english_reference_only" in producer
    assert "validate_result(video" in producer
    assert "save_storyboard_report" in producer


def test_production_never_reorders_reviewed_narration_to_win_visual_impact():
    source = (Path(__file__).resolve().parents[1] /
              "scripts" / "media_first.py").read_text()
    assert "prioritize_opening(topic, items[:1]" in source
    assert "if director_mode" in source
    assert "if director_mode and len(items) != len(options)" in source
