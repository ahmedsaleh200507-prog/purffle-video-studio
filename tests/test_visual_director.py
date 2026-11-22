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
    whale = SimpleNamespace(
        narration="A humpback whale bursts out of the sea and splashes down.",
        object="whale", action="ambient",
        visual_search_query="whale ocean close up")
    assert build_contract(whale, "Why Do Whales Jump?", 1)["family"] == "breaching"


def test_visual_contract_is_multi_frame_not_provider_title_only():
    contract = build_contract(scenes()[-1], TOPIC, 3)
    calm = visual_scores(contract, [[.21, .31], [.23, .33], [.22, .32]])
    assert calm["verified"] is False
    eruption = visual_scores(contract, [[.20,.28], [.31,.19], [.25,.26]])
    assert eruption["verified"] is True
    assert eruption["sampled_scene_frames"] == 3
    # A stock source may show the eruption at second 40 while the final
    # short uses seconds 0-10. The opening must never pass on that late event.
    late = [[.20, .31], [.21, .29], [.35, .19]]
    assert visual_scores(contract, late)["verified"]
    assert not visual_scores(contract, late, opening=True)["verified"]
    assert visual_scores(contract, late, opening=True)[
        "opening_action_visible"] is False
    early = [[.34, .21], [.29, .22], [.20, .30]]
    assert visual_scores(contract, early, opening=True)["verified"]
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
    runtime = (Path(__file__).resolve().parents[1] /
               "scripts" / "studio_runtime.py").read_text()
    assert "min(float(need), float(quality[\"duration\"]))" in runtime
    assert "opening=(idx == 0)" in runtime
    assert "visual_director_unverified: at least one narrated scene" in producer
    assert "visual_director_sequence_mismatch" in producer
    assert "save_storyboard_report" in producer


def test_production_never_reorders_reviewed_narration_to_win_visual_impact():
    source = (Path(__file__).resolve().parents[1] /
              "scripts" / "media_first.py").read_text()
    assert "prioritize_opening(topic, items[:1]" in source
    assert "if director_mode" in source
    assert "if director_mode and len(items) != len(options)" in source



def test_wave_intro_uses_independent_subject_proof_not_unshown_action():
    """Reported ocean-wave footage passed CLIP but was rejected as 'illustrative_subject'.

    A generic ocean-waves scene makes no claim of an exact breaking event.
    Source metadata, physical motion, vertical crop, license and local CLIP
    have ALREADY been checked before this helper. Do not manufacture action.
    """
    from visual_director import verify_visible_event_or_illustrative_subject
    scene=SimpleNamespace(
        narration="Wind transfers energy across the ocean surface.",
        object="wave",action="ambient",
        visual_search_query="ocean waves")
    contract=build_contract(scene,"Warum entstehen Meereswellen?",1)
    assert contract["family"]=="illustrative_subject"
    assert contract["event_required"] is False
    calls=[]
    proof=verify_visible_event_or_illustrative_subject(
        "real-ocean-waves.mp4",10,.5,contract,
        {"verification":"local_clip_screening","visual_score":.30},
        event_inspector=lambda *a,**k:calls.append(1))
    assert proof["verified"]
    assert not proof["event_required"]
    assert proof["method"]=="local_clip_subject_match_no_specific_event_claim"
    assert not calls


def test_illustrative_scene_rejects_missing_real_frame_verification():
    from visual_director import verify_visible_event_or_illustrative_subject
    scene=SimpleNamespace(
        narration="Die Wellen entstehen durch Wind.",
        object="wave",action="ambient",visual_search_query="ocean waves")
    contract=build_contract(scene,"Warum entstehen Meereswellen?",1)
    for proof in ({}, {"verification":"metadata_only"},
                  {"verification":"claimed_clip_proof"}):
        with pytest.raises(RuntimeError,match="missing_independent_clip_match"):
            verify_visible_event_or_illustrative_subject(
                "unverified.mp4",10,.5,contract,proof)


def test_true_event_scene_keeps_original_multiframe_action_gate():
    from visual_director import verify_visible_event_or_illustrative_subject
    scene=SimpleNamespace(
        narration="In Küstennähe brechen Wellen gegen das Ufer.",
        object="wave",action="ambient",
        visual_search_query="wave breaking waves")
    contract=build_contract(scene,"Warum entstehen Meereswellen?",2)
    assert contract["event_required"] is True
    calls=[]
    def failed_inspector(*args,**kwargs):
        calls.append(kwargs.get("opening"))
        return {"verified":False,"family":"water_motion"}
    with pytest.raises(ValueError,match="action_not_visible"):
        verify_visible_event_or_illustrative_subject(
            "still-sea.mp4",10,.5,contract,
            {"verification":"local_clip_screening"},
            event_inspector=failed_inspector,opening=True)
    assert calls==[True]


def test_no_arbitrary_100ms_source_duration_overrequirement():
    """The verified 10.060s video can cover 10.000s without looping."""
    src=(Path(__file__).resolve().parents[1] /
         "scripts" / "studio_runtime.py").read_text()
    assert "quality = self.quality.validate(path, need=need)" in src
    assert "quality = self.quality.validate(path, need=need + 0.1)" not in src
    assert "verify_visible_event_or_illustrative_subject(" in src


def test_aurora_glow_production_89_search_stays_on_topic():
    """Regression: a luminous sky phenomenon is NOT glowing ocean footage."""
    topic = "Warum leuchten Polarlichter?"
    storyboard = [
        SimpleNamespace(**s) for s in
        ground_verified_documentary({}, topic, "de", scene_count=3)["scenes"]
    ]
    opening = build_contract(storyboard[0], topic, 1)
    assert opening["family"] == "glowing"
    assert opening["event_required"]
    assert opening["queries"][0] == "aurora borealis"
    assert all(
        ("aurora" in q.casefold() or "northern lights" in q.casefold())
        for q in opening["queries"]
    )
    assert not any("ocean" in q.casefold() or "bioluminescent" in q.casefold()
                   for q in opening["queries"])
    assert metadata_allows(opening, "Authentic aurora borealis northern lights")
    assert not metadata_allows(opening, "Bioluminescent ocean glowing blue waves")
    assert "aurora" in opening["positive"].casefold()

    # Invisible magnetic-field/gas mechanisms remain illustrative subjects:
    # no artificial footage depicting hidden scientific causes.
    for idx, scene in enumerate(storyboard[1:], 2):
        later = build_contract(scene, topic, idx)
        assert later["family"] == "illustrative_subject"
        assert later["event_required"] is False


def test_aurora_glow_uses_existing_real_video_gate_not_any_image():
    """The new query vocabulary must not bypass licensing / HD / motion."""
    topic = "Warum leuchten Polarlichter?"
    from pathlib import Path
    visuals = (Path(__file__).resolve().parents[1] /
               "scripts" / "studio_runtime.py").read_text()
    assert "StrictVisuals" in visuals
    contract = build_contract(SimpleNamespace(
        narration="Polarlichter leuchten hoch in der Atmosphäre der Erde.",
        object="aurora", action="ambient",
        visual_search_query="aurora borealis"), topic, 1)
    assert contract["event_required"] is True
    assert metadata_allows(contract, "aurora borealis") is True


@pytest.mark.parametrize("language", ["de", "en"])
def test_two_shot_aurora_is_source_approved_and_filmable(language, tmp_path):
    """#89: two distinct real aurora clips suffice for the complete mechanism."""
    from science_sources import discover_evidence, screen_narration
    from retention_storyboard import audit_storyboard
    topic = ("Warum leuchten Polarlichter?" if language == "de"
             else "Why Do Northern Lights Glow?")
    cards = ground_verified_documentary(
        {}, topic, language, scene_count=2)["scenes"]
    assert len(cards) == 2
    storyboard = SimpleNamespace(scenes=[SimpleNamespace(**s) for s in cards])
    assert audit_storyboard(topic, storyboard, language)["state"] == "editorial_screen_passed"
    references = discover_evidence(topic, language)
    assert references.method == "curated_editor_reviewed"
    report = tmp_path / f"aurora-{language}.json"
    screen_narration(storyboard, references, None, path=report)
    assert json.loads(report.read_text())["state"] == "curated_editor_reviewed"
    first = build_contract(storyboard.scenes[0], topic, 1)
    second = build_contract(storyboard.scenes[1], topic, 2)
    assert first["family"] == "glowing"
    assert second["family"] == "illustrative_subject"
    assert len({s["narration"] for s in cards}) == 2


def test_aurora_production_scene_count_is_two_without_weakened_video_gate():
    source = (Path(__file__).resolve().parents[1] /
              "scripts" / "render_job.py").read_text()
    assert '2 if verified_kind == "northern_lights_glow"' in source
    assert "min_scenes=script_scene_count" in source
    assert "max_scenes=script_scene_count" in source
    assert "validate_narration_timing(palette, screenplay" in source
