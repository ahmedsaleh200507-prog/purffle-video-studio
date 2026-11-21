"""All future Shorts must start with engaging verified first-second real footage.

These tests cover genuine decoded-frame heuristics and ordering contracts,
not any guarantee of YouTube audience retention.
"""
from types import SimpleNamespace

import pytest

from opening_impact import _evaluate_frames, prioritize_opening


def record(original, verified, impact, hot=0.0):
    return {"verified": verified, "impact": impact,
            "hot_lava_ratio": hot, "reason": "test"}


def palette():
    items = [SimpleNamespace(path=f"shot-{i}") for i in range(3)]
    plans = [{"visual_search_query": query} for query in (
        "calm ocean at night", "rough ocean waves", "huge breaking ocean wave")]
    reports = [{"id": i, "match": {"visual_score": .29}}
               for i in range(3)]
    return items, plans, reports


def test_best_first_seconds_used_for_any_topic_not_just_lava():
    items, plans, reports = palette()
    scores = {
        "shot-0": record(1, True, 22),
        "shot-1": record(2, True, 42),
        "shot-2": record(3, True, 75),
    }
    review = prioritize_opening(
        "How Do Huge Ocean Waves Form?", items, plans, reports,
        analyzer=lambda path: scores[path])
    assert review["state"] == "selected"
    assert review["original_scene"] == 3
    assert review["first_seconds_inspected"] is True
    assert review["no_opening_title"] is True
    assert items[0].path == "shot-2"
    assert plans[0]["visual_search_query"] == "huge breaking ocean wave"
    assert reports[0]["id"] == 2
    assert [row["id"] for row in reports] == [2, 0, 1]


def test_weak_black_or_still_intro_never_wins_even_with_high_raw_number():
    items, plans, reports = palette()
    scores = {
        "shot-0": record(1, False, 100),
        "shot-1": record(2, True, 33),
        "shot-2": record(3, True, 32),
    }
    review = prioritize_opening(
        "Why Do Ocean Waves Form?", items, plans, reports,
        analyzer=lambda path: scores[path])
    assert review["original_scene"] == 2
    assert reports[0]["id"] == 1


def test_no_strong_opening_fails_instead_of_approving_boring_video():
    items, plans, reports = palette()
    with pytest.raises(RuntimeError, match="opening_quality_unverified"):
        prioritize_opening(
            "Why Do Ocean Waves Form?", items, plans, reports,
            analyzer=lambda path: record(1, True, 10))
    assert [x.path for x in items] == ["shot-0", "shot-1", "shot-2"]


def test_lava_intro_must_show_measurable_lava_in_first_seconds():
    items, plans, reports = palette()
    # Generic seascape can be high-contrast, but is not a lava reveal.
    scores = {
        "shot-0": record(1, True, 93, 0),
        "shot-1": record(2, True, 56, 0.04),
        "shot-2": record(3, True, 67, .001),
    }
    result = prioritize_opening(
        "What Happens When Lava Hits the Ocean?", items, plans, reports,
        analyzer=lambda path: scores[path])
    assert result["original_scene"] == 2
    assert items[0].path == "shot-1"


def test_lava_without_visible_first_second_lava_rejected():
    items, plans, reports = palette()
    with pytest.raises(RuntimeError, match="opening_quality_unverified"):
        prioritize_opening(
            "What Happens When Lava Hits the Ocean?", items, plans, reports,
            analyzer=lambda _: record(1, True, 95, 0))


def test_does_not_falsely_certify_test_doubles_or_lose_provenance():
    # Offline CI metadata stubs do not carry actual video files.
    items = [SimpleNamespace(), SimpleNamespace()]
    plans = [{"visual_search_query": "real waves"} for _ in items]
    reports = [{"id": i} for i in range(2)]
    result = prioritize_opening("Why Do Ocean Waves Form?", items, plans, reports)
    assert result["state"] == "not_evaluated_without_real_video"
    assert reports == [{"id": 0}, {"id": 1}]


def test_one_missing_video_file_cannot_be_called_verified():
    items, plans, reports = palette()
    items[1].path = None
    with pytest.raises(RuntimeError, match="opening_quality_unverified"):
        prioritize_opening("Why Do Ocean Waves Form?", items, plans, reports)


def test_early_frame_metrics_require_light_detail_and_motion():
    Image = pytest.importorskip("PIL.Image")
    from PIL import ImageDraw
    still = Image.new("RGB", (96, 170), "#344e67")
    assert _evaluate_frames([still, still])["verified"] is False
    dark = Image.new("RGB", (96, 170), "#000000")
    assert _evaluate_frames([dark, dark])["verified"] is False
    first = Image.new("RGB", (96, 170), "#182739")
    second = Image.new("RGB", (96, 170), "#182739")
    one, two = ImageDraw.Draw(first), ImageDraw.Draw(second)
    for x in range(0, 96, 12):
        one.rectangle((x, 10, x+7, 130), fill="#ff3a0a")
        two.rectangle((min(95,x+5), 10, min(95,x+10), 130), fill="#ffb222")
    result = _evaluate_frames([first, second])
    assert result["verified"] is True
    assert result["hot_lava_ratio"] > .006
    assert result["impact"] >= 24


def test_empty_decoder_does_not_claim_visual_success():
    assert _evaluate_frames([]) == {
        "verified": False, "reason": "opening_frame_decode_failed"}


def test_integration_happens_before_script_voice_and_render():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    preflight = (root / "scripts" / "media_first.py").read_text()
    producer = (root / "scripts" / "render_job.py").read_text()
    assert preflight.index("opening_review = prioritize_opening(") < preflight.index(
        "# Re-number successful selections")
    assert '"opening_review": opening_review' in preflight
    assert producer.index("screen_narration(") < producer.index("prepare_verified_palette(")
    assert producer.index("studio.draft(") < producer.index("prepare_verified_palette(")
    assert producer.index("studio.draft(") < producer.index("studio.produce(")
    assert "hook_overlay=False" in producer
    assert "screen_narration(" in producer


def test_production_83_abandoned_ship_does_not_win_buoyancy_hook():
    items, plans, reports = palette()
    reports[0]["source_url"] = (
        "https://coverr.co/videos/an-abandoned-ship-in-tierra-del-fuego-argentina")
    reports[1]["source_url"] = "https://pixabay.com/videos/freighter-cruising-at-sea"
    reports[2]["source_url"] = "https://pixabay.com/videos/cargo-ship-on-water"
    scores = {
        "shot-0": record(1, True, 97),
        "shot-1": record(2, True, 68),
        "shot-2": record(3, True, 53),
    }
    result = prioritize_opening("Why Do Steel Ships Float?", items, plans,
                                reports, analyzer=lambda path: scores[path])
    assert result["original_scene"] == 2
    assert result["clip_scores"][0]["verified"] is False
    assert result["clip_scores"][0]["reason"] == (
        "opening_source_does_not_demonstrate_floating_ship")
    assert items[0].path == "shot-1"


def test_unrelated_documentary_does_not_inherit_ship_hook_rejection():
    items, plans, reports = palette()
    reports[0]["source_url"] = "https://coverr.co/videos/an-abandoned-ship"
    scores = {"shot-0": record(1, True, 97),
              "shot-1": record(2, True, 68),
              "shot-2": record(3, True, 53)}
    result = prioritize_opening("How Did an Abandoned Ship Become a Wreck?",
                                items, plans, reports,
                                analyzer=lambda path: scores[path])
    assert result["original_scene"] == 1
