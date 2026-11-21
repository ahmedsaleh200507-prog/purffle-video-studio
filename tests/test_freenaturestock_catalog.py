"""Free Nature Stock automatic provider: static approved URLs, never crawl site.

Tests only exercise offline lookup and provider policy, never download media.
The normal downstream quality validator still gates real MP4 acceptance.
"""
from dataclasses import dataclass, field
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from video_sources import LicenseValidator, ProviderRegistry


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
    client = Mock()
    return ProviderRegistry(Item, client=client)


def test_no_keys_needed_and_provider_enabled(monkeypatch):
    for key in ("PIXABAY_API_KEY", "PEXELS_API_KEY", "EUROPEANA_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    reg = registry()
    status = next(x for x in reg.health() if x["provider"] == "freenaturestock-video")
    assert status["enabled"]
    clips = reg.search("freenaturestock-video", "ocean coast waves")
    assert clips
    assert clips[0].source == "freenaturestock-video"
    assert clips[0].url == (
        "https://cdn.freenaturestock.com/videos/freenaturestock-rugged-ocean-coast.mp4"
    )
    assert clips[0].width == 3840 and clips[0].height == 2160
    assert clips[0].extra["license"]["id"] == "CC0-1.0"
    assert LicenseValidator.validate(clips[0].extra["license"])
    assert clips[0].extra["catalog_mode"] == "manually_verified_official_downloads_no_crawl"
    reg.client.get.assert_not_called()


def test_automatic_query_matches_clouds_and_river_without_scraping():
    reg = registry()
    clouds = reg.search("freenaturestock-video", "clouds moving sky")
    assert len(clouds) >= 2
    assert all("cloud" in x.text.casefold() for x in clouds)
    river = reg.search("freenaturestock-video", "river water")
    assert any("River" in x.text for x in river)
    assert all(x.url.startswith("https://cdn.freenaturestock.com/videos/") for x in clouds + river)
    assert all(x.kind == "video" for x in clouds + river)
    reg.client.get.assert_not_called()


def test_no_invented_aurora_or_lightning_footage():
    reg = registry()
    assert reg.search("freenaturestock-video", "aurora borealis") == []
    assert reg.search("freenaturestock-video", "thunder lightning") == []
    assert reg.search("freenaturestock-video", "unrelated car driving") == []
    reg.client.get.assert_not_called()


def test_allowlist_is_curated_official_downloads_not_unbounded_scraper():
    path = Path(__file__).resolve().parents[1] / "data" / "freenaturestock_video_catalog.json"
    catalog = json.loads(path.read_text(encoding="utf-8"))
    assert catalog["license_id"] == "CC0-1.0"
    assert "No live crawling" in catalog["policy"]
    assert len(catalog["clips"]) == 12
    for row in catalog["clips"]:
        assert row["video_url"].startswith("https://cdn.freenaturestock.com/videos/")
        assert row["source_page"].startswith("https://freenaturestock.com/video/")
        assert row["video_url"].endswith(".mp4")
        assert min(row["width"], row["height"]) >= 1080
        assert row["duration"] >= 10
    assert len(set(x["video_url"] for x in catalog["clips"])) == 12


def test_no_host_spoofing_from_edited_manifest(monkeypatch):
    catalog_path = Path(__file__).resolve().parents[1] / "data" / "freenaturestock_video_catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    evil = dict(catalog["clips"][0], video_url="https://cdn.freenaturestock.com.evil.invalid/videos/hack.mp4",
                title="Ocean Coast Waves")
    injected = dict(catalog, clips=[evil])
    original = Path.read_text

    def fake_read(self, *args, **kwargs):
        if self.name == "freenaturestock_video_catalog.json":
            return json.dumps(injected)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read)
    reg = registry()
    assert reg.search("freenaturestock-video", "ocean coast waves") == []
    reg.client.get.assert_not_called()


def test_real_video_workflows_include_fns_and_do_not_change_locked_english_voice():
    root = Path(__file__).resolve().parents[1] / ".github" / "workflows"
    for name in ("videos.yml", "one-german-bathroom-mirror-20261118.yml",
                 "daily-life-five-20261118.yml",
                 "one-video-volcanic-island-20261118.yml"):
        yml = (root / name).read_text()
        assert "freenaturestock-video" in next(line for line in yml.splitlines() if "VISUAL_SOURCES:" in line)
        assert "PURFFLE_NARRATOR_LOCK: '1'" in yml
