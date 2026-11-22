"""Free-source and scene-identity regressions from Productions #91/#92.

Offline contracts only. These checks do NOT claim an MP4 was downloaded,
USGS footage met 720p, or that a YouTube-quality rendered video exists.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import Mock

import pytest

from video_sources import ProviderRegistry, LicenseValidator
from topic_footage import opening_subject_prompts
from opening_impact import _semantic_subject_screen


@dataclass
class Item:
    source: str
    id: str
    kind: str
    url: str = ""
    width: int = 0
    height: int = 0
    duration: float = 0
    credit: str = ""
    query: str = ""
    rank: int = 0
    text: str = ""
    extra: dict = field(default_factory=dict)


def registry():
    return ProviderRegistry(Item, client=Mock())


def test_usgs_curated_official_lava_is_free_and_does_not_need_an_api_key(monkeypatch):
    monkeypatch.setenv("PURFFLE_NO_ATTRIBUTION", "1")
    result = registry().search("usgs-video", "lava flowing into ocean")
    assert len(result) == 4
    assert len({row.url for row in result}) == len(result)
    for item in result:
        assert item.source == "usgs-video"
        assert item.url.startswith("https://usgs-ocapsv2-public-input-media.s3.us-west-2.amazonaws.com/")
        assert item.extra["catalog_mode"] == "reviewed_official_usgs_gallery_download"
        assert item.width == item.height == 0  # ffprobe MUST inspect the real source
        assert LicenseValidator.validate(item.extra["license"])
        assert item.extra["license"]["attribution_required"] is False
        assert item.extra["license"]["id"] == "PDM-1.0"


@pytest.mark.parametrize("unrelated", [
    "whale jumping ocean", "foggy bathroom mirror", "lightning sky",
    "bioluminescent sea", "iceberg breaking",
])
def test_usgs_lava_does_not_fill_unrelated_science_scenes(unrelated):
    reg = registry()
    assert reg.search("usgs-video", unrelated) == []
    reg.client.get.assert_not_called()


@pytest.mark.parametrize("tamper", [
    {"video_url": "https://evil.example.org/lava.mp4"},
    {"source_page": "https://not-usgs.example.org/media/videos/lava"},
    {"rights_statement": "CC BY-SA 4.0"},
    {"creator": "Outside Contributor"},
    {"video_url": "https://usgs-ocapsv2-public-input-media.s3.us-west-2.amazonaws.com/elsewhere.mp4"},
])
def test_usgs_never_trusts_unapproved_manifest_links_or_rights(monkeypatch, tamper):
    original_read_text = Path.read_text
    filename = "usgs_public_domain_video_catalog.json"
    def substituted(path, *args, **kwargs):
        if Path(path).name == filename:
            source = json.loads(original_read_text(path, *args, **kwargs))
            source["clips"] = [{**source["clips"][0], **tamper}]
            return json.dumps(source)
        return original_read_text(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", substituted)
    assert registry().search("usgs-video", "lava ocean") == []


def test_usgs_catalog_never_masquerades_as_measured_hd():
    source = (Path(__file__).resolve().parents[1] /
              "scripts" / "studio_runtime.py").read_text()
    assert "self.quality.validate(path, need=need)" in source
    assert "portrait_crop_allowed(native_scale)" in source
    assert "min(item.width, item.height) < 720" in source


def test_mirror_has_subject_gate_that_rejects_outdoor_palm_trees():
    spec = opening_subject_prompts("Warum beschlägt der Badezimmerspiegel?")
    assert spec["subject"] == "bathroom_mirror"
    assert "palm" in " ".join(spec["negatives"]).lower()
    # Two actual frames judged to look more like palm trees than mirrors.
    frame_scores = [[.17, .38, .23, .31], [.16, .42, .25, .30]]
    verdict = _semantic_subject_screen(
        [object(), object()], spec, scorer=lambda f, text: frame_scores)
    assert not verdict["verified"]


def test_real_mirror_not_rejected_as_palm_tree_when_visible():
    spec = opening_subject_prompts("Warum beschlägt der Badezimmerspiegel?")
    frame_scores = [[.42, .18, .20, .19], [.44, .14, .19, .18]]
    verdict = _semantic_subject_screen(
        [object(), object()], spec, scorer=lambda f, text: frame_scores)
    assert verdict["verified"]


def test_iceberg_scene_screen_explicitly_contrasts_boat_without_ice():
    spec = opening_subject_prompts("Why Do Icebergs Break Apart?")
    assert spec["subject"] == "iceberg"
    assert "boat" in " ".join(spec["negatives"]).lower()


def test_second_scene_sampled_after_first_second_to_catch_midscene_mismatch():
    source = (Path(__file__).resolve().parents[1] /
              "scripts" / "studio_runtime.py").read_text()
    assert "if idx == 0:" in source
    assert "seconds=(.15, mid)" in source
    assert "visual_subject_not_grounded" in source


def test_broaden_commons_and_nasa_no_extra_search_rounds():
    reg = registry()
    reg.client.get.return_value = {"query": {"pages": {}}}
    assert reg.search("wikimedia-video", "lightning") == []
    assert reg.client.get.call_args.kwargs["params"]["gsrlimit"] == 30
    reg.client.get.reset_mock()
    reg.client.get.return_value = {"collection": {"items": []}}
    assert reg.search("nasa-video", "volcano") == []
    assert reg.client.get.call_args.kwargs["params"]["page_size"] == 12
