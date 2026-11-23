"""Production #93 visual false positives: offline regression coverage.

This checks candidate rules only. It does NOT claim new MP4s have rendered
or that USGS files actually pass native 720p FFprobe verification.
"""
from pathlib import Path

import pytest

from opening_impact import _semantic_subject_screen


def specification():
    return {
        "subject": "iceberg",
        "positive": "A very large clearly visible white iceberg on the water.",
        "negatives": (
            "A dark sea without any iceberg.",
            "A boat and water without the iceberg.",
        ),
    }


def screen(scores, **kwargs):
    frames = [object() for _ in scores]
    return _semantic_subject_screen(
        frames, specification(),
        scorer=lambda sample, captions: scores, **kwargs)


def test_persistent_iceberg_must_still_be_visible_in_final_scene_frame():
    # #93 second iceberg scene looked on topic at the start but almost
    # entirely dark water at the end. Median-only checks missed this drift.
    frames = [
        [.33, .21, .19],
        [.31, .23, .20],
        [.19, .27, .22],
    ]
    assert screen(frames)["verified"]
    result = screen(frames, require_all_frames=True, minimum_margin=.032)
    assert result["verified"] is False
    assert result["sampled_subject_frames"] == 3
    assert result["all_sampled_frames_subject_visible"] is False


def test_strong_subject_can_pass_in_all_three_scene_frames():
    result = screen([
        [.35, .20, .18],
        [.34, .19, .22],
        [.33, .20, .21],
    ], require_all_frames=True, minimum_margin=.032)
    assert result["verified"]
    assert result["all_sampled_frames_subject_visible"] is True


@pytest.mark.parametrize("margin", [.0135, .02, .031])
def test_production93_weak_similarity_margin_is_insufficient(margin):
    frames = [[.30, .30-margin, .18], [.30, .30-margin, .19]]
    assert screen(frames)["verified"] is True  # baseline historical threshold
    assert screen(frames, minimum_margin=.05)["verified"] is False
    assert screen(frames, minimum_margin=.032)["verified"] is False


def test_transient_lightning_does_not_require_constant_flash():
    # Flash can be momentary; it needs strong contrast, not permanence.
    good_flash = [[.37, .24, .22], [.20, .25, .24], [.38, .23, .20]]
    result = screen(good_flash, minimum_margin=.05, require_all_frames=False)
    assert result["verified"]
    assert result["all_sampled_frames_subject_visible"] is False


def test_usgs_gets_priority_for_actual_ocean_entry_not_every_lava_scene():
    source = (Path(__file__).resolve().parents[1] /
              "scripts/studio_runtime.py").read_text()
    assert 'exact_ocean_entry = (is_lava_ocean_topic(topic)' in source
    assert 'source_order.insert(0, "usgs-video")' in source
    assert 'for source in source_order:' in source
    assert 'seconds=(.15, mid, near_end)' in source
    assert 'require_all_frames=permanent_subject' in source
