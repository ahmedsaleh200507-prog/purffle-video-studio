"""V5 #106 footage regressions: octopus black stripe and port-only ship."""
from PIL import Image, ImageDraw

from visual_crop_integrity import assess_portrait_pillarbox
from topic_footage import opening_subject_prompts


def source_frame(*, pillarbox=False, dark=False, blank=False):
    if blank:
        return Image.new("RGB", (96, 168), (0, 0, 0))
    frame = Image.new("RGB", (96, 168), (19, 24, 34) if dark else (75, 134, 195))
    if pillarbox:
        ImageDraw.Draw(frame).rectangle((72, 0, 95, 167), fill=(0, 0, 0))
    return frame


def test_106_black_right_hand_portion_rejected_before_render():
    frames = [source_frame(pillarbox=True) for _ in range(3)]
    result = assess_portrait_pillarbox(frames)
    assert not result["verified"]
    assert result["reason"] == "persistent_black_side_pillarbox"
    assert result["black_side_frames"] == 3
    assert result["problem_sides"] == ["right"] * 3


def test_106_normal_dark_storm_not_mistaken_for_pillarboxing():
    frames = [source_frame(dark=True)] * 3
    assert assess_portrait_pillarbox(frames)["verified"]
    assert assess_portrait_pillarbox([source_frame()] * 3)["verified"]


def test_106_single_short_bad_frame_does_not_block_good_video():
    frames = [source_frame(pillarbox=True), source_frame(), source_frame()]
    assert assess_portrait_pillarbox(frames)["verified"]
    assert assess_portrait_pillarbox([source_frame(blank=True)] * 3)["verified"]
    assert not assess_portrait_pillarbox([])["verified"]


def test_106_ship_detector_compares_docks_and_cranes_not_just_empty_sea():
    spec = opening_subject_prompts("Why do steel ships float?")
    assert spec["subject"] == "floating_cargo_ship"
    negatives = " ".join(spec["negatives"]).casefold()
    assert "container terminal" in negatives
    assert "cranes" in negatives and "no ship" in negatives
    assert "large cargo container ship" in spec["positive"]


def test_106_illustrative_crop_gate_runs_before_scene_is_selected():
    from pathlib import Path
    src = Path("scripts/studio_runtime.py").read_text(encoding="utf-8")
    assert src.index("assess_portrait_pillarbox(crop_frames)") < src.index(
        'scene.update({"status": "selected"')
    assert "portrait_pillarbox_invalid" in src
