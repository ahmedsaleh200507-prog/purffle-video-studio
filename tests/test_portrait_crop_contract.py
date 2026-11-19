"""The #68 real-world regression: 5 verified clips must not fail in FFmpeg.

The archive has 2 correctly selected 1080p landscape videos needing 1.18519x
portrait crop. Search accepted both, while strict_prepare_segment previously
rejected ANY enlargement. This tests selection/render/output as one contract.
"""
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from media_validation import portrait_crop_allowed, portrait_crop_limit
from studio_runtime import _native_portrait_scale, strict_prepare_segment
from render_job import validate_result


@pytest.mark.parametrize("width,height,allowed", [
    (1440, 1080, True),  # hurricane eye, Wikimedia scene 1 (#68)
    (3840, 2160, True),  # 4K thematic storm scenes 2-4 (#68)
    (1920, 1080, True),  # hurricane eye, Wikimedia scene 5 (#68)
    (1280, 720, False),  # unsafe 1.78x portrait crop
    (540, 960, False),   # too little original detail for 720p
])
def test_actual_source_dimensions_share_a_crop_quality_policy(
        width, height, allowed, monkeypatch):
    monkeypatch.setenv("PURFFLE_MAX_PORTRAIT_UPSCALE", "1.20")
    scale = _native_portrait_scale({"width": width, "height": height}, 720, 1280)
    assert portrait_crop_allowed(scale) is allowed
    if (width, height) in ((1440, 1080), (1920, 1080)):
        assert scale == pytest.approx(1.185185, rel=1e-5)


@pytest.mark.parametrize("width,height,allowed", [
    (1440, 1080, True),
    (1920, 1080, True),
    (3840, 2160, True),
    (1280, 720, False),
])
def test_renderer_applies_same_bound_as_search(tmp_path, monkeypatch, width, height, allowed):
    calls = []
    # The FFmpeg interface is stubbed here; the test guards that the renderer
    # REACHES the encode step instead of rejecting already verified clips.
    upstream = types.ModuleType("purffle_shorts")
    upstream.__path__ = []
    upstream.ffmpeg = SimpleNamespace(
        run=lambda args, **kwargs: calls.append((args, kwargs)))
    render = types.ModuleType("purffle_shorts.render")
    render._encode_args = lambda settings, final=False: ["-c:v", "libx264"]
    render._grade = lambda settings: ""
    monkeypatch.setitem(sys.modules, "purffle_shorts", upstream)
    monkeypatch.setitem(sys.modules, "purffle_shorts.render", render)
    item = SimpleNamespace(kind="video", path=tmp_path / "source.webm",
                           duration=12, width=width, height=height,
                           extra={"strict_validated": True,
                                  "match": {"crop_focus_x": 0.5}})
    item.path.write_bytes(b"mock video source")
    settings = SimpleNamespace(width=720, height=1280, fps=30)
    if allowed:
        out = strict_prepare_segment(item, 3, 0, settings, tmp_path)
        assert out.name == "seg00.mp4"
        assert len(calls) == 1
        assert "scale=720:1280" in " ".join(calls[0][0])
        assert item.extra["crop"]["crop_scale"] == pytest.approx(
            _native_portrait_scale({"width": width, "height": height}, 720, 1280), rel=1e-3)
    else:
        with pytest.raises(RuntimeError, match="insufficient_native_resolution"):
            strict_prepare_segment(item, 3, 0, settings, tmp_path)
        assert calls == []


def test_strict_native_only_mode_rejects_1080p_landscape(tmp_path, monkeypatch):
    monkeypatch.setenv("PURFFLE_MAX_PORTRAIT_UPSCALE", "1.0")
    assert portrait_crop_limit() == 1.0
    assert not portrait_crop_allowed(
        _native_portrait_scale({"width": 1920, "height": 1080}, 720, 1280))


def test_successful_hurricane_scene_report_is_accepted_at_final_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("PURFFLE_MAX_PORTRAIT_UPSCALE", "1.20")
    monkeypatch.setenv("RESOLUTION", "720x1280")
    # Exact measured crop scales and order from purffle-videos-68.zip.
    dimensions = [(1440, 1080), (3840, 2160), (3840, 2160),
                  (3840, 2160), (1920, 1080)]
    scenes = []
    for idx, (width, height) in enumerate(dimensions, 1):
        scenes.append({
            "index": idx, "status": "selected",
            "source": "pixabay" if idx in (2, 3, 4) else "wikimedia-video",
            "sha256": str(idx) * 64,
            "match": {"visual_score": .27}, "license": {"id": "PDM-1.0"},
            "quality": {"width": width, "height": height,
                        "portrait_crop_scale": _native_portrait_scale(
                            {"width": width, "height": height}, 720, 1280)},
        })
    report = tmp_path / "footage-report.json"
    report.write_text(json.dumps({"state": "footage_ready", "scenes": scenes}))
    clip = tmp_path / "final.mp4"
    clip.write_bytes(b"fake MP4 checked by mocked output probe")
    captions = tmp_path / "captions.srt"
    captions.write_text("1\n00:00:00,000 --> 00:00:03,000\nHurricane eye\n")
    with patch("media_validation.QualityValidator.validate",
               return_value={"width": 720, "height": 1280, "duration": 33, "has_audio": True}):
        _, validated = validate_result(clip, {"language": "de", "voice": "edge:de", "timing": "native"},
                                       captions, report)
    assert len(validated["scenes"]) == 5
    assert sum(x["quality"]["portrait_crop_scale"] > 1 for x in validated["scenes"]) == 2
